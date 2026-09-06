"""What an uploaded file is, decided from its bytes and from nothing else.

This module is where the attachment feature's security decisions live, so that
"is this file acceptable" has exactly one implementation and can be exercised
without a server, a database or a network. Everything here is a pure function
over `bytes` and plain values (AGENTS.md: pure business rules go in `domain/`).

Two rules shape the whole module, both from the spec's Security section:

- **The client is never asked what the file is.** The multipart part's
  `Content-Type` header and the filename's extension are discarded *before* any
  decision is taken. `ticket.pdf` whose bytes are a JPEG is a JPEG named
  `ticket.pdf`; `photo.jpg` whose bytes are an HTML page is refused.
- **No image library runs on the server.** Pillow was the obvious alternative
  and it lost: `Image.open()` plus `verify()` is a *decoder* touching
  attacker-controlled bytes, historically the richest CVE surface in this area,
  and it would buy something this product does not need — no thumbnail, no
  re-encode, no EXIF strip is in scope. Reading two 32-bit integers out of a PNG
  `IHDR` is not a decode, and neither is walking a JPEG's marker chain. Adding
  pillow/wand/opencv/pyvips to `backend/pyproject.toml` would silently undo that
  decision, so `tests/test_domain_uploads.py` asserts none of them is declared.

The structural checks are deliberately shallow. They establish that the bytes
are plausibly the format their header claims and that the upload is not
truncated. They are *not* a validity proof, and the module says so where a
reader might otherwise be tempted to lean on one.

Rejections are returned, not raised: this module predates the `ErrorCode`
members the upload endpoints will map them to, and a pure function that returns
its verdict stays testable without the HTTP layer. `UploadRejection`'s values
are the wire codes those endpoints answer with, so the mapping is an identity.
"""

from __future__ import annotations

import unicodedata
import zlib
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "ATTACHMENT_CONTENT_TYPES",
    "MAX_ATTACHMENT_BYTES",
    "MAX_FILENAME_CHARS",
    "MAX_PIXELS",
    "SNIFF_HEAD_BYTES",
    "InspectedUpload",
    "NormalisedFilename",
    "UploadRejection",
    "inspect_upload",
    "jpeg_dimensions",
    "normalise_filename",
    "png_dimensions",
    "sniff_type",
    "within_pixel_bound",
]

#: The only three types the bytes of an upload are allowed to turn out to be.
#:
#: This is the *derived* type — what sniffing the file's own header concluded —
#: never the `Content-Type` the client claimed. It lives here, in the module that
#: derives it, and `db/models.py` imports it for the `attachment.content_type`
#: `CHECK`, so "what we accept" and "what we can store" are one fact rather than
#: two that drift. The dependency runs `db` → `domain`; the reverse would drag
#: SQLAlchemy into a module whose whole point is that it needs nothing.
#:
#: Everything else is refused, each for its own reason (spec, Security):
#: SVG executes script in the rendering origin; PKPASS is a ZIP whose identity
#: could only be established by unzipping attacker-controlled archive bytes;
#: HEIC/WEBP/GIF/TIFF are further parser families for formats no ticket vendor
#: issues; HTML and text are the stored-XSS vector a screenshot replaces.
ATTACHMENT_CONTENT_TYPES = ("application/pdf", "image/jpeg", "image/png")

#: 10 MiB, the per-file cap (A4).
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

#: The display filename's bound, in characters — not bytes, so the truncation
#: cannot land inside a character.
MAX_FILENAME_CHARS = 200

#: The bound on an image's *declared* pixel count.
#:
#: A decompression bomb is a small file that expands catastrophically **when
#: decoded**. This server never decodes, so the bound is not protecting the
#: server: it protects the **browser** that will, which is the only decoder in
#: the system. 25 MPx is roughly 100 MB of decoded raster and is comfortably
#: above any phone camera, so it refuses bombs without refusing photographs. A
#: file whose header claims 60 000 × 60 000 — 3.6 gigapixels — is refused.
MAX_PIXELS = 25_000_000

#: How many leading bytes `sniff_type` needs. The longest signature it looks at
#: is the PDF's `%PDF-` plus its two version digits and the separating dot.
SNIFF_HEAD_BYTES = 8

_PDF_MAGIC = b"%PDF-"
_PDF_EOF_MARKER = b"%%EOF"
_PDF_EOF_WINDOW = 1024
_PDF_MIN_BYTES = 100
_PDF_MIN_VERSION = (1, 0)
_PDF_MAX_VERSION = (2, 0)

