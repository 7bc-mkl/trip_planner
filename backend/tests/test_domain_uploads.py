"""The upload validator, over a corpus built in this file rather than committed.

Every fixture is constructed as `bytes` here on purpose. A repository holding a
handful of binary attachment fixtures is a repository where nobody can review a
change to one, and where "the malicious sample" is a real file sitting on
contributors' disks. Constructing them makes each case's *shape* the readable
part: what makes the truncated PDF truncated is one visible line.
"""

from __future__ import annotations

import struct
import sys
import tomllib
import zlib
from pathlib import Path

import pytest

from trip_planner.domain.uploads import (
    ATTACHMENT_CONTENT_TYPES,
    MAX_FILENAME_CHARS,
    MAX_PIXELS,
    InspectedUpload,
    UploadRejection,
    inspect_upload,
    jpeg_dimensions,
    normalise_filename,
    png_dimensions,
    sniff_type,
    within_pixel_bound,
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------- #
# The corpus
# --------------------------------------------------------------------------- #


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        len(payload).to_bytes(4, "big")
        + kind
        + payload
        + zlib.crc32(kind + payload).to_bytes(4, "big")
    )


def make_png(width: int = 2, height: int = 2, *, break_ihdr_crc: bool = False) -> bytes:
    """A minimal RGB PNG whose `IHDR` declares `width` × `height`.

    The `IDAT` raster is capped at 4 × 4 regardless, so that a fixture declaring
    60 000 × 60 000 stays a few hundred bytes — which is precisely the shape of
    the pixel bomb this corpus exists to refuse, and the reason the validator
    reads the declared dimensions instead of decoding anything.
    """
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    if break_ihdr_crc:
        ihdr = ihdr[:-4] + b"\xde\xad\xbe\xef"
    raster_width, raster_height = min(width, 4), min(height, 4)
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * raster_width for _ in range(raster_height))
    return PNG_SIGNATURE + ihdr + _png_chunk(b"IDAT", zlib.compress(raw)) + _png_chunk(b"IEND", b"")


def make_jpeg(width: int = 4, height: int = 3, *, truncate_eoi: bool = False) -> bytes:
    """A JPEG whose marker chain is real: SOI, APP0, SOF0, SOS, EOI."""
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = (
        b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + bytes([8])
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + bytes([3])
        + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    )
    sos = b"\xff\xda" + (12).to_bytes(2, "big") + b"\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00"
    body = b"\xff\xd8" + app0 + sof0 + sos + b"\x2a" * 32
    return body if truncate_eoi else body + b"\xff\xd9"


def make_pdf(*, version: bytes = b"1.4", with_eof: bool = True) -> bytes:
    """A one-page PDF: header, four objects, an xref table and a trailer."""
    body = (
        b"%PDF-" + version + b"\n%\xe2\xe3\xcf\xd3\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] >>\nendobj\n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\n"
    )
    return body + b"startxref\n0\n%%EOF\n" if with_eof else body


HTML_PAGE = b"<!DOCTYPE html>\n<html><body><script>alert(1)</script></body></html>\n"
SVG_IMAGE = (
    b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg">'
    b"<script>alert(1)</script></svg>\n"
)
# A ZIP local-file header — what a `.pkpass` actually is.
PKPASS_ZIP = b"PK\x03\x04\x14\x00\x00\x00\x08\x00" + b"\x00" * 20 + b"pass.json"


# --------------------------------------------------------------------------- #
# Sniffing: the bytes decide, the extension never does
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (make_pdf(), "application/pdf"),
        (make_jpeg(), "image/jpeg"),
        (make_png(), "image/png"),
    ],
)
def test_sniff_recognises_each_accepted_format(data: bytes, expected: str) -> None:
    assert sniff_type(data) == expected
    assert expected in ATTACHMENT_CONTENT_TYPES


@pytest.mark.parametrize(
    "data",
    [HTML_PAGE, SVG_IMAGE, PKPASS_ZIP, b"", b"GIF89a", b"plain text", b"RIFF\x00\x00\x00\x00WEBP"],
)
def test_sniff_refuses_everything_else(data: bytes) -> None:
    assert sniff_type(data) is None


def test_sniff_refuses_a_pdf_version_outside_the_accepted_range() -> None:
    assert sniff_type(b"%PDF-9.9\n") is None
    assert sniff_type(b"%PDF-x.y\n") is None


def test_sniff_accepts_the_range_boundaries() -> None:
    assert sniff_type(b"%PDF-1.0\n") == "application/pdf"
    assert sniff_type(b"%PDF-2.0\n") == "application/pdf"


# --------------------------------------------------------------------------- #
# inspect_upload — the corpus the spec's Edge Cases table names
# --------------------------------------------------------------------------- #


