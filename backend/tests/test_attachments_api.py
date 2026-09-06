"""The attachment endpoints: the two uploads and their check order, then the reads.

The corpus is imported from `tests/test_domain_uploads.py` rather than copied:
the validator's refusals and the endpoint's status codes must be answers to the
same files, and two corpora would drift into testing two different things.

Three classes here are not ordinary endpoint tests and are worth reading as
security assertions:

- `TestNothingTouchesTheFilesystem` fails if any temporary-file object is
  constructed while an upload larger than Starlette's 1 MB spool threshold is
  handled — the exact thing a `file: UploadFile` parameter would do.
- `TestTheOrderOfChecks` proves the rate window is consulted *before* the body is
  read, and that the byte counter refuses a body whose length was never declared.
- `TestTheDerivedTypeWins` proves the stored type comes from the bytes, with a
  request that lies in both places a client can lie.

The read half adds three more of the same kind: `TestServingTheContent` asserts
**every** header of the spec's serving set verbatim for **every** accepted type —
the images included, which is what proves `Content-Disposition: attachment` is
universal — and that a hostile filename reaches both `Content-Disposition`
parameters safely; `TestAnotherTripsAttachment` pins the `404` on all three
routes; and `TestThereIsNoPatch` asserts the absence of the route whose existence
would invalidate the strong `ETag`.
"""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from urllib.parse import quote

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession

from tests.test_domain_uploads import (
    HTML_PAGE,
    PKPASS_ZIP,
    SVG_IMAGE,
    make_jpeg,
    make_pdf,
    make_png,
)
from tests.test_items_api import DAY, add_item
from tests.test_trips_api import TRIPS, create, error_code
from trip_planner.api import attachments as attachments_module
from trip_planner.api.attachments import MAX_BODY_BYTES, MAX_PARTS, parse_single_file_part
from trip_planner.db.models import Attachment, AttachmentBlob, Owner, Trip
from trip_planner.domain.uploads import MAX_ATTACHMENT_BYTES
from trip_planner.errors import ApiError, ErrorCode
from trip_planner.security.quota import UploadQuota, get_upload_quota, set_upload_quota

BOUNDARY = "----trip-planner-test-boundary"
MULTIPART_CONTENT_TYPE = f"multipart/form-data; boundary={BOUNDARY}"


@pytest.fixture
def trip(signed_in_client: TestClient) -> dict:
    return create(signed_in_client)


def day_attachments_url(trip: dict, day: str = DAY) -> str:
    return f"{TRIPS}/{trip['id']}/days/{day}/attachments"


def item_attachments_url(trip: dict, item: dict) -> str:
    return f"{TRIPS}/{trip['id']}/items/{item['id']}/attachments"


def upload(
    client: TestClient,
    url: str,
    data: bytes,
    *,
    filename: str = "voucher.pdf",
    content_type: str = "application/pdf",
):
    """One `file` part, built by httpx exactly as the browser's `FormData` would."""
    return client.post(url, files={"file": (filename, data, content_type)})


def multipart_body(parts: list[tuple[str, bytes, str | None]]) -> bytes:
    """A multipart body assembled by hand, for the requests httpx will not build.

    `(name, value, filename)` — a `filename` makes it a file part. Needed for the
    two-`file`-parts case and for the chunked request, neither of which httpx's
    `files=` argument can express.
    """
    chunks: list[bytes] = []
    for name, value, filename in parts:
        disposition = f'form-data; name="{name}"'
        if filename is not None:
            disposition += f'; filename="{filename}"'
        chunks.append(
            f"--{BOUNDARY}\r\nContent-Disposition: {disposition}\r\n\r\n".encode()
            + value
            + b"\r\n"
        )
    chunks.append(f"--{BOUNDARY}--\r\n".encode())
    return b"".join(chunks)


def pdf_of_exactly(size: int) -> bytes:
    """A valid PDF padded to `size` bytes exactly, for testing the cap's edges."""
    base = make_pdf()
    padding = b"%" + b"a" * (size - len(base) - 2)
    padded = base.replace(b"trailer", padding + b"\ntrailer")
    assert len(padded) == size, "the padding arithmetic, not the code under test"
    return padded


def oversized_pdf() -> bytes:
    """A PDF one byte past the per-file cap. Valid, and refused for its size alone."""
    return pdf_of_exactly(MAX_ATTACHMENT_BYTES + 1)


