"""What a forwarded message *is*, decided from the message and from nothing else.

Everything here is a pure function over `bytes` and plain values, like every
other module under `domain/` (AGENTS.md): no database, no HTTP, no AWS and no
clock it is not handed. That is what makes the sender policy and the part rules
assertable without a server, a mailbox or an AWS account — and the sender policy
is the whole of this feature's answer to the brief's **A09**, so it had better be
testable on its own.

Four rules shape the module, all from the spec's Security section:

- **The sender policy runs before anything is fetched.** Its inputs are the
  verified SNS notification's own fields — SES's authentication and scan
  verdicts, and the `From` it reports — never a header out of the MIME body.
  `decide_sender` therefore takes verdicts and an allow-list, and returns a
  verdict; it cannot fetch anything even by accident.
- **A missing verdict is a failure.** SES omitting `dmarcVerdict` means SES did
  not say, and the only safe reading of "did not say" is "no". Failing open here
  would make the control depend on a field an outage can drop.
- **HTML is reduced to text and the HTML is discarded.** `html.parser` is the
  standard library's own parser, not a binary decoder, so this carries none of
  the parser-CVE weight the attachments spec refused. It exists so that no
  stored value is ever a document a browser could later be persuaded to render:
  the inbox renders `text_body` as text, and there is no markup to render.
- **Remote content is never fetched.** Tracking pixels, remote images and linked
  stylesheets all vanish with the tags, because the reducer keeps text and drops
  every element — including, deliberately, the contents of `<script>` and
  `<style>`, which are not text the owner wrote.

Part selection reuses `domain/uploads.py`'s sniffing **unchanged**: a part is a
document if its own bytes say it is a PDF, a JPEG or a PNG. A part that is not
one of those three — an `.ics`, a `.zip`, an inline signature — is **dropped and
counted, never stored, and never a reason to reject the whole message**, because
the text is usually the part worth reading.
"""

from __future__ import annotations

import email
import email.policy
import unicodedata
from dataclasses import dataclass
from email.message import Message
from enum import StrEnum
from html.parser import HTMLParser

from trip_planner.domain.uploads import (
    MAX_ATTACHMENT_BYTES,
    InspectedUpload,
    UploadRejection,
    inspect_upload,
    normalise_filename,
)

__all__ = [
    "MAX_INBOUND_DOCUMENTS",
    "MAX_INBOUND_SUBJECT_CHARS",
    "MAX_INBOUND_TEXT_CHARS",
    "MAX_MIME_PARTS",
    "TRUNCATION_MARKER",
    "InboundDocument",
    "QuarantineReason",
    "SelectedContent",
    "SenderDecision",
    "decide_sender",
    "decide_stored_sender",
    "html_to_text",
    "normalise_address",
    "normalise_subject",
    "normalise_verdict",
    "select_content",
    "truncate_text",
]

#: The stored text body's bound, in characters. Mirrors the `CHECK` on
#: `inbound_message.text_body` — the column restates it so a write path that
#: skipped this module still cannot store more.
MAX_INBOUND_TEXT_CHARS = 200_000

#: The subject's bound, likewise mirrored by a `CHECK`.
MAX_INBOUND_SUBJECT_CHARS = 1000

#: Appended when the text is cut, so a truncated body never looks complete.
#: Typographic rather than prose, deliberately: it needs no translation and
#: therefore cannot go missing from one locale.
TRUNCATION_MARKER = "\n\n[…]"

#: How many MIME parts are walked before the rest are dropped and counted.
#:
#: The bound is on the **walk**, not on a list built afterwards, for the reason
#: `api/attachments.py`'s `MAX_PARTS` gives: a message can carry far more parts
#: than it carries useful bytes, and building one object per part before
#: counting is how a small message costs a large amount of memory.
MAX_MIME_PARTS = 100

#: How many documents one message may contribute. Twenty is the shipped
#: per-parent attachment cap; ten is well past any real confirmation — a
#: boarding pass, a voucher and a receipt is three — and leaves room under the
#: cap for what the owner attaches by hand afterwards.
MAX_INBOUND_DOCUMENTS = 10