def test_a_real_pdf_is_accepted() -> None:
    assert inspect_upload(make_pdf()) == InspectedUpload("application/pdf")


def test_a_real_jpeg_is_accepted_with_its_declared_dimensions() -> None:
    assert inspect_upload(make_jpeg(640, 480)) == InspectedUpload("image/jpeg", 640, 480)


def test_a_real_png_is_accepted_with_its_declared_dimensions() -> None:
    assert inspect_upload(make_png(120, 90)) == InspectedUpload("image/png", 120, 90)


def test_a_jpeg_named_pdf_is_stored_as_a_jpeg() -> None:
    """The extension is never authoritative — the bytes are."""
    result = inspect_upload(make_jpeg())
    assert isinstance(result, InspectedUpload)
    assert result.content_type == "image/jpeg"

    filename = normalise_filename("ticket.pdf", content_type=result.content_type)
    assert filename.display == "ticket.pdf", "the display name is left exactly as the owner sees it"


@pytest.mark.parametrize(
    ("label", "data"),
    [
        ("an html page named photo.jpg", HTML_PAGE),
        ("an svg", SVG_IMAGE),
        ("a pkpass zip", PKPASS_ZIP),
    ],
)
def test_unsupported_formats_are_refused(label: str, data: bytes) -> None:
    assert inspect_upload(data) is UploadRejection.UNSUPPORTED_FILE_TYPE


def test_a_zero_byte_file_is_malformed_not_unsupported() -> None:
    assert inspect_upload(b"") is UploadRejection.MALFORMED_UPLOAD


def test_a_truncated_pdf_with_no_eof_marker_is_refused() -> None:
    assert inspect_upload(make_pdf(with_eof=False)) is UploadRejection.MALFORMED_UPLOAD


def test_an_eof_marker_outside_the_last_1024_bytes_does_not_count() -> None:
    padded = make_pdf() + b" " * 2048
    assert inspect_upload(padded) is UploadRejection.MALFORMED_UPLOAD


def test_a_pdf_shorter_than_100_bytes_is_refused() -> None:
    assert inspect_upload(b"%PDF-1.4\n%%EOF\n") is UploadRejection.MALFORMED_UPLOAD


def test_a_jpeg_without_its_end_of_image_marker_is_refused() -> None:
    assert inspect_upload(make_jpeg(truncate_eoi=True)) is UploadRejection.MALFORMED_UPLOAD


def test_a_jpeg_with_no_frame_header_is_refused() -> None:
    assert inspect_upload(b"\xff\xd8\xff\xd9") is UploadRejection.MALFORMED_UPLOAD


def test_a_png_whose_ihdr_crc_does_not_verify_is_refused() -> None:
    assert inspect_upload(make_png(break_ihdr_crc=True)) is UploadRejection.MALFORMED_UPLOAD


def test_a_png_whose_first_chunk_is_not_ihdr_is_refused() -> None:
    not_ihdr = PNG_SIGNATURE + _png_chunk(b"tEXt", b"a" * 13) + _png_chunk(b"IEND", b"")
    assert inspect_upload(not_ihdr) is UploadRejection.MALFORMED_UPLOAD


def test_a_png_header_alone_is_refused() -> None:
    assert inspect_upload(PNG_SIGNATURE) is UploadRejection.MALFORMED_UPLOAD


# --------------------------------------------------------------------------- #
# The pixel bound — protecting the browser, which is the only decoder
# --------------------------------------------------------------------------- #


def test_a_png_claiming_60000_by_60000_is_refused_as_unsupported() -> None:
    bomb = make_png(60_000, 60_000)
    assert png_dimensions(bomb) == (60_000, 60_000)
    assert inspect_upload(bomb) is UploadRejection.UNSUPPORTED_FILE_TYPE


def test_a_jpeg_claiming_60000_by_60000_is_refused_as_unsupported() -> None:
    bomb = make_jpeg(60_000, 60_000)
    assert jpeg_dimensions(bomb) == (60_000, 60_000)
    assert inspect_upload(bomb) is UploadRejection.UNSUPPORTED_FILE_TYPE


def test_the_pixel_bound_sits_exactly_where_the_spec_puts_it() -> None:
    assert MAX_PIXELS == 25_000_000
    assert within_pixel_bound(5_000, 5_000)
    assert not within_pixel_bound(5_000, 5_001)
    # Comfortably above any phone camera: 48 MPx sensors output ~8 000 × 6 000.
    assert within_pixel_bound(8_000, 3_000)


def test_a_phone_sized_photograph_is_not_caught_by_the_bound() -> None:
    assert isinstance(inspect_upload(make_png(4_032, 3_024)), InspectedUpload)