class TestUploadingToADay:
    @pytest.mark.parametrize(
        ("data", "filename", "expected_type"),
        [
            (make_pdf(), "Voucher_Memmo_Alfama.pdf", "application/pdf"),
            (make_jpeg(), "boarding-pass.jpg", "image/jpeg"),
            (make_png(), "screenshot.png", "image/png"),
        ],
    )
    def test_each_accepted_type_is_stored(
        self,
        signed_in_client: TestClient,
        trip: dict,
        data: bytes,
        filename: str,
        expected_type: str,
    ) -> None:
        response = upload(signed_in_client, day_attachments_url(trip), data, filename=filename)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["filename"] == filename
        assert body["content_type"] == expected_type
        assert body["byte_size"] == len(data)
        assert body["item_id"] is None
        assert body["trip_day_id"] is not None

    def test_the_bytes_and_their_digest_are_stored_verbatim(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        """Byte-for-byte: the server never re-encodes, so the digest must match."""
        import hashlib

        data = make_jpeg()
        body = upload(signed_in_client, day_attachments_url(trip), data).json()

        stored = db_session.get(AttachmentBlob, uuid.UUID(body["id"]))
        assert stored is not None
        assert stored.data == data
        assert body["sha256"] == hashlib.sha256(data).hexdigest()

    def test_a_day_outside_the_trip_is_a_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = upload(signed_in_client, day_attachments_url(trip, "2027-01-01"), make_pdf())

        assert response.status_code == 404
        assert error_code(response) == "not_found"


class TestUploadingToAnItem:
    @pytest.mark.parametrize(
        ("data", "expected_type"),
        [
            (make_pdf(), "application/pdf"),
            (make_jpeg(), "image/jpeg"),
            (make_png(), "image/png"),
        ],
    )
    def test_each_accepted_type_is_pinned_to_the_item(
        self, signed_in_client: TestClient, trip: dict, data: bytes, expected_type: str
    ) -> None:
        item = add_item(signed_in_client, trip)

        response = upload(signed_in_client, item_attachments_url(trip, item), data)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["content_type"] == expected_type
        assert body["item_id"] == item["id"]
        assert body["trip_day_id"] is None

    def test_an_item_of_another_trip_is_a_404(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        other = create(signed_in_client, title="Another trip")
        theirs = add_item(signed_in_client, other)

        response = upload(signed_in_client, item_attachments_url(trip, theirs), make_pdf())

        assert response.status_code == 404
        assert error_code(response) == "not_found"


class TestRefusals:
    """1.2's corpus, answered at the endpoint with the codes the spec's table fixes."""

    @pytest.mark.parametrize(
        ("data", "filename", "status", "code"),
        [
            (HTML_PAGE, "photo.jpg", 415, "unsupported_file_type"),
            (SVG_IMAGE, "map.svg", 415, "unsupported_file_type"),
            (PKPASS_ZIP, "boarding.pkpass", 415, "unsupported_file_type"),
            (make_png(width=60_000, height=60_000), "bomb.png", 415, "unsupported_file_type"),
            (make_pdf(with_eof=False), "truncated.pdf", 422, "malformed_upload"),
            (make_jpeg(truncate_eoi=True), "truncated.jpg", 422, "malformed_upload"),
            (b"", "empty.pdf", 422, "malformed_upload"),
        ],
    )
    def test_the_corpus_is_refused_with_its_code(
        self,
        signed_in_client: TestClient,
        trip: dict,
        data: bytes,
        filename: str,
        status: int,
        code: str,
    ) -> None:
        response = upload(signed_in_client, day_attachments_url(trip), data, filename=filename)

        assert response.status_code == status, response.text
        assert error_code(response) == code

    def test_nothing_is_written_when_the_bytes_are_refused(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        upload(signed_in_client, day_attachments_url(trip), HTML_PAGE, filename="x.jpg")

        assert db_session.query(Attachment).count() == 0
        assert db_session.query(AttachmentBlob).count() == 0

    def test_a_file_one_byte_over_the_cap_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = upload(signed_in_client, day_attachments_url(trip), oversized_pdf())

        assert response.status_code == 413
        assert error_code(response) == "attachment_too_large"

    def test_a_file_of_exactly_the_cap_is_stored(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        """The documented limit is inclusive, and the test above it is the first refusal.

        The body carries the multipart envelope as well as the file, so bounding
        the *body* at the per-file cap refused a file of exactly 10 MB while
        quoting 10 MB back at the client — and made
        `ck_attachment_byte_size`'s `byte_size <= 10485760` unreachable by any
        code path. This is the path that reaches it.
        """
        data = pdf_of_exactly(MAX_ATTACHMENT_BYTES)

        response = upload(signed_in_client, day_attachments_url(trip), data)

        assert response.status_code == 201, response.text
        assert response.json()["byte_size"] == MAX_ATTACHMENT_BYTES

        stored = db_session.get(Attachment, uuid.UUID(response.json()["id"]))
        assert stored is not None
        assert stored.byte_size == MAX_ATTACHMENT_BYTES

    def test_a_declared_length_past_the_body_bound_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The pre-read half of the memory control, on the body rather than the file."""
        response = signed_in_client.post(
            day_attachments_url(trip),
            content=b"x" * (MAX_BODY_BYTES + 1),
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 413
        assert error_code(response) == "attachment_too_large"


class TestTheOneFilePartRule:
    def test_two_file_parts_are_malformed(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = multipart_body(
            [("file", make_pdf(), "one.pdf"), ("file", make_jpeg(), "two.jpg")]
        )

        response = signed_in_client.post(
            day_attachments_url(trip),
            content=body,
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 422
        assert error_code(response) == "malformed_upload"

    def test_no_file_part_is_malformed(self, signed_in_client: TestClient, trip: dict) -> None:
        body = multipart_body([("document", make_pdf(), "one.pdf")])

        response = signed_in_client.post(
            day_attachments_url(trip),
            content=body,
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 422
        assert error_code(response) == "malformed_upload"

    def test_an_empty_multipart_body_is_malformed(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(
            day_attachments_url(trip),
            content=multipart_body([]),
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 422
        assert error_code(response) == "malformed_upload"

    def test_a_body_that_is_not_multipart_is_malformed(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = signed_in_client.post(day_attachments_url(trip), json={"file": "hello"})

        assert response.status_code == 422
        assert error_code(response) == "malformed_upload"

    def test_a_field_value_past_the_cap_is_malformed(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Non-file field values are capped at 200 bytes while parsing."""
        body = multipart_body(
            [("file", make_pdf(), "one.pdf"), ("caption", b"x" * 201, None)]
        )

        response = signed_in_client.post(
            day_attachments_url(trip),
            content=body,
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 422
        assert error_code(response) == "malformed_upload"

    def test_a_field_value_within_the_cap_is_ignored_not_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = multipart_body([("file", make_pdf(), "one.pdf"), ("caption", b"x" * 200, None)])

        response = signed_in_client.post(
            day_attachments_url(trip),
            content=body,
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 201, response.text


class TestThePartCountIsBoundedByTheParser:
    """The part count is the parser's limit, not a count taken after it finished.

    `read_body` bounds the *bytes*; nothing bounded the objects built out of
    them. A 10 MB body of empty parts is over a million `_Part`s, each with its
    own `bytearray` — ~145 MB resident before the post-hoc "exactly one `file`
    part" check answered `422`. The measurement that matters is therefore how
    many parts were *built*, not what the request answered: the answer was
    already right.
    """

    def test_far_fewer_parts_are_built_than_the_body_submits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        submitted = 20_000
        body = multipart_body([("x", b"", None)] * submitted)
        built = 0
        real_part = attachments_module._Part

        def counting_part() -> object:
            nonlocal built
            built += 1
            return real_part()

        monkeypatch.setattr(attachments_module, "_Part", counting_part)

        with pytest.raises(ApiError) as raised:
            parse_single_file_part(MULTIPART_CONTENT_TYPE, body)

        assert raised.value.code is ErrorCode.MALFORMED_UPLOAD
        assert built == MAX_PARTS, "the parse must stop at the bound, not run to the end"
        assert built < submitted / 1000

    def test_a_body_of_many_parts_is_malformed_at_the_endpoint(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        body = multipart_body([("file", make_pdf(), "one.pdf")] + [("x", b"", None)] * 20_000)

        response = signed_in_client.post(
            day_attachments_url(trip),
            content=body,
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 422
        assert error_code(response) == "malformed_upload"

    def test_the_bound_leaves_room_for_a_clients_stray_fields(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """`MAX_PARTS` is not "refuse the second part" — a few stray fields still upload."""
        assert MAX_PARTS >= 4
        body = multipart_body(
            [("file", make_pdf(), "one.pdf")] + [(f"f{n}", b"v", None) for n in range(3)]
        )

        response = signed_in_client.post(
            day_attachments_url(trip),
            content=body,
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert response.status_code == 201, response.text


class TestTheDerivedTypeWins:
    def test_the_stored_type_comes_from_the_bytes_not_the_request(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        """A JPEG named `ticket.pdf`, declared `application/pdf`, twice a lie."""
        response = upload(
            signed_in_client,
            day_attachments_url(trip),
            make_jpeg(),
            filename="ticket.pdf",
            content_type="application/pdf",
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["content_type"] == "image/jpeg"
        # The display name is *not* corrected: it is metadata, and rewriting it
        # would be lying to the owner about the file he uploaded.
        assert body["filename"] == "ticket.pdf"

        stored = db_session.get(Attachment, uuid.UUID(body["id"]))
        assert stored is not None
        assert stored.content_type == "image/jpeg"


class TestTheOrderOfChecks:
    """The two properties an `UploadFile` parameter would silently give up."""

    @pytest.fixture
    def no_uploads_allowed(self) -> Iterator[None]:
        previous = get_upload_quota()
        set_upload_quota(UploadQuota(max_uploads_per_rate_window=0))
        yield
        set_upload_quota(previous)

    def test_the_rate_window_is_checked_before_the_body_is_read(
        self, signed_in_client: TestClient, trip: dict, no_uploads_allowed: None
    ) -> None:
        """An oversized body under a full window answers `429`, never `413`.

        `413` would prove the length or the bytes were looked at first, which is
        the ordering the spec calls out as the wrong one: the limiter would be
        refusing to *store* the flood while still *absorbing* it.
        """
        response = upload(signed_in_client, day_attachments_url(trip), oversized_pdf())

        assert response.status_code == 429
        assert error_code(response) == "rate_limited"

    def test_an_undeclared_length_is_still_refused_by_the_counter(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """A chunked request declares no length; the byte counter is the limit."""
        body = multipart_body([("file", oversized_pdf(), "huge.pdf")])

        def stream() -> Iterator[bytes]:
            for start in range(0, len(body), 65536):
                yield body[start : start + 65536]

        response = signed_in_client.post(
            day_attachments_url(trip),
            content=stream(),
            headers={"content-type": MULTIPART_CONTENT_TYPE},
        )

        assert "content-length" not in response.request.headers, (
            "the request must not declare its length, or this asserts the header check"
        )
        assert response.status_code == 413
        assert error_code(response) == "attachment_too_large"


class TestNothingTouchesTheFilesystem:
    def test_no_temporary_file_is_created_for_a_large_upload(
        self,
        signed_in_client: TestClient,
        trip: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Well past Starlette's 1 MB spool threshold, with `tempfile` disarmed.

        Starlette's `UploadFile` rolls its `SpooledTemporaryFile` over to a real
        file on disk past ~1 MB — every real voucher. This uploads 2 MiB with
        every temporary-file constructor replaced by an explosion, so the test
        fails the moment a handler starts spooling instead of buffering.

        `starlette.formparsers` is patched as well as `tempfile`, and not
        redundantly: it binds `SpooledTemporaryFile` by `from tempfile import …`
        at import time, so patching `tempfile` alone would leave the one path
        that actually matters — `request.form()` — untouched.
        """
        import starlette.formparsers

        def explode(*args: object, **kwargs: object) -> object:
            raise AssertionError("an upload created a temporary file")

        for name in ("SpooledTemporaryFile", "NamedTemporaryFile", "TemporaryFile", "mkstemp"):
            monkeypatch.setattr(tempfile, name, explode)
        monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", explode)

        padding = b"%" + b"a" * (2 * 1024 * 1024)
        large = make_pdf().replace(b"trailer", padding + b"\ntrailer")

        response = upload(signed_in_client, day_attachments_url(trip), large)

        assert response.status_code == 201, response.text
        assert response.json()["byte_size"] == len(large)


class TestAccessControl:
    def test_a_request_without_a_csrf_token_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The session cookie alone is not enough on an unsafe method.

        A cross-site upload is one of the three adversaries the spec's threat
        model names, and the double-submit token is what refuses it.
        """
        from trip_planner.security.sessions import CSRF_HEADER_NAME

        del signed_in_client.headers[CSRF_HEADER_NAME]

        response = upload(signed_in_client, day_attachments_url(trip), make_pdf())

        assert response.status_code == 403
        assert error_code(response) == "csrf_token_invalid"

    def test_without_a_session_it_is_401(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        from trip_planner.security.sessions import SESSION_COOKIE_NAME

        signed_in_client.cookies.delete(SESSION_COOKIE_NAME)

        response = upload(signed_in_client, day_attachments_url(trip), make_pdf())

        assert response.status_code == 401
        assert error_code(response) == "not_authenticated"

    def test_another_owners_trip_answers_404_not_403(
        self, signed_in_client: TestClient, db_session: OrmSession, other_owner: Owner
    ) -> None:
        theirs = Trip(
            owner_id=other_owner.id,
            title="Not yours",
            start_date=date(2026, 10, 10),
            end_date=date(2026, 10, 11),
            departure_place="Gdańsk",
        )
        db_session.add(theirs)
        db_session.flush()

        response = upload(
            signed_in_client,
            f"{TRIPS}/{theirs.id}/days/2026-10-10/attachments",
            make_pdf(),
        )

        assert response.status_code == 404
        assert error_code(response) == "not_found"


class TestQuotas:
    def test_the_parent_limit_engages(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        previous = get_upload_quota()
        set_upload_quota(UploadQuota(max_attachments_per_parent=1))
        try:
            first = upload(signed_in_client, day_attachments_url(trip), make_pdf())
            second = upload(signed_in_client, day_attachments_url(trip), make_pdf())
        finally:
            set_upload_quota(previous)

        assert first.status_code == 201, first.text
        assert second.status_code == 409
        assert error_code(second) == "attachment_limit_reached"

    def test_the_trip_byte_quota_engages(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        previous = get_upload_quota()
        set_upload_quota(UploadQuota(max_trip_bytes=10))
        try:
            response = upload(signed_in_client, day_attachments_url(trip), make_pdf())
        finally:
            set_upload_quota(previous)

        assert response.status_code == 409
        assert error_code(response) == "trip_storage_quota_exceeded"

    def test_a_successful_upload_is_recorded_against_the_window(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        from trip_planner.db.models import UploadEvent

        data = make_png()
        assert upload(signed_in_client, day_attachments_url(trip), data).status_code == 201

        events = db_session.query(UploadEvent).all()
        assert [event.byte_size for event in events] == [len(data)]


# --------------------------------------------------------------------------- #
# Reading one back
# --------------------------------------------------------------------------- #


@contextmanager
def recorded_statements() -> Iterator[list[str]]:
    """Every SQL statement executed inside the block, as text.

    Registered on the `Engine` class rather than on one engine instance so it
    catches the request's own session, which the test never holds a handle to.
    """
    statements: list[str] = []

    def record(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def attachment_url(trip: dict, attachment_id: str) -> str:
    return f"{TRIPS}/{trip['id']}/attachments/{attachment_id}"


def stored(
    client: TestClient, trip: dict, data: bytes = b"", *, filename: str = "voucher.pdf"
) -> dict:
    """Upload one file to the trip's first day and return its metadata."""
    response = upload(
        client, day_attachments_url(trip), data or make_pdf(), filename=filename
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestReadingTheMetadata:
    def test_it_answers_the_same_object_the_upload_did(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        created = stored(signed_in_client, trip, make_png(), filename="screenshot.png")

        response = signed_in_client.get(attachment_url(trip, created["id"]))

        assert response.status_code == 200, response.text
        assert response.json() == created

    def test_it_does_not_read_the_bytes(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """`attachment_blob` is a separate table so a listing costs no megabytes.

        The guarantee is worth an assertion rather than a comment: a `joinedload`,
        a `selectinload` or a widened `SELECT` added later would make the metadata
        route read the file itself, and nothing else in the suite would notice. So
        every statement the request emits is recorded and the blob table must not
        appear in any of them.
        """
        created = stored(signed_in_client, trip, make_png())

        with recorded_statements() as statements:
            response = signed_in_client.get(attachment_url(trip, created["id"]))

        assert response.status_code == 200, response.text
        assert not [sql for sql in statements if "attachment_blob" in sql], statements

    def test_an_unknown_id_is_a_404(self, signed_in_client: TestClient, trip: dict) -> None:
        response = signed_in_client.get(attachment_url(trip, str(uuid.uuid4())))

        assert response.status_code == 404
        assert error_code(response) == "not_found"

    def test_an_item_attachment_is_reachable_through_its_trip(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The second parent chain: `attachment → item → trip_day → trip`."""
        item = add_item(signed_in_client, trip)
        created = upload(signed_in_client, item_attachments_url(trip, item), make_jpeg()).json()

        response = signed_in_client.get(attachment_url(trip, created["id"]))

        assert response.status_code == 200, response.text
        assert response.json()["item_id"] == item["id"]


#: The exact header set the spec's Security section fixes, minus the two that
#: depend on the file itself. Asserted verbatim, per type, so a dropped header
#: fails here rather than in a penetration test.
CONSTANT_SERVING_HEADERS = {
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'none'; sandbox",
    "cross-origin-resource-policy": "same-origin",
    "referrer-policy": "no-referrer",
    "cache-control": "private, no-cache",
}


class TestServingTheContent:
    @pytest.mark.parametrize(
        ("data", "filename", "expected_type"),
        [
            (make_pdf(), "voucher.pdf", "application/pdf"),
            (make_jpeg(), "boarding-pass.jpg", "image/jpeg"),
            (make_png(), "screenshot.png", "image/png"),
        ],
    )
    def test_every_header_is_served_for_every_accepted_type(
        self,
        signed_in_client: TestClient,
        trip: dict,
        data: bytes,
        filename: str,
        expected_type: str,
    ) -> None:
        """Including the images — `Content-Disposition: attachment` is universal.

        An `<img src>` ignores the header, so parametrising the image types here
        is what proves the gallery's convenience never became a reason to serve a
        file inline in this origin.
        """
        created = stored(signed_in_client, trip, data, filename=filename)

        response = signed_in_client.get(f"{attachment_url(trip, created['id'])}/content")

        assert response.status_code == 200, response.text
        assert response.content == data
        assert response.headers["content-type"] == expected_type
        assert response.headers["content-disposition"] == (
            f'attachment; filename="{filename}"; filename*=UTF-8\'\'{quote(filename, safe="")}'
        )
        assert response.headers["etag"] == f'"{created["id"]}"'
        for name, value in CONSTANT_SERVING_HEADERS.items():
            assert response.headers[name] == value, name

    def test_the_served_type_is_the_derived_one_not_the_clients(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """A JPEG uploaded as `ticket.pdf`, declared `application/pdf`."""
        created = upload(
            signed_in_client,
            day_attachments_url(trip),
            make_jpeg(),
            filename="ticket.pdf",
            content_type="application/pdf",
        ).json()

        response = signed_in_client.get(f"{attachment_url(trip, created['id'])}/content")

        assert response.headers["content-type"] == "image/jpeg"

    @pytest.mark.parametrize(
        ("filename", "expected_ascii"),
        [
            # Non-ASCII: the name survives intact only in `filename*`, and the
            # quoted string carries a lossy but header-safe transliteration.
            ("Rezerwacja_Kraków_żółć.pdf", "Rezerwacja_Krak_w_____.pdf"),
            # The quoted-string escape. `"` is not a control character, so step 3
            # of the normalisation leaves it alone and step 6 is the only thing
            # between it and an injected `Content-Disposition` parameter.
            ('a";x=".pdf', "a__x__.pdf"),
            # The parameter separators themselves: `;` and `=` are ordinary
            # printables, so nothing before step 6 removes them.
            ("semi;colon=equals.pdf", "semi_colon_equals.pdf"),
        ],
    )
    def test_a_hostile_filename_reaches_the_header_safely_in_both_forms(
        self,
        signed_in_client: TestClient,
        trip: dict,
        db_session: OrmSession,
        filename: str,
        expected_ascii: str,
    ) -> None:
        """The stored name is put on the wire directly, so the worst case is stored.

        The name is written onto the row rather than sent through the upload,
        because httpx (like a browser) percent-escapes `"` inside a multipart
        `filename=` parameter — so an upload cannot produce the very row this
        route has to be safe against. What it *can* be is a row written by an
        older client, a fixture, or a future import path, and that is exactly what
        the header builder has to survive.
        """
        created = stored(signed_in_client, trip, make_pdf())
        db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == uuid.UUID(created["id"]))
            .values(filename=filename)
        )
        db_session.flush()

        response = signed_in_client.get(f"{attachment_url(trip, created['id'])}/content")

        header = response.headers["content-disposition"]
        assert header == (
            f'attachment; filename="{expected_ascii}"; '
            f"filename*=UTF-8''{quote(filename, safe='')}"
        )
        # Neither parameter can carry a raw quote, a backslash or a separator: the
        # quoted string is `[A-Za-z0-9._-]` only, and `filename*` is percent-encoded.
        _, quoted, extended = header.split("; ")
        assert set(quoted[len('filename="') : -1]) <= set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        )
        assert '"' not in extended and "\\" not in extended and ";" not in extended

    def test_a_newline_in_a_stored_filename_cannot_split_the_response(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        """The response-header-injection case, with the primitive itself."""
        created = stored(signed_in_client, trip, make_pdf())
        db_session.execute(
            sa.update(Attachment)
            .where(Attachment.id == uuid.UUID(created["id"]))
            .values(filename="a\r\nX-Injected: yes\r\n.pdf")
        )
        db_session.flush()

        response = signed_in_client.get(f"{attachment_url(trip, created['id'])}/content")

        assert response.status_code == 200
        assert "x-injected" not in response.headers
        assert "\r" not in response.headers["content-disposition"]
        assert "\n" not in response.headers["content-disposition"]

    def test_a_conditional_request_with_the_etag_answers_304(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The reason the caching contract is `no-cache` rather than `no-store`."""
        created = stored(signed_in_client, trip, make_png())
        url = f"{attachment_url(trip, created['id'])}/content"

        first = signed_in_client.get(url)
        second = signed_in_client.get(url, headers={"if-none-match": first.headers["etag"]})

        assert second.status_code == 304
        assert second.content == b""
        assert second.headers["etag"] == first.headers["etag"]

    def test_a_stale_etag_still_serves_the_bytes(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        created = stored(signed_in_client, trip, make_png())

        response = signed_in_client.get(
            f"{attachment_url(trip, created['id'])}/content",
            headers={"if-none-match": f'"{uuid.uuid4()}"'},
        )

        assert response.status_code == 200
        assert response.content == make_png()

    def test_every_revalidation_still_passes_the_session_check(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """`no-cache` is what makes this true, and it is the point of the choice."""
        from trip_planner.security.sessions import SESSION_COOKIE_NAME

        created = stored(signed_in_client, trip, make_png())
        url = f"{attachment_url(trip, created['id'])}/content"
        etag = signed_in_client.get(url).headers["etag"]

        signed_in_client.cookies.delete(SESSION_COOKIE_NAME)
        response = signed_in_client.get(url, headers={"if-none-match": etag})

        assert response.status_code == 401
        assert error_code(response) == "not_authenticated"


class TestDeletingAnAttachment:
    def test_it_removes_the_metadata_row_and_the_blob(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        """The blob goes by the database's own `ON DELETE CASCADE`, and is asserted."""
        created = stored(signed_in_client, trip, make_jpeg())

        response = signed_in_client.delete(attachment_url(trip, created["id"]))

        assert response.status_code == 204
        assert response.content == b""
        assert db_session.get(Attachment, uuid.UUID(created["id"])) is None
        assert db_session.get(AttachmentBlob, uuid.UUID(created["id"])) is None
        assert db_session.query(AttachmentBlob).count() == 0

    def test_it_is_gone_from_both_read_routes(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        created = stored(signed_in_client, trip)
        url = attachment_url(trip, created["id"])

        assert signed_in_client.delete(url).status_code == 204

        assert signed_in_client.get(url).status_code == 404
        assert signed_in_client.get(f"{url}/content").status_code == 404
        assert signed_in_client.delete(url).status_code == 404

    def test_it_leaves_the_trips_other_attachments_alone(
        self, signed_in_client: TestClient, trip: dict, db_session: OrmSession
    ) -> None:
        first = stored(signed_in_client, trip, make_pdf())
        second = stored(signed_in_client, trip, make_png())

        assert signed_in_client.delete(attachment_url(trip, first["id"])).status_code == 204

        assert db_session.get(Attachment, uuid.UUID(second["id"])) is not None
        assert db_session.get(AttachmentBlob, uuid.UUID(second["id"])) is not None


class TestAnotherTripsAttachment:
    """One condition, one code: a cross-owner reference is `404`, never `403`.

    A `403` would confirm the id exists, which is a membership oracle over the
    whole table — and inventing a distinct code for "belongs to another trip"
    would be the same leak spelled differently (spec, Edge Cases).
    """

    @pytest.fixture
    def theirs(self, signed_in_client: TestClient) -> tuple[dict, dict]:
        """A second trip of the same owner, holding one attachment.

        The same owner deliberately: this isolates *trip* scoping from the owner
        check `TestAccessControl` already covers, so a route that resolved the
        attachment by id alone fails here even though the caller is legitimate.
        """
        other = create(signed_in_client, title="Another trip")
        return other, stored(signed_in_client, other)

    def test_the_metadata_route_answers_404(
        self, signed_in_client: TestClient, trip: dict, theirs: tuple[dict, dict]
    ) -> None:
        response = signed_in_client.get(attachment_url(trip, theirs[1]["id"]))

        assert response.status_code == 404
        assert error_code(response) == "not_found"

    def test_the_content_route_answers_404(
        self, signed_in_client: TestClient, trip: dict, theirs: tuple[dict, dict]
    ) -> None:
        response = signed_in_client.get(f"{attachment_url(trip, theirs[1]['id'])}/content")

        assert response.status_code == 404
        assert error_code(response) == "not_found"

    def test_the_delete_route_answers_404_and_deletes_nothing(
        self,
        signed_in_client: TestClient,
        trip: dict,
        theirs: tuple[dict, dict],
        db_session: OrmSession,
    ) -> None:
        response = signed_in_client.delete(attachment_url(trip, theirs[1]["id"]))

        assert response.status_code == 404
        assert error_code(response) == "not_found"
        assert db_session.get(Attachment, uuid.UUID(theirs[1]["id"])) is not None

    def test_the_owning_trip_still_serves_it(
        self, signed_in_client: TestClient, theirs: tuple[dict, dict]
    ) -> None:
        """Guards the three above: a route that 404'd on everything would pass them."""
        owner_trip, attachment = theirs

        assert signed_in_client.get(attachment_url(owner_trip, attachment["id"])).status_code == 200


class TestThereIsNoPatch:
    def test_patching_an_attachment_is_not_routed(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Immutability is what lets the content route serve a strong `ETag`.

        Renaming the display filename is a feature nobody asked for, and replacing
        the bytes is a delete plus an upload. A `PATCH` added later would silently
        invalidate the caching contract, so its absence is asserted.
        """
        created = stored(signed_in_client, trip)

        response = signed_in_client.patch(
            attachment_url(trip, created["id"]), json={"filename": "renamed.pdf"}
        )

        assert response.status_code == 405


# --------------------------------------------------------------------------- #
# The counts and the lists on the trip and day payloads
# --------------------------------------------------------------------------- #


def timeline_items(client: TestClient, trip: dict, day: str = DAY) -> list[dict]:
    """The items of one day, as the *timeline* payload serves them."""
    response = client.get(f"{TRIPS}/{trip['id']}")
    assert response.status_code == 200, response.text
    days = [one for one in response.json()["days"] if one["date"] == day]
    assert days, f"{day} is not a day of this trip"
    return days[0]["items"]


def day_detail(client: TestClient, trip: dict, day: str = DAY) -> dict:
    response = client.get(f"{TRIPS}/{trip['id']}/days/{day}")
    assert response.status_code == 200, response.text
    return response.json()


class TestAttachmentCountOnTheTimeline:
    @pytest.mark.parametrize("count", [0, 1, 3])
    def test_the_count_matches_what_was_uploaded(
        self, signed_in_client: TestClient, trip: dict, count: int
    ) -> None:
        item = add_item(signed_in_client, trip)
        for index in range(count):
            assert (
                upload(
                    signed_in_client,
                    item_attachments_url(trip, item),
                    make_pdf(),
                    filename=f"voucher-{index}.pdf",
                ).status_code
                == 201
            )

        served = timeline_items(signed_in_client, trip)

        assert [one["attachment_count"] for one in served] == [count]

    def test_a_days_own_file_is_not_counted_against_its_items(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """A day's ferry timetable belongs to the day, not to the hotel booked on it."""
        item = add_item(signed_in_client, trip)
        assert upload(signed_in_client, day_attachments_url(trip), make_pdf()).status_code == 201

        served = timeline_items(signed_in_client, trip)

        assert [one["attachment_count"] for one in served] == [0]
        assert item["attachment_count"] == 0, "and the item was created with none"

    def test_the_timeline_carries_the_number_and_not_the_filenames(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """The badge needs a number; a year-long trip must not ship every filename."""
        item = add_item(signed_in_client, trip)
        upload(signed_in_client, item_attachments_url(trip, item), make_pdf())

        served = timeline_items(signed_in_client, trip)[0]

        assert served["attachment_count"] == 1
        assert "attachments" not in served

    def test_the_payload_does_not_issue_a_query_per_item(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """One aggregate for the whole trip, whatever the trip's length.

        The failure this guards is not a wrong answer, it is a payload that
        answers correctly and costs one `SELECT count(*)` per item — three hundred
        statements for a year-long trip, on the screen the owner opens first. So
        the statements are recorded and the ones touching `attachment` are
        counted, with more items than any per-item implementation could hide in.
        """
        for index in range(5):
            item = add_item(signed_in_client, trip, title=f"Item {index}")
            upload(signed_in_client, item_attachments_url(trip, item), make_pdf())

        with recorded_statements() as statements:
            served = timeline_items(signed_in_client, trip)

        assert [one["attachment_count"] for one in served] == [1, 1, 1, 1, 1]
        touching = [sql for sql in statements if " attachment" in sql.lower()]
        assert len(touching) == 1, touching
        assert not [sql for sql in statements if "attachment_blob" in sql], statements


class TestAttachmentsOnTheDayDetail:
    def test_the_day_lists_its_own_files_and_the_item_lists_its_own(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip)
        of_the_day = stored(signed_in_client, trip, make_pdf(), filename="ferry.pdf")
        of_the_item = upload(
            signed_in_client,
            item_attachments_url(trip, item),
            make_png(),
            filename="hotel.png",
        ).json()

        body = day_detail(signed_in_client, trip)

        assert [one["filename"] for one in body["attachments"]] == ["ferry.pdf"]
        assert body["attachments"][0]["id"] == of_the_day["id"]
        assert [one["filename"] for one in body["items"][0]["attachments"]] == ["hotel.png"]
        assert body["items"][0]["attachments"][0]["id"] == of_the_item["id"]
        assert body["items"][0]["attachment_count"] == 1

    def test_an_item_with_no_files_lists_an_empty_array(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Empty, never absent: "none" and "not served here" must stay distinct."""
        add_item(signed_in_client, trip)

        body = day_detail(signed_in_client, trip)

        assert body["attachments"] == []
        assert body["items"][0]["attachments"] == []
        assert body["items"][0]["attachment_count"] == 0

    def test_the_day_detail_does_not_issue_a_query_per_item(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """Two statements cover every attachment on the payload, however many items."""
        for index in range(5):
            item = add_item(signed_in_client, trip, title=f"Item {index}")
            upload(signed_in_client, item_attachments_url(trip, item), make_pdf())

        with recorded_statements() as statements:
            body = day_detail(signed_in_client, trip)

        assert [len(one["attachments"]) for one in body["items"]] == [1, 1, 1, 1, 1]
        touching = [sql for sql in statements if " attachment" in sql.lower()]
        assert len(touching) == 2, touching
        assert not [sql for sql in statements if "attachment_blob" in sql], statements

    def test_the_lists_never_carry_the_bytes(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip)
        upload(signed_in_client, item_attachments_url(trip, item), make_png())
        stored(signed_in_client, trip, make_pdf())

        with recorded_statements() as statements:
            body = day_detail(signed_in_client, trip)

        assert len(body["items"][0]["attachments"]) == 1
        assert not [sql for sql in statements if "attachment_blob" in sql], statements


class TestMovingAnItem:
    """`PATCH … {"date": …}` moves the item; its files go with it, the day's do not."""

    OTHER_DAY = "2026-10-12"

    def move(self, client: TestClient, trip: dict, item: dict) -> dict:
        response = client.patch(
            f"{TRIPS}/{trip['id']}/items/{item['id']}", json={"date": self.OTHER_DAY}
        )
        assert response.status_code == 200, response.text
        return response.json()

    def test_an_items_attachments_travel_with_it(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        item = add_item(signed_in_client, trip)
        attachment = upload(
            signed_in_client,
            item_attachments_url(trip, item),
            make_pdf(),
            filename="boarding.pdf",
        ).json()

        moved = self.move(signed_in_client, trip, item)

        assert moved["attachment_count"] == 1, "the PATCH response counts them too"
        assert day_detail(signed_in_client, trip)["items"] == []
        arrived = day_detail(signed_in_client, trip, self.OTHER_DAY)["items"]
        assert [one["id"] for one in arrived[0]["attachments"]] == [attachment["id"]]

    def test_a_days_own_attachment_does_not_move(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        """It was pinned to the day, and the day did not go anywhere."""
        item = add_item(signed_in_client, trip)
        of_the_day = stored(signed_in_client, trip, make_pdf(), filename="ferry.pdf")

        self.move(signed_in_client, trip, item)

        assert [one["id"] for one in day_detail(signed_in_client, trip)["attachments"]] == [
            of_the_day["id"]
        ]
        assert day_detail(signed_in_client, trip, self.OTHER_DAY)["attachments"] == []