#: SES's own verdict vocabulary. Only `PASS` is a pass: `GRAY`,
#: `PROCESSING_FAILED` and `DISABLED` all mean SES did not establish the thing
#: being asked about, and are treated exactly like `FAIL`.
_VERDICT_PASS = "PASS"

#: Recorded — and quarantined on — when the notification carried no verdict at all.
VERDICT_UNKNOWN = "unknown"

_TEXT_PLAIN = "text/plain"
_TEXT_HTML = "text/html"
_DROPPED_HTML_ELEMENTS = frozenset({"script", "style", "template"})
#: Elements whose end implies a line break, so a reduced table or list does not
#: run into one unreadable paragraph.
_BLOCK_HTML_ELEMENTS = frozenset(
    {
        "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "ul", "ol", "blockquote", "section", "article", "header", "footer",
    }
)


class QuarantineReason(StrEnum):
    """Why a message was held at the door. The value is a translation key suffix.

    Three reasons and not one, because the owner's way out differs for each and
    a single "rejected" would collapse a recoverable false positive into a dead
    end. See `SenderDecision` for which recovery each one permits.
    """

    #: The `From` is on no allow-list, but SES says it authenticated.
    UNKNOWN_SENDER = "unknown_sender"
    #: DMARC failed, or SES did not report it. Covers the mailbox rule that
    #: auto-forwards an airline's confirmation while preserving the airline's
    #: `From` — a real false positive, which is why release exists.
    FAILED_AUTHENTICATION = "failed_authentication"
    #: SES's spam or virus scan said no. Not recoverable from the application.
    FAILED_SCAN = "failed_scan"


@dataclass(frozen=True, slots=True)
class SenderDecision:
    """Whether to fetch this message's MIME at all, and what the owner may do about it.

    `accepted` is the only field the ingestion path branches on. The two
    recovery flags exist so the screen can offer the *right* action rather than
    both — offering *Trust this sender* for a DMARC failure would add a spoofable
    address to the allow-list permanently, which is a policy change dressed up
    as a recovery.
    """

    accepted: bool
    reason: QuarantineReason | None = None

    @property
    def may_trust_sender(self) -> bool:
        """Only for an unknown address that SES says authenticated.

        Trusting is permanent and applies to later mail, so it is offered only
        where "this really is who it says it is" has already been established.
        """
        return self.reason is QuarantineReason.UNKNOWN_SENDER

    @property
    def may_release_message(self) -> bool:
        """Only for a failed or missing authentication verdict, and only ever for one message.

        Release bypasses the verdict for exactly one stored SES object after
        re-checking its metadata; it trusts nobody and changes no policy. A
        failed *scan* is deliberately excluded: a virus verdict is not a false
        positive the owner is in a position to overrule.
        """
        return self.reason is QuarantineReason.FAILED_AUTHENTICATION


def normalise_address(address: str) -> str:
    """The comparison form for a sender address.

    Kept here as well as on the model because the policy is a pure function and
    must be callable without importing SQLAlchemy; the two agree by having the
    same one-line definition, and `tests/test_domain_inbound.py` asserts they do.
    """
    return address.strip().lower()


def decide_sender(
    *,
    from_address: str,
    dmarc_verdict: str | None,
    spam_verdict: str | None,
    virus_verdict: str | None,
    allowed: frozenset[str] | set[str],
) -> SenderDecision:
    """The whole of the sender policy, over the verified notification's fields.

    **Order matters and is not arbitrary.** The scan verdicts are checked first
    because a virus verdict is the one outcome no owner action may overrule, and
    deciding it after the allow-list would mean an allow-listed address could
    carry one through. Authentication comes next, so a spoofed forward from an
    allow-listed address is a stranger rather than the owner. The allow-list is
    last, which is what makes `UNKNOWN_SENDER` mean *"authenticated, just not
    known"* — the only state in which trusting an address permanently is a
    defensible thing to offer.

    Every verdict is `None`-safe in the same direction: absent is not a pass.
    """
    if not _passes(spam_verdict) or not _passes(virus_verdict):
        return SenderDecision(accepted=False, reason=QuarantineReason.FAILED_SCAN)

    if not _passes(dmarc_verdict):
        return SenderDecision(accepted=False, reason=QuarantineReason.FAILED_AUTHENTICATION)

    if normalise_address(from_address) not in {normalise_address(one) for one in allowed}:
        return SenderDecision(accepted=False, reason=QuarantineReason.UNKNOWN_SENDER)

    return SenderDecision(accepted=True)


