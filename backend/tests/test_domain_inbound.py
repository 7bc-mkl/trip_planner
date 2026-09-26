"""The inbound domain rules, exercised without a server, a mailbox or AWS.

That is the point of the module being pure: the sender policy is the whole of
this feature's answer to the brief's **A09**, and a control that can only be
tested through an integration is a control nobody re-tests after the first time.

The message builders below construct real MIME with the standard library rather
than pasting captured bytes, so a fixture stays readable and a new case is three
lines instead of a hundred-line blob nobody edits.
"""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from tests.test_domain_uploads import make_jpeg, make_pdf, make_png
from trip_planner.domain.inbound import (
    MAX_INBOUND_DOCUMENTS,
    MAX_INBOUND_SUBJECT_CHARS,
    MAX_INBOUND_TEXT_CHARS,
    TRUNCATION_MARKER,
    VERDICT_UNKNOWN,
    QuarantineReason,
    decide_sender,
    html_to_text,
    normalise_address,
    normalise_subject,
    normalise_verdict,
    select_content,
    truncate_text,
)

OWNER = "owner@example.com"
ALLOWED = frozenset({OWNER})


def build(
    *,
    text: str | None = None,
    html: str | None = None,
    documents: list[tuple[str, bytes, str]] | None = None,
) -> bytes:
    """A raw MIME message with the parts a test cares about and nothing else."""
    message = EmailMessage()
    message["From"] = OWNER
    message["To"] = "inbox@mail.planner.example.com"
    message["Subject"] = "Potwierdzenie rezerwacji"

    if text is not None and html is not None:
        message.set_content(text)
        message.add_alternative(html, subtype="html")
    elif html is not None:
        message.set_content(html, subtype="html")
    else:
        message.set_content(text if text is not None else "")

    for filename, data, content_type in documents or []:
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    return message.as_bytes()


# --------------------------------------------------------------------------- #
# The sender policy — A09's answer
# --------------------------------------------------------------------------- #


def policy(**overrides: object) -> object:
    defaults: dict[str, object] = {
        "from_address": OWNER,
        "dmarc_verdict": "PASS",
        "spam_verdict": "PASS",
        "virus_verdict": "PASS",
        "allowed": ALLOWED,
    }
    defaults.update(overrides)
    return decide_sender(**defaults)  # type: ignore[arg-type]


def test_an_allow_listed_sender_that_passes_every_verdict_is_accepted() -> None:
    decision = policy()

    assert decision.accepted
    assert decision.reason is None


def test_an_unknown_sender_is_quarantined_and_may_be_trusted() -> None:
    """Authenticated, just not known — the only state in which trusting is defensible."""
    decision = policy(from_address="rezerwacje@airline.example")

    assert not decision.accepted
    assert decision.reason is QuarantineReason.UNKNOWN_SENDER
    assert decision.may_trust_sender
    assert not decision.may_release_message


def test_an_allow_listed_sender_failing_dmarc_is_treated_as_a_stranger() -> None:
    """A spoofed forward from the owner's own address is not the owner."""
    decision = policy(dmarc_verdict="FAIL")

    assert not decision.accepted
    assert decision.reason is QuarantineReason.FAILED_AUTHENTICATION
    assert decision.may_release_message
    # Trusting would add a spoofable address to the allow-list permanently.
    assert not decision.may_trust_sender


@pytest.mark.parametrize("verdict", [None, "", "GRAY", "PROCESSING_FAILED", "DISABLED"])
def test_a_missing_or_inconclusive_authentication_verdict_quarantines(
    verdict: str | None,
) -> None:
    """SES not saying is not SES saying yes.

    Failing open here would make the control depend on a field an SES outage can
    drop — the message would be accepted precisely when the infrastructure that
    vouches for it is unhealthy.
    """
    decision = policy(dmarc_verdict=verdict)

    assert not decision.accepted
    assert decision.reason is QuarantineReason.FAILED_AUTHENTICATION


