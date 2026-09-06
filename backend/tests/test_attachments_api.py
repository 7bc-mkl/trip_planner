"""The two upload endpoints, and the order of their checks.

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
"""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
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
from trip_planner.db.models import Attachment, AttachmentBlob, Owner, Trip
from trip_planner.domain.uploads import MAX_ATTACHMENT_BYTES
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


def oversized_pdf() -> bytes:
    """A PDF one byte past the per-file cap. Valid, and refused for its size alone."""
    padding = b"%" + b"a" * (MAX_ATTACHMENT_BYTES - len(make_pdf()))
    return make_pdf().replace(b"trailer", padding + b"\ntrailer")


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

    def test_a_declared_length_over_the_cap_is_refused(
        self, signed_in_client: TestClient, trip: dict
    ) -> None:
        response = upload(signed_in_client, day_attachments_url(trip), oversized_pdf())

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
