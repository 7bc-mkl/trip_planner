"""Serving a document that is still in the inbox.

The test this file exists for is
`test_the_two_content_routes_answer_with_byte_identical_headers`. The inbox
needed a **second** content route — the shipped one is mounted under
`/trips/{trip_id}` and resolves ownership through a parent chain an inbox
document does not have — and a second route is exactly where a header set
quietly diverges. Comparing the two responses for the same bytes turns "there is
one answer in this product to how a file is served" from a claim in a docstring
into something that fails a test when it stops being true.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import TEST_ENVIRONMENT
from tests.test_attachments_api import item_attachments_url, upload
from tests.test_domain_uploads import make_pdf
from tests.test_items_api import add_item
from tests.test_scheduler import INBOX_ENV
from tests.test_trips_api import create
from trip_planner.config import Settings, require_settings
from trip_planner.db.models import Attachment, AttachmentBlob, InboundMessage, Owner

PDF = make_pdf()

#: Headers that legitimately differ between any two responses and say nothing
#: about how a file is served.
IGNORED_HEADERS = frozenset({"date", "server", "content-length", "connection", "set-cookie"})


@pytest.fixture
def inbox_settings(database_url: str) -> Settings:
    return require_settings({"DATABASE_URL": database_url, **TEST_ENVIRONMENT, **INBOX_ENV})


@pytest.fixture
def inbox_app(db_session: OrmSession, inbox_settings: Settings) -> Iterator[FastAPI]:
    from trip_planner.api.deps import get_db
    from trip_planner.app import create_app
    from trip_planner.config import get_settings

    def request_scoped_db() -> Iterator[OrmSession]:
        db_session.expire_all()
        yield db_session

    application = create_app(check_configuration=False)
    application.dependency_overrides[get_db] = request_scoped_db
    application.dependency_overrides[get_settings] = lambda: inbox_settings
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def signed_in(inbox_app: FastAPI, owner: Owner, owner_password: str) -> Iterator[TestClient]:
    from trip_planner.security.sessions import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

    with TestClient(inbox_app, base_url="http://testserver") as client:
        response = client.post(
            "/api/v1/auth/login", json={"email": owner.email, "password": owner_password}
        )
        assert response.status_code == 204, response.text
        client.headers[CSRF_HEADER_NAME] = client.cookies.get(CSRF_COOKIE_NAME, "")
        yield client


def make_message(db: OrmSession, owner: Owner, **overrides: object) -> InboundMessage:
    fields: dict[str, object] = {
        "owner_id": owner.id,
        "ses_message_id": f"ses-{uuid.uuid4().hex}",
        "ses_sender_verdict": "PASS",
        "ses_scan_verdict": "PASS",
        "received_at": datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
        "from_address": owner.email,
        "subject": "Potwierdzenie rezerwacji",
        "state": "received",
        "text_body": "PNR: SX-9912L",
    }
    fields.update(overrides)
    record = InboundMessage(**fields)
    db.add(record)
    db.flush()
    return record


def attach(db: OrmSession, message: InboundMessage, *, data: bytes = PDF) -> Attachment:
    import hashlib

    attachment = Attachment(
        inbound_message_id=message.id,
        filename="voucher.pdf",
        content_type="application/pdf",
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )
    db.add(attachment)
    db.flush()
    db.add(AttachmentBlob(attachment_id=attachment.id, data=data))
    db.flush()
    return attachment


def content_url(message: InboundMessage, attachment: Attachment) -> str:
    return f"/api/v1/inbox/messages/{message.id}/attachments/{attachment.id}/content"


# --------------------------------------------------------------------------- #
# The header set, which must be the product's one answer
# --------------------------------------------------------------------------- #


def test_the_two_content_routes_answer_with_byte_identical_headers(
    signed_in: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """One file, two routes, one header set — asserted rather than intended.

    A second route is exactly where `nosniff`, the sandbox CSP or the
    `Content-Disposition` quietly goes missing, and the loss is invisible until
    somebody navigates straight to a hostile file. Comparing the responses means
    a header dropped from either side fails here rather than in a pen test.
    """
    trip = create(signed_in)
    item = add_item(signed_in, trip, trip["start_date"])
    uploaded = upload(signed_in, item_attachments_url(trip, item), PDF)
    assert uploaded.status_code == 201, uploaded.text
    shipped_url = (
        f"/api/v1/trips/{trip['id']}/attachments/{uploaded.json()['id']}/content"
    )

    message = make_message(db_session, owner)
    inbox_attachment = attach(db_session, message)

    shipped = signed_in.get(shipped_url)
    inbox = signed_in.get(content_url(message, inbox_attachment))

    assert (shipped.status_code, inbox.status_code) == (200, 200)
    assert shipped.content == inbox.content == PDF

    def comparable(response) -> dict[str, str]:
        return {
            name.lower(): value
            for name, value in response.headers.items()
            # The ETag is the attachment's own id, so it differs by construction
            # for two different rows; every other header must match exactly.
            if name.lower() not in IGNORED_HEADERS and name.lower() != "etag"
        }

    assert comparable(shipped) == comparable(inbox)


def test_the_full_shipped_header_set_is_present(
    signed_in: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Named explicitly as well as compared, so the comparison cannot pass vacuously
    if both routes lose a header at once."""
    message = make_message(db_session, owner)
    attachment = attach(db_session, message)

    response = signed_in.get(content_url(message, attachment))

    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["etag"] == f'"{attachment.id}"'