@pytest.mark.parametrize("scan", ["spam_verdict", "virus_verdict"])
def test_a_failed_scan_is_quarantined_and_is_not_recoverable(scan: str) -> None:
    """The one outcome no owner action may overrule.

    Checked before the allow-list on purpose: deciding it afterwards would let an
    allow-listed address carry a virus verdict straight through.
    """
    decision = policy(**{scan: "FAIL"})

    assert not decision.accepted
    assert decision.reason is QuarantineReason.FAILED_SCAN
    assert not decision.may_trust_sender
    assert not decision.may_release_message


def test_a_virus_verdict_outranks_an_unknown_sender() -> None:
    """Precedence, stated as a test because the wrong order is invisible in review."""
    decision = policy(from_address="stranger@example.net", virus_verdict="FAIL")

    assert decision.reason is QuarantineReason.FAILED_SCAN


def test_the_allow_list_comparison_is_case_and_space_insensitive() -> None:
    decision = policy(
        from_address="  Owner@Example.COM ", allowed=frozenset({"owner@example.com"})
    )

    assert decision.accepted


def test_the_domain_and_the_model_normalise_an_address_the_same_way() -> None:
    """Two definitions of "the same sender" would make the allow-list miss rows."""
    from trip_planner.db.models import normalise_address as model_normalise

    for raw in ["  Owner@Example.COM ", "rezerwacje@airline.example", "X@Y.Z"]:
        assert normalise_address(raw) == model_normalise(raw)


@pytest.mark.parametrize(
    ("given", "expected"),
    [("PASS", "PASS"), ("fail", "FAIL"), (None, VERDICT_UNKNOWN), ("  ", VERDICT_UNKNOWN)],
)
def test_a_verdict_is_stored_in_a_form_that_shows_when_it_was_absent(
    given: str | None, expected: str
) -> None:
    assert normalise_verdict(given) == expected


# --------------------------------------------------------------------------- #
# HTML, reduced to text
# --------------------------------------------------------------------------- #


def test_html_is_reduced_to_its_text_and_the_markup_is_gone() -> None:
    reduced = html_to_text("<p>Rezerwacja <b>SX-9912L</b></p><p>Kwota: 249 PLN</p>")

    assert "SX-9912L" in reduced
    assert "249 PLN" in reduced
    assert "<" not in reduced


def test_script_and_style_contents_are_dropped_rather_than_read_as_text() -> None:
    """Keeping them would put executable-looking prose into a body the owner reads.

    It is not an XSS defence — nothing renders this as markup — it is that a
    minified stylesheet is not text anybody forwarded on purpose.
    """
    reduced = html_to_text(
        "<div>Bilet</div><script>alert('x')</script><style>.a{color:red}</style>"
    )

    assert reduced == "Bilet"


def test_a_tracking_pixel_leaves_nothing_and_is_never_fetched() -> None:
    """There is no markup left to request it from, which is the whole mechanism.

    The absence of a URL in the stored body is what makes "remote content is
    never fetched" structural rather than a rule the renderer has to remember.
    """
    reduced = html_to_text(
        '<p>Do zobaczenia</p><img src="https://tracker.example/pixel.gif?id=42" width="1">'
    )

    assert reduced == "Do zobaczenia"
    assert "tracker.example" not in reduced


def test_block_elements_become_line_breaks_rather_than_one_paragraph() -> None:
    reduced = html_to_text("<ul><li>Lot</li><li>Hotel</li></ul>")

    assert reduced.splitlines() == ["Lot", "Hotel"]


def test_character_references_are_resolved() -> None:
    assert html_to_text("<p>Hotel&nbsp;&amp; Spa</p>").endswith("Spa")


# --------------------------------------------------------------------------- #
# Truncation and the subject
# --------------------------------------------------------------------------- #