# --------------------------------------------------------------------------- #
# Filenames — the six numbered steps
# --------------------------------------------------------------------------- #


def test_path_traversal_reduces_to_a_basename() -> None:
    assert normalise_filename("../../etc/passwd").display == "passwd"
    assert normalise_filename("..\\..\\windows\\win.ini").display == "win.ini"
    assert normalise_filename("/absolute/path/voucher.pdf").display == "voucher.pdf"


def test_a_newline_is_removed_because_it_is_a_header_injection_primitive() -> None:
    result = normalise_filename("ticket\r\nX-Injected: 1\t.pdf")
    assert "\r" not in result.display
    assert "\n" not in result.display
    assert "\t" not in result.display
    assert result.display == "ticketX-Injected: 1.pdf"
    assert result.ascii_fallback == "ticketX-Injected__1.pdf"


def test_four_thousand_emoji_truncate_on_a_character_boundary() -> None:
    result = normalise_filename("🧳" * 4_000)
    assert len(result.display) == MAX_FILENAME_CHARS
    assert result.display == "🧳" * MAX_FILENAME_CHARS
    assert result.ascii_fallback == "_" * MAX_FILENAME_CHARS


@pytest.mark.parametrize("raw", ["", "...", ".", "   ", "/", "..\\"])
def test_a_name_that_normalises_to_nothing_is_generated_from_the_detected_type(raw: str) -> None:
    assert normalise_filename(raw, content_type="application/pdf").display == "attachment.pdf"
    assert normalise_filename(raw, content_type="image/jpeg").display == "image.jpg"
    assert normalise_filename(raw, content_type="image/png").display == "image.png"


def test_the_ascii_fallback_cannot_close_the_content_disposition_quote() -> None:
    """Step 6, and the reason it is not redundant with step 3."""
    result = normalise_filename('a";x=".pdf')
    assert result.display == 'a";x=".pdf', "the displayed name is not mangled"
    assert result.ascii_fallback == "a__x__.pdf"
    assert '"' not in result.ascii_fallback
    assert "\\" not in result.ascii_fallback

    header = f'attachment; filename="{result.ascii_fallback}"'
    assert header == 'attachment; filename="a__x__.pdf"'
    assert header.count('"') == 2, "exactly the two quotes we wrote"


def test_the_ascii_fallback_is_restricted_to_the_spec_s_character_class() -> None:
    result = normalise_filename("Bilet — Kraków (2 osoby)!.pdf")
    assert result.display == "Bilet — Kraków (2 osoby)!.pdf"
    assert set(result.ascii_fallback) <= set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    )


def test_the_display_form_is_nfc_normalised() -> None:
    """Two spellings of the same accented name must become one string."""
    decomposed = "Kraków.pdf"  # "o" plus COMBINING ACUTE ACCENT
    assert normalise_filename(decomposed).display == "Kraków.pdf"


def test_invalid_utf8_is_replaced_rather_than_raising() -> None:
    result = normalise_filename(b"bilet\xff\xfe.pdf")
    assert result.display.endswith(".pdf")
    assert result.ascii_fallback.endswith(".pdf")


def test_an_ordinary_name_survives_untouched() -> None:
    result = normalise_filename("boarding-pass_2026.pdf")
    assert result.display == "boarding-pass_2026.pdf"
    assert result.ascii_fallback == "boarding-pass_2026.pdf"


# --------------------------------------------------------------------------- #
# The decision that has to stay decided
# --------------------------------------------------------------------------- #

_IMAGE_LIBRARIES = ("pillow", "pil", "wand", "opencv", "opencv-python", "pyvips", "pillow-simd")


def test_no_image_library_is_a_declared_backend_dependency() -> None:
    """Pillow and friends are refused by design, not by omission.

    `Image.open()` / `verify()` is a decoder run over attacker-controlled bytes.
    Nothing in this feature needs one: reading two integers out of a PNG `IHDR`
    is not a decode. If a future change genuinely needs server-side decoding it
    has to argue with the spec's Security section and delete this test — which
    is the point of the test existing.
    """
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    declared: list[str] = list(config["project"].get("dependencies", []))
    for group in config.get("dependency-groups", {}).values():
        declared.extend(entry for entry in group if isinstance(entry, str))

    for requirement in declared:
        name = requirement.split(";")[0].split("[")[0]
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", " "):
            name = name.split(separator)[0]
        assert name.strip().lower() not in _IMAGE_LIBRARIES, (
            f"{requirement!r} is an image library; the server must never decode an upload"
        )


def test_no_image_library_is_importable_from_the_module() -> None:
    """A belt-and-braces check that nothing pulled one in transitively."""
    import trip_planner.domain.uploads  # noqa: F401

    assert "PIL" not in sys.modules
    assert "cv2" not in sys.modules