def test_a_conditional_request_answers_304_without_reading_the_bytes(
    signed_in: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """The whole point of the strong `ETag`: a revalidation costs one metadata row."""
    message = make_message(db_session, owner)
    attachment = attach(db_session, message)
    url = content_url(message, attachment)

    first = signed_in.get(url)
    second = signed_in.get(url, headers={"If-None-Match": first.headers["etag"]})

    assert second.status_code == 304
    assert second.content == b""


def test_a_weakened_etag_still_matches(
    signed_in: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """A cache is entitled to weaken a strong validator on the way back."""
    message = make_message(db_session, owner)
    attachment = attach(db_session, message)

    response = signed_in.get(
        content_url(message, attachment), headers={"If-None-Match": f'W/"{attachment.id}"'}
    )

    assert response.status_code == 304


# --------------------------------------------------------------------------- #
# Who may read it
# --------------------------------------------------------------------------- #


def test_another_owner_s_message_is_a_404(
    signed_in: TestClient, db_session: OrmSession, other_owner: Owner
) -> None:
    """404, never 403 — a 403 would confirm the id exists, which is a membership
    oracle over the whole table. The same answer the shipped routes give."""
    message = make_message(db_session, other_owner)
    attachment = attach(db_session, message)

    assert signed_in.get(content_url(message, attachment)).status_code == 404


def test_an_attachment_on_a_different_message_is_a_404(
    signed_in: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Scoped to *this* message, not merely to the owner.

    Otherwise the message id in the URL is decorative, and a bug that mixed up
    two of his messages would serve the wrong document while looking right.
    """
    first = make_message(db_session, owner)
    second = make_message(db_session, owner)
    attachment = attach(db_session, second)

    assert signed_in.get(content_url(first, attachment)).status_code == 404


def test_an_unknown_attachment_is_a_404(
    signed_in: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    message = make_message(db_session, owner)
    url = f"/api/v1/inbox/messages/{message.id}/attachments/{uuid.uuid4()}/content"

    assert signed_in.get(url).status_code == 404


def test_a_discarded_message_is_a_404(
    signed_in: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """"Deleted" must not mean "invisible in one place and readable in another"."""
    message = make_message(db_session, owner, state="discarded")
    attachment = attach(db_session, message)

    assert signed_in.get(content_url(message, attachment)).status_code == 404


def test_the_route_needs_a_session(
    inbox_app: FastAPI, db_session: OrmSession, owner: Owner
) -> None:
    message = make_message(db_session, owner)
    attachment = attach(db_session, message)

    with TestClient(inbox_app, base_url="http://testserver") as anonymous:
        assert anonymous.get(content_url(message, attachment)).status_code == 401


def test_an_unconfigured_deployment_answers_inbox_not_configured(
    signed_in_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """`signed_in_client` is the ordinary app fixture, with no INBOX_* settings.

    409 rather than 404: the route exists and the request is fine — the
    deployment simply has no inbox — and the screen has something honest to say.
    """
    message = make_message(db_session, owner)
    attachment = attach(db_session, message)

    response = signed_in_client.get(content_url(message, attachment))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inbox_not_configured"