def test_a_long_body_is_cut_with_a_marker_and_still_fits_the_column() -> None:
    """The marker's length comes out of the budget, not out of the column's.

    Cutting to exactly the bound and appending afterwards is the off-by-a-marker
    that produces a string the `CHECK` refuses — at ingestion time, on a message
    already accepted, which is the worst moment to discover it.
    """
    cut = truncate_text("x" * (MAX_INBOUND_TEXT_CHARS + 5000))

    assert len(cut) == MAX_INBOUND_TEXT_CHARS
    assert cut.endswith(TRUNCATION_MARKER)


def test_a_body_inside_the_bound_is_returned_untouched() -> None:
    text = "Rezerwacja potwierdzona"
    assert truncate_text(text) == text


def test_a_subject_loses_its_control_characters_and_collapses_its_whitespace() -> None:
    """A newline in a stored value that later reaches a header or a log is a primitive."""
    assert normalise_subject("Re:\r\n  Rezerwacja\tKL-4411 ") == "Re: Rezerwacja KL-4411"


def test_a_very_long_subject_is_cut_to_the_column_bound() -> None:
    assert len(normalise_subject("x" * 5000)) == MAX_INBOUND_SUBJECT_CHARS


def test_an_absent_subject_is_an_empty_string_not_a_none() -> None:
    assert normalise_subject(None) == ""


# --------------------------------------------------------------------------- #
# Selecting content out of a real MIME message
# --------------------------------------------------------------------------- #


def test_a_plain_text_message_keeps_its_text_and_has_no_documents() -> None:
    selected = select_content(build(text="PNR: SX-9912L"))

    assert selected.text == "PNR: SX-9912L"
    assert selected.documents == ()
    assert selected.dropped_documents == 0


def test_the_plain_alternative_is_preferred_over_the_html_one() -> None:
    """What the sender wrote beats what their mail client generated."""
    selected = select_content(
        build(text="PNR: SX-9912L", html="<p>PNR: <b>SX-9912L</b> (HTML)</p>")
    )

    assert selected.text == "PNR: SX-9912L"


def test_an_html_only_message_is_stored_as_reduced_text() -> None:
    selected = select_content(build(html="<p>Rezerwacja <b>SX-9912L</b></p>"))

    assert "SX-9912L" in selected.text
    assert "<" not in selected.text


def test_a_pdf_attachment_is_kept_with_its_derived_type() -> None:
    selected = select_content(
        build(text="W zalaczeniu", documents=[("voucher.pdf", make_pdf(), "application/pdf")])
    )

    assert len(selected.documents) == 1
    document = selected.documents[0]
    assert document.filename == "voucher.pdf"
    assert document.inspected.content_type == "application/pdf"
    assert selected.dropped_documents == 0


def test_the_declared_content_type_is_ignored_in_favour_of_the_bytes() -> None:
    """`ticket.pdf` whose bytes are a JPEG is a JPEG, exactly as for a browser upload."""
    selected = select_content(
        build(text="", documents=[("ticket.pdf", make_jpeg(), "application/pdf")])
    )

    assert selected.documents[0].inspected.content_type == "image/jpeg"