def decide_stored_sender(
    *,
    from_address: str,
    sender_verdict: str,
    scan_verdict: str,
    allowed: frozenset[str] | set[str],
) -> SenderDecision:
    """`decide_sender` over the two verdicts the row actually stores.

    The row keeps one scan verdict rather than two because the owner's remedy is
    identical either way, and the *failing* one is what is kept — so a row that
    says `FAIL` says why it was quarantined. Feeding it to both scan parameters
    is therefore exact rather than approximate: if either scan failed, this is
    the one that did.

    `VERDICT_UNKNOWN` is not a pass, so a row recorded from a notification that
    carried no verdict quarantines here exactly as it would have at the endpoint.
    """
    return decide_sender(
        from_address=from_address,
        dmarc_verdict=sender_verdict,
        spam_verdict=scan_verdict,
        virus_verdict=scan_verdict,
        allowed=allowed,
    )


def _passes(verdict: str | None) -> bool:
    """`PASS` and nothing else — a missing verdict is a failure, not a shrug."""
    return verdict is not None and verdict.strip().upper() == _VERDICT_PASS


def normalise_verdict(verdict: str | None) -> str:
    """The form stored on the row, so a missing verdict is visible rather than blank."""
    cleaned = (verdict or "").strip().upper()
    return cleaned or VERDICT_UNKNOWN


# --------------------------------------------------------------------------- #
# HTML, reduced to text
# --------------------------------------------------------------------------- #