_JPEG_MAGIC = b"\xff\xd8\xff"
_JPEG_EOI = b"\xff\xd9"
#: `SOF0`–`SOF3` — the baseline and progressive frame headers that carry the
#: declared dimensions. `SOF4`+ are other coding processes, and `0xC4`/`0xC8`/
#: `0xCC` are not frame headers at all despite sitting in the same numeric range.
_JPEG_SOF_MARKERS = frozenset({0xC0, 0xC1, 0xC2, 0xC3})
#: Markers that carry no length field: TEM, RSTn and a stray SOI.
_JPEG_STANDALONE_MARKERS = frozenset({0x01, 0xD8}) | frozenset(range(0xD0, 0xD8))

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PNG_IHDR_LENGTH = 13
#: signature (8) + chunk length (4) + chunk type (4) + IHDR payload (13) + CRC (4)
_PNG_IHDR_TOTAL = 8 + 4 + 4 + _PNG_IHDR_LENGTH + 4

_FILENAME_SAFE_ASCII = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)
_GENERATED_NAMES = {
    "application/pdf": "attachment.pdf",
    "image/jpeg": "image.jpg",
    "image/png": "image.png",
}
_FALLBACK_NAME = "attachment"


class UploadRejection(StrEnum):
    """Why an upload was refused. The value is the endpoint's error code."""

    #: The bytes are not one of the three accepted formats, or an image's header
    #: declares more pixels than any browser should be asked to decode.
    UNSUPPORTED_FILE_TYPE = "unsupported_file_type"
    #: The bytes claim an accepted format but do not hold together as one —
    #: empty, truncated, or structurally inconsistent.
    MALFORMED_UPLOAD = "malformed_upload"


@dataclass(frozen=True, slots=True)
class InspectedUpload:
    """An accepted upload: its derived type and, for images, its dimensions."""

    content_type: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True, slots=True)
class NormalisedFilename:
    """The two forms a filename has to exist in, and they are not the same.

    `display` is what the UI shows and what `filename*` carries percent-encoded.
    `ascii_fallback` is the only form allowed into the `filename="…"` parameter
    of a `Content-Disposition` header — see `normalise_filename`, step 6.
    """

    display: str
    ascii_fallback: str


def sniff_type(head: bytes) -> str | None:
    """The content type derived from the leading bytes, or `None` if unknown.

    The request's `Content-Type` part header and the filename extension are
    **never** consulted — not here and not by any caller. This function is the
    only place in the application that decides what a file is.

    `head` may be the whole file or just its first `SNIFF_HEAD_BYTES` bytes;
    sniffing alone proves nothing beyond the signature, so every accepted type
    is then put through `inspect_upload`'s structural check.
    """
    if head.startswith(_PNG_MAGIC):
        return "image/png"
    if head.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if head.startswith(_PDF_MAGIC) and _pdf_version(head) is not None:
        return "application/pdf"
    return None


def _pdf_version(head: bytes) -> tuple[int, int] | None:
    """The `M.m` version digits after `%PDF-`, when they are in `1.0`–`2.0`.

    A version outside that range is not a PDF this application has any reason to
    accept, and the check costs nothing — it is two ASCII digits, still not a
    parse.
    """
    version = head[len(_PDF_MAGIC) : len(_PDF_MAGIC) + 3]
    if len(version) != 3 or version[1:2] != b"." or not version[0:1].isdigit():
        return None
    if not version[2:3].isdigit():
        return None
    parsed = (version[0] - 0x30, version[2] - 0x30)
    if not _PDF_MIN_VERSION <= parsed <= _PDF_MAX_VERSION:
        return None
    return parsed


def _check_pdf(data: bytes) -> UploadRejection | None:
    """Structural check for a PDF. **The document is never parsed.**

    No object graph is walked, no cross-reference table is followed and no
    stream is decoded, so no PDF-parser CVE is reachable from an upload. What is
    checked is only that the file is long enough to be a document and that it
    carries an `%%EOF` marker in its last 1024 bytes.

    That `%%EOF` check is an **integrity heuristic, not a security control**. It
    catches a browser that dropped the connection half way through a voucher —
    the truncated-upload case the spec names — and nothing else. Any attacker
    can append five bytes. It must never be leaned on as though it resisted one.
    """
    if len(data) < _PDF_MIN_BYTES:
        return UploadRejection.MALFORMED_UPLOAD
    if _PDF_EOF_MARKER not in data[-_PDF_EOF_WINDOW:]:
        return UploadRejection.MALFORMED_UPLOAD
    return None


def jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """`(width, height)` as the first `SOF0`–`SOF3` frame header declares them.

    The marker chain is walked with plain stdlib code: each segment announces its
    own length, so reaching the frame header is arithmetic over two-byte
    integers rather than decoding. Nothing is decompressed and no scan data is
    read. Returns `None` when the chain does not hold together or ends before a
    frame header — a JPEG whose dimensions cannot be found is malformed.
    """
    if not data.startswith(_JPEG_MAGIC):
        return None

    pos = 2
    end = len(data)
    while pos + 1 < end:
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker == 0xFF:
            # A fill byte. The real marker is the next one along.
            pos += 1
            continue
        pos += 2
        if marker in _JPEG_STANDALONE_MARKERS:
            continue
        if marker in (0xD9, 0xDA):
            # EOI, or the start of the entropy-coded scan: past this point there
            # is no frame header left to find, and reading scan data is decoding.
            return None
        if pos + 2 > end:
            return None
        length = int.from_bytes(data[pos : pos + 2], "big")
        if length < 2:
            return None
        if marker in _JPEG_SOF_MARKERS:
            # Payload: precision (1), height (2), width (2) — five bytes that
            # follow the two-byte length. Height comes first; the order is the
            # single easiest thing to get backwards here.
            if length < 7 or pos + 7 > end:
                return None
            height = int.from_bytes(data[pos + 3 : pos + 5], "big")
            width = int.from_bytes(data[pos + 5 : pos + 7], "big")
            return (width, height)
        pos += length
    return None


def _check_jpeg(data: bytes) -> InspectedUpload | UploadRejection:
    """Structural check for a JPEG: a readable frame header and a real EOI.

    The trailing `FF D9` is the same class of integrity heuristic as the PDF's
    `%%EOF` — it catches the interrupted upload, and it resists nobody.
    """
    dimensions = jpeg_dimensions(data)
    if dimensions is None:
        return UploadRejection.MALFORMED_UPLOAD
    if not data.endswith(_JPEG_EOI):
        return UploadRejection.MALFORMED_UPLOAD
    rejection = _check_dimensions(*dimensions)
    if rejection is not None:
        return rejection
    width, height = dimensions
    return InspectedUpload("image/jpeg", width=width, height=height)


def _check_dimensions(width: int, height: int) -> UploadRejection | None:
    """The dimension rules both image formats answer, in one place.

    Hoisted out of `_check_png`, where the zero check used to live alone: a JPEG
    declaring `0 × 0` passed `within_pixel_bound` — `0 * h <= MAX_PIXELS` is true
    — and was stored, where it renders as a broken `<img>` in the gallery and the
    lightbox that the equivalent PNG was correctly refused for. One rule cannot
    have two answers depending on which branch reaches it, so neither branch
    states it any more.

    A zero dimension is `malformed_upload`, not `unsupported_file_type`: the file
    claims a format this application accepts and then contradicts itself, which
    is the same class of fact as a JPEG missing its EOI.
    """
    if width == 0 or height == 0:
        return UploadRejection.MALFORMED_UPLOAD
    if not within_pixel_bound(width, height):
        return UploadRejection.UNSUPPORTED_FILE_TYPE
    return None


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    """`(width, height)` out of the `IHDR` chunk, or `None` if it is not there.

    Two 32-bit big-endian integers at fixed offsets. Nothing is inflated: the
    `IDAT` chunks — the only attacker-controlled *compressed* bytes in a PNG —
    are never touched.
    """
    if not data.startswith(_PNG_MAGIC) or len(data) < _PNG_IHDR_TOTAL:
        return None
    if int.from_bytes(data[8:12], "big") != _PNG_IHDR_LENGTH:
        return None
    if data[12:16] != b"IHDR":
        return None
    return (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))


def _check_png(data: bytes) -> InspectedUpload | UploadRejection:
    """Structural check for a PNG: a first `IHDR` chunk whose CRC verifies.

    The CRC is the format's own integrity field, so verifying it costs one
    `zlib.crc32` over 17 bytes and catches a truncated or corrupted header
    before the dimensions read out of it are believed. Like every other check
    here it is an integrity check: a CRC is trivially recomputed by anyone
    editing the file on purpose.
    """
    dimensions = png_dimensions(data)
    if dimensions is None:
        return UploadRejection.MALFORMED_UPLOAD

    # The CRC covers the chunk type and its payload, never the length field.
    if zlib.crc32(data[12 : 16 + _PNG_IHDR_LENGTH]) != int.from_bytes(
        data[16 + _PNG_IHDR_LENGTH : _PNG_IHDR_TOTAL], "big"
    ):
        return UploadRejection.MALFORMED_UPLOAD

    rejection = _check_dimensions(*dimensions)
    if rejection is not None:
        return rejection
    width, height = dimensions
    return InspectedUpload("image/png", width=width, height=height)