@pytest.mark.parametrize(
    ("filename", "data", "declared"),
    [
        ("plan.ics", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", "text/calendar"),
        ("bilet.zip", b"PK\x03\x04nonsense", "application/zip"),
        ("payload.svg", b"<svg onload=alert(1)></svg>", "image/svg+xml"),
    ],
)
def test_an_unsupported_part_is_dropped_and_counted_never_stored(
    filename: str, data: bytes, declared: str
) -> None:
    """And it is never a reason to reject the whole message — the text still lands.

    The `.ics` case is the one the spec names: a calendar invite rides along with
    most airline confirmations, and losing the confirmation because of it would
    be the feature failing at the thing it exists for.
    """
    selected = select_content(
        build(text="Twoj lot", documents=[(filename, data, declared)])
    )

    assert selected.text == "Twoj lot"
    assert selected.documents == ()
    assert selected.dropped_documents == 1


def test_an_oversized_part_is_dropped_while_the_text_survives() -> None:
    """A message is never lost because a document was too big."""
    from trip_planner.domain.uploads import MAX_ATTACHMENT_BYTES

    oversized = make_pdf() + b"0" * MAX_ATTACHMENT_BYTES
    selected = select_content(
        build(text="Duzy zalacznik", documents=[("huge.pdf", oversized, "application/pdf")])
    )

    assert selected.text == "Duzy zalacznik"
    assert selected.documents == ()
    assert selected.dropped_documents == 1


def test_a_message_with_eleven_documents_keeps_ten_and_counts_the_rest() -> None:
    documents = [(f"voucher-{n}.pdf", make_pdf(), "application/pdf") for n in range(11)]
    selected = select_content(build(text="Komplet", documents=documents))

    assert len(selected.documents) == MAX_INBOUND_DOCUMENTS
    assert selected.dropped_documents == 11 - MAX_INBOUND_DOCUMENTS


def test_a_forty_megabyte_message_still_yields_its_text() -> None:
    """The per-part cap refuses the excess; nothing about the size loses the body."""
    selected = select_content(
        build(
            text="Rezerwacja",
            documents=[("big.pdf", make_pdf() + b"0" * (40 * 1024 * 1024), "application/pdf")],
        )
    )

    assert selected.text == "Rezerwacja"
    assert selected.dropped_documents == 1


def test_a_message_with_no_text_and_one_pdf_stores_the_document_and_an_empty_body() -> None:
    """The case the "read this document" action exists for, from Phase 4."""
    selected = select_content(
        build(text="", documents=[("bilet.pdf", make_pdf(), "application/pdf")])
    )

    assert selected.text == ""
    assert len(selected.documents) == 1


def test_a_document_with_a_hostile_filename_is_normalised_before_storage() -> None:
    """Same rule as a browser upload — the name is display metadata and nothing else."""
    selected = select_content(
        build(text="", documents=[('../../etc/passwd.png', make_png(), "image/png")])
    )

    assert selected.documents[0].filename == "passwd.png"


def test_a_document_with_no_filename_gets_one_generated_from_its_detected_type() -> None:
    message = EmailMessage()
    message["From"] = OWNER
    message["Subject"] = "Bez nazwy"
    message.set_content("")
    message.add_attachment(make_png(), maintype="image", subtype="png")

    selected = select_content(message.as_bytes())

    assert selected.documents[0].filename == "image.png"


def test_a_body_part_marked_as_an_attachment_is_treated_as_a_document_candidate() -> None:
    """A `text/plain` part explicitly dispositioned as an attachment is not the body.

    It is then dropped like any other unsupported type, which is right: a
    forwarded `.txt` is not one of the three formats D16 fixes.
    """
    message = EmailMessage()
    message["From"] = OWNER
    message["Subject"] = "Zalacznik tekstowy"
    message.set_content("To jest tresc")
    message.add_attachment(b"notatka", maintype="text", subtype="plain", filename="notes.txt")

    selected = select_content(message.as_bytes())

    assert selected.text == "To jest tresc"
    assert selected.documents == ()
    assert selected.dropped_documents == 1


def test_bytes_that_are_not_really_mime_become_a_body_rather_than_an_exception() -> None:
    """A message this broken still arrived, and losing it silently is the worse failure.

    `email.message_from_bytes` is deliberately lenient and reads headerless
    garbage as a `text/plain` body, so the honest outcome is a message whose text
    is what arrived — visible, deletable, and carrying no documents — rather than
    an ingestion that raises and retries forever.
    """
    selected = select_content(b"\x00\xff not mime at all")

    assert "not mime at all" in selected.text
    assert selected.documents == ()
    assert selected.dropped_documents == 0


def test_a_very_long_body_is_truncated_on_the_way_out_of_selection() -> None:
    selected = select_content(build(text="x" * (MAX_INBOUND_TEXT_CHARS + 100)))

    assert len(selected.text) <= MAX_INBOUND_TEXT_CHARS
    assert selected.text.endswith(TRUNCATION_MARKER)