class _TextExtractor(HTMLParser):
    """Keeps character data, drops every tag, and drops `<script>`/`<style>` wholesale.

    Not a sanitiser — there is nothing to sanitise, because no markup survives.
    A sanitiser's job is to decide which tags are safe to keep, and keeping none
    is both stricter and very much simpler to be sure about.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._suppressed = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in _DROPPED_HTML_ELEMENTS:
            self._suppressed += 1
        elif tag in _BLOCK_HTML_ELEMENTS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DROPPED_HTML_ELEMENTS:
            self._suppressed = max(0, self._suppressed - 1)
        elif tag in _BLOCK_HTML_ELEMENTS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._suppressed:
            self._chunks.append(data)

    @property
    def text(self) -> str:
        return "".join(self._chunks)


def html_to_text(html: str) -> str:
    """An HTML body as plain text, with the markup discarded rather than stored.

    Whitespace is collapsed per line and blank lines are dropped **entirely**,
    which is a judgement rather than an oversight: mail HTML is overwhelmingly
    layout — nested tables, spacer rows, a `<p>` per line — so preserving its
    vertical rhythm produces a column of empty lines rather than a readable
    message. A list becomes one item per line, which is what it looks like.
    """
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()

    lines = [" ".join(line.split()) for line in extractor.text.splitlines()]

    return "\n".join(line for line in lines if line).strip()


def truncate_text(text: str) -> str:
    """Cut to the stored bound, with the marker inside it rather than past it.

    Cutting to exactly the bound and *then* appending would produce a string the
    column's `CHECK` refuses — the classic off-by-a-marker. The marker's own
    length is taken out of the budget instead.
    """
    if len(text) <= MAX_INBOUND_TEXT_CHARS:
        return text
    return text[: MAX_INBOUND_TEXT_CHARS - len(TRUNCATION_MARKER)] + TRUNCATION_MARKER


def normalise_subject(raw: str | None) -> str:
    """The subject reduced to something safe to store and to show.

    Control characters go — a newline in a value that later reaches a header or
    a log line is an injection primitive, and the subject is attacker-controlled
    in exactly the way a filename is. Then whitespace is collapsed and the
    result is cut to the column's bound.

    They are replaced by a **space**, not deleted, and the difference is visible
    in the output: a tab between two words is a word separator, so deleting it
    turns `Rezerwacja\\tKL-4411` into one meaningless token. `normalise_filename`
    deletes them instead, correctly — a filename must not gain spaces it never
    had — which is why these are two functions and not one shared helper.
    """
    text = unicodedata.normalize("NFC", raw or "")
    text = "".join(
        " " if unicodedata.category(char) in ("Cc", "Cf") else char for char in text
    )
    text = " ".join(text.split())
    return text[:MAX_INBOUND_SUBJECT_CHARS]


# --------------------------------------------------------------------------- #
# Selecting what is worth keeping out of a MIME message
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class InboundDocument:
    """One accepted attachment part: its bytes, its display name, its derived type."""

    filename: str
    data: bytes
    inspected: InspectedUpload


@dataclass(frozen=True, slots=True)
class SelectedContent:
    """Everything worth keeping out of one message.

    `dropped_documents` is carried rather than discarded because the screen says
    *which* documents did not make it — "a message is never lost because a
    document was too big; the document is dropped and named as dropped".
    """

    text: str
    documents: tuple[InboundDocument, ...]
    dropped_documents: int


def select_content(raw_mime: bytes) -> SelectedContent:
    """Walk one raw MIME message and keep the text and the documents.

    The text is the first `text/plain` part; failing that, the first `text/html`
    reduced by `html_to_text`. Preferring plain text is not a style choice — it
    is what the sender wrote, whereas the HTML alternative is what a mail client
    generated, and reducing the latter is strictly lossier.

    A part is a document when **its own bytes** sniff as PDF, JPEG or PNG. The
    part's declared `Content-Type` and its filename extension are not consulted,
    exactly as they are not for a browser upload: `ticket.pdf` whose bytes are a
    JPEG is a JPEG, and `photo.jpg` whose bytes are an HTML page is dropped.
    """
    try:
        message: Message = email.message_from_bytes(raw_mime, policy=email.policy.default)
    except Exception:
        # A message this malformed still arrived, and losing it silently would be
        # worse than storing an empty body the owner can look at and delete.
        return SelectedContent(text="", documents=(), dropped_documents=0)

    plain: str | None = None
    html: str | None = None
    documents: list[InboundDocument] = []
    dropped = 0

    for index, part in enumerate(message.walk()):
        if index >= MAX_MIME_PARTS:
            dropped += 1
            continue
        if part.get_content_maintype() == "multipart":
            continue

        content_type = part.get_content_type()
        payload = _payload_of(part)
        if payload is None:
            dropped += 1
            continue

        is_body = part.get_content_disposition() != "attachment"
        if is_body and content_type == _TEXT_PLAIN and plain is None:
            plain = _decode(part, payload)
            continue
        if is_body and content_type == _TEXT_HTML and html is None:
            html = _decode(part, payload)
            continue

        document = _as_document(part, payload)
        if document is None:
            dropped += 1
            continue
        if len(documents) >= MAX_INBOUND_DOCUMENTS:
            dropped += 1
            continue
        documents.append(document)

    text = plain if plain is not None else (html_to_text(html) if html is not None else "")

    return SelectedContent(
        text=truncate_text(text.strip()),
        documents=tuple(documents),
        dropped_documents=dropped,
    )


def _payload_of(part: Message) -> bytes | None:
    """The part's decoded bytes, or `None` when it has none we can read.

    Broad `except` on purpose: `get_payload(decode=True)` raises a family of
    errors over malformed base64 and unknown transfer encodings, and every one
    of them means the same thing here — this part is not readable, drop it and
    count it, and keep processing the rest of the message.
    """
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        return None
    return payload if isinstance(payload, bytes) else None


def _decode(part: Message, payload: bytes) -> str:
    """Text out of a part's bytes, never raising over a wrong or absent charset."""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        # A charset name no codec answers to. The bytes are still text.
        return payload.decode("utf-8", errors="replace")


def _as_document(part: Message, payload: bytes) -> InboundDocument | None:
    """An accepted document, or `None` for a part that is dropped and counted.

    The size check comes **before** `inspect_upload` so an oversized part is not
    structurally walked first; the sniffing is cheap, but the order is the one
    the upload path uses and there is no reason for the two to differ.
    """
    if not payload or len(payload) > MAX_ATTACHMENT_BYTES:
        return None

    inspected = inspect_upload(payload)
    if isinstance(inspected, UploadRejection):
        return None

    filename = normalise_filename(
        part.get_filename() or "", content_type=inspected.content_type
    )
    return InboundDocument(filename=filename.display, data=payload, inspected=inspected)