def within_pixel_bound(width: int, height: int) -> bool:
    """Whether the *declared* pixel count is inside `MAX_PIXELS`.

    Declared, because nothing is decoded — the header's own claim is the whole
    input, which is exactly why the bound is worth applying: a bomb's header
    tells the truth about how big it will get, and the browser would believe it.
    """
    return width * height <= MAX_PIXELS


def inspect_upload(data: bytes) -> InspectedUpload | UploadRejection:
    """Derive the type from the bytes and put it through its structural check.

    The single entry point the upload endpoints call. Returns an
    `InspectedUpload` carrying the type to store — always the derived one — or
    an `UploadRejection` naming the error code to answer with.

    A zero-byte file is `malformed_upload` rather than `unsupported_file_type`:
    nothing was uploaded, which is a broken request rather than a refused
    format, and the spec's Edge Cases table fixes that answer.
    """
    if not data:
        return UploadRejection.MALFORMED_UPLOAD

    content_type = sniff_type(data[:SNIFF_HEAD_BYTES])
    if content_type is None:
        return UploadRejection.UNSUPPORTED_FILE_TYPE

    if content_type == "application/pdf":
        rejection = _check_pdf(data)
        return rejection if rejection is not None else InspectedUpload("application/pdf")
    if content_type == "image/jpeg":
        return _check_jpeg(data)
    return _check_png(data)


def normalise_filename(raw: str | bytes, *, content_type: str | None = None) -> NormalisedFilename:
    """The client's filename reduced to something safe to show and to send back.

    The filename is **display metadata and nothing else**, and it is
    structurally incapable of being anything else: the storage identity is the
    attachment's UUID primary key, so path traversal is unrepresentable rather
    than filtered. What this function defends is the two places the string is
    echoed — HTML, and a response header.

    The spec's six numbered steps, in order:

    1. decode as UTF-8 replacing invalid sequences, then NFC-normalise, so two
       spellings of the same accented name are one string;
    2. reduce to the basename — everything up to and including the last `/` or
       `\\` is discarded, which is what makes `../../etc/passwd` display as
       `passwd`;
    3. remove control characters, `\\r`, `\\n` and `\\t` — a newline in a filename
       is a response-header injection primitive;
    4. truncate to `MAX_FILENAME_CHARS` characters, on a character boundary
       (Python slices code points, so 4 000 emoji become 200 emoji, never half
       of one);
    5. if what is left is empty or only dots, replace it with a name generated
       from the **detected** type — never from the extension the client sent;
    6. derive a **separate** ASCII fallback for `Content-Disposition` by
       replacing every character outside `[A-Za-z0-9._-]` with `_`.

    Step 6 is not cosmetic and it is not redundant with step 3. The header's
    `filename="…"` parameter is a quoted string, so a name like `a";x=".pdf`
    would close the quote and inject a parameter — and `"` and `\\` are not
    control characters, so step 3 does not touch them. The UTF-8 form goes in
    `filename*`, where RFC 5987 percent-encodes it; the raw string never reaches
    a header in either form.
    """
    # 1 — decode, replacing anything that is not valid UTF-8, then NFC.
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    text = unicodedata.normalize("NFC", text)

    # 2 — basename. Both separators, because the client may be any platform.
    text = text.replace("\\", "/").rsplit("/", 1)[-1]

    # 3 — control characters out. `Cc` covers \r, \n and \t; `Cf` covers the
    # invisible formatting characters (RTL overrides and friends) that make a
    # displayed name lie about its own extension.
    text = "".join(char for char in text if unicodedata.category(char) not in ("Cc", "Cf"))

    # 4 — truncate on a character boundary.
    text = text[:MAX_FILENAME_CHARS].strip()

    # 5 — a generated name when nothing usable survived.
    if not text or set(text) <= {"."}:
        text = _GENERATED_NAMES.get(content_type or "", _FALLBACK_NAME)

    # 6 — the separate, header-safe ASCII form.
    ascii_fallback = "".join(char if char in _FILENAME_SAFE_ASCII else "_" for char in text)

    return NormalisedFilename(display=text, ascii_fallback=ascii_fallback)
