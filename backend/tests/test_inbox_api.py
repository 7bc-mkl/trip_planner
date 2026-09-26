"""The owner's inbox routes, and the two ways out of quarantine.

Two groups of claim are worth the length here. The first is **what quarantine
withholds**: headers, and nothing else, from every route — a barrier that
renders what it is holding back has become a delivery mechanism. The second is
**what hand placement does not do**: it changes one column and writes nothing to
the plan, which is what lets Phase 1 be useful without `inbound_action_item`
existing and keeps D21 governing every later write.

S3 is reached through the same stub the ingestion tests use, injected through the
route's own dependency, so these exercise the real handlers without any suite run
touching AWS.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import TEST_ENVIRONMENT
from tests.test_domain_uploads import make_pdf
from tests.test_inbox_ingest import PREFIX, StubS3, mime
from tests.test_scheduler import INBOX_ENV
from tests.test_trips_api import create
from trip_planner.config import Settings, require_settings
from trip_planner.db.models import (
    Attachment,
    InboundDeliveryStatus,
    InboundMessage,
    InboundTrustedSender,
    Owner,
)

INBOX = "/api/v1/inbox"


@pytest.fixture
def s3() -> StubS3:
    return StubS3()


@pytest.fixture
def inbox_settings(database_url: str) -> Settings:
    return require_settings({"DATABASE_URL": database_url, **TEST_ENVIRONMENT, **INBOX_ENV})


@pytest.fixture
def inbox_app(
    db_session: OrmSession, inbox_settings: Settings, s3: StubS3
) -> Iterator[FastAPI]:
    from trip_planner.api import inbox as inbox_module
    from trip_planner.api.deps import get_db
    from trip_planner.app import create_app
    from trip_planner.config import get_settings

    def request_scoped_db() -> Iterator[OrmSession]:
        db_session.expire_all()
        yield db_session

    application = create_app(check_configuration=False)
    application.dependency_overrides[get_db] = request_scoped_db
    application.dependency_overrides[get_settings] = lambda: inbox_settings
    application.dependency_overrides[inbox_module.get_s3_fetcher] = lambda: s3

    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def owner_client(inbox_app: FastAPI, owner: Owner, owner_password: str) -> Iterator[TestClient]:
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
        "s3_object_key": f"{PREFIX}ses-1",
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


# --------------------------------------------------------------------------- #
# The summary
# --------------------------------------------------------------------------- #


def test_the_summary_counts_the_queue_and_the_quarantine(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    make_message(db_session, owner, state="unrouted")
    make_message(db_session, owner, state="unrouted")
    make_message(db_session, owner, state="quarantined", text_body="")
    make_message(db_session, owner, state="received")

    body = owner_client.get(f"{INBOX}/summary").json()

    assert body["unrouted"] == 2
    assert body["quarantined"] == 1
    assert body["inbox_enabled"] is True
    assert body["address"] == INBOX_ENV["INBOX_RECIPIENT"]


def test_the_summary_reports_freshness_so_quiet_and_broken_look_different(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """An empty inbox and an inbox whose ingestion has been failing for a day
    must not render identically."""
    db_session.add(
        InboundDeliveryStatus(
            owner_id=owner.id,
            last_received_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
            last_error_at=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
            last_error="ingest_failed",
        )
    )
    db_session.flush()

    body = owner_client.get(f"{INBOX}/summary").json()

    assert body["last_received_at"] is not None
    assert body["last_error"] == "ingest_failed"


def test_the_summary_answers_on_an_unconfigured_deployment(
    signed_in_client: TestClient,
) -> None:
    """Not behind `require_inbox`, deliberately.

    The screen has to render its "not set up" state, and a summary that answered
    409 would make the nav badge's absence look like a failure rather than a
    setting.
    """
    body = signed_in_client.get(f"{INBOX}/summary").json()

    assert body["inbox_enabled"] is False
    assert body["address"] is None


def test_the_summary_does_not_promise_action_items_that_do_not_exist_yet(
    owner_client: TestClient,
) -> None:
    """A field reporting zero for a concept Phase 1 does not have says something
    false; an absent field is something a consumer can see is absent."""
    assert "pending_action_items" not in owner_client.get(f"{INBOX}/summary").json()


# --------------------------------------------------------------------------- #
# The list and the detail
# --------------------------------------------------------------------------- #


def test_the_list_carries_metadata_and_never_the_body(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    make_message(db_session, owner, text_body="PNR: SX-9912L")

    row = owner_client.get(f"{INBOX}/messages").json()[0]

    assert row["subject"] == "Potwierdzenie rezerwacji"
    assert "text_body" not in row


def test_the_list_never_shows_a_quarantined_message_whatever_is_asked_for(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Quarantine has its own route precisely so that showing it is a separate,
    deliberate act — including against a `state=quarantined` filter."""
    make_message(db_session, owner, state="quarantined", text_body="")

    assert owner_client.get(f"{INBOX}/messages").json() == []
    assert owner_client.get(f"{INBOX}/messages?state=quarantined").json() == []


def test_a_message_that_has_arrived_but_is_not_yet_readable_is_still_listed(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Hiding it would make a slow ingestion indistinguishable from no mail."""
    make_message(db_session, owner, state="pending_ingest", text_body="")

    assert [one["state"] for one in owner_client.get(f"{INBOX}/messages").json()] == [
        "pending_ingest"
    ]


def test_the_list_is_newest_first(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    make_message(db_session, owner, subject="Starsza", received_at=datetime(2026, 9, 1, tzinfo=UTC))
    make_message(db_session, owner, subject="Nowsza", received_at=datetime(2026, 10, 1, tzinfo=UTC))

    assert [one["subject"] for one in owner_client.get(f"{INBOX}/messages").json()] == [
        "Nowsza",
        "Starsza",
    ]


def test_another_owner_s_messages_are_not_listed(
    owner_client: TestClient, db_session: OrmSession, other_owner: Owner
) -> None:
    make_message(db_session, other_owner)

    assert owner_client.get(f"{INBOX}/messages").json() == []


def test_the_detail_carries_the_text_and_the_documents(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    import hashlib

    message = make_message(db_session, owner)
    data = make_pdf()
    db_session.add(
        Attachment(
            inbound_message_id=message.id,
            filename="voucher.pdf",
            content_type="application/pdf",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
    )
    db_session.flush()

    body = owner_client.get(f"{INBOX}/messages/{message.id}").json()

    assert body["text_body"] == "PNR: SX-9912L"
    assert [one["filename"] for one in body["attachments"]] == ["voucher.pdf"]
    assert body["attachment_count"] == 1
    # Phase 1 has no model, so nothing has left this deployment.
    assert body["attachments"][0]["sent_externally_at"] is None


def test_the_detail_refuses_a_quarantined_message(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Its content is exactly what quarantine exists to withhold.

    Serving it here "because the owner asked" would make the barrier a
    formality; `/inbox/quarantine/{id}` is the route for what he may see.
    """
    message = make_message(db_session, owner, state="quarantined", text_body="")

    assert owner_client.get(f"{INBOX}/messages/{message.id}").status_code == 404


def test_another_owner_s_message_is_a_404(
    owner_client: TestClient, db_session: OrmSession, other_owner: Owner
) -> None:
    message = make_message(db_session, other_owner)

    assert owner_client.get(f"{INBOX}/messages/{message.id}").status_code == 404


# --------------------------------------------------------------------------- #
# Hand placement — and what it deliberately does not do
# --------------------------------------------------------------------------- #


def test_placing_a_message_changes_exactly_one_column(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """The claim that lets Phase 1 ship without `inbound_action_item`.

    He is classifying his own mail, not approving a change to a trip. Nothing is
    written to the plan, and the document stays parented to the message, so D21
    still governs every later write.
    """
    import hashlib

    trip = create(owner_client)
    message = make_message(db_session, owner, state="unrouted")
    data = make_pdf()
    db_session.add(
        Attachment(
            inbound_message_id=message.id,
            filename="voucher.pdf",
            content_type="application/pdf",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
    )
    db_session.flush()

    response = owner_client.post(
        f"{INBOX}/messages/{message.id}/place", json={"trip_id": trip["id"]}
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "routed"
    assert response.json()["routing_reason"] == "placed_by_hand"

    db_session.expire_all()
    stored = db_session.get(InboundMessage, message.id)
    assert stored is not None and str(stored.trip_id) == trip["id"]
    # The document has not moved into the plan.
    attachment = db_session.execute(
        sa.select(Attachment).where(Attachment.inbound_message_id == message.id)
    ).scalar_one()
    assert attachment.item_id is None and attachment.trip_day_id is None


def test_placing_on_a_trip_that_is_not_his_is_refused(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, other_owner: Owner
) -> None:
    """422 rather than 404: the message is his and the route is right, so what is
    wrong is a value in the body."""
    from tests.test_models_trip import make_trip

    stranger_trip = make_trip(other_owner)
    db_session.add(stranger_trip)
    db_session.flush()
    message = make_message(db_session, owner, state="unrouted")

    response = owner_client.post(
        f"{INBOX}/messages/{message.id}/place", json={"trip_id": str(stranger_trip.id)}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "message_not_routable"


def test_placing_requires_the_csrf_header(
    inbox_app: FastAPI, db_session: OrmSession, owner: Owner, owner_password: str
) -> None:
    """Every unsafe inbox method is CSRF-checked, and not by remembering to.

    `get_current_owner` depends on `CurrentSession`, which runs `verify_csrf`, so
    the check arrives with the dependency rather than with the handler.
    """
    message = make_message(db_session, owner, state="unrouted")
    trip_id = str(uuid.uuid4())

    with TestClient(inbox_app, base_url="http://testserver") as client:
        client.post("/api/v1/auth/login", json={"email": owner.email, "password": owner_password})
        response = client.post(
            f"{INBOX}/messages/{message.id}/place", json={"trip_id": trip_id}
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_token_invalid"


def test_an_unknown_field_in_the_place_body_is_refused(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """`extra="forbid"`, per AGENTS.md, so a typo'd field is not silently ignored."""
    trip = create(owner_client)
    message = make_message(db_session, owner, state="unrouted")

    response = owner_client.post(
        f"{INBOX}/messages/{message.id}/place",
        json={"trip_id": trip["id"], "item_id": str(uuid.uuid4())},
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Deleting
# --------------------------------------------------------------------------- #


def test_deleting_a_message_with_no_outstanding_object_removes_it_outright(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    message = make_message(db_session, owner, s3_object_key=None)

    assert owner_client.delete(f"{INBOX}/messages/{message.id}").status_code == 204

    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id) is None


def test_deleting_a_message_whose_object_remains_leaves_a_tombstone(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Hard-deleting the row first would lose the only record of which object to
    delete, leaving a private copy of his confirmation in S3 for a month."""
    message = make_message(db_session, owner, s3_object_key=f"{PREFIX}ses-1")

    assert owner_client.delete(f"{INBOX}/messages/{message.id}").status_code == 204

    db_session.expire_all()
    stored = db_session.get(InboundMessage, message.id)
    assert stored is not None
    assert stored.state == "discarded"
    assert stored.s3_object_key == f"{PREFIX}ses-1"


def test_a_discarded_message_is_hidden_from_every_route(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    message = make_message(db_session, owner, state="discarded")

    assert owner_client.get(f"{INBOX}/messages").json() == []
    assert owner_client.get(f"{INBOX}/messages/{message.id}").status_code == 404


def test_deleting_removes_the_documents(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    import hashlib

    message = make_message(db_session, owner, s3_object_key=f"{PREFIX}ses-1")
    data = make_pdf()
    db_session.add(
        Attachment(
            inbound_message_id=message.id,
            filename="voucher.pdf",
            content_type="application/pdf",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
    )
    db_session.flush()

    owner_client.delete(f"{INBOX}/messages/{message.id}")
    db_session.expire_all()

    assert (
        db_session.execute(
            sa.select(sa.func.count())
            .select_from(Attachment)
            .where(Attachment.inbound_message_id == message.id)
        ).scalar_one()
        == 0
    )


# --------------------------------------------------------------------------- #
# Quarantine
# --------------------------------------------------------------------------- #


def quarantined(db: OrmSession, owner: Owner, **overrides: object) -> InboundMessage:
    fields: dict[str, object] = {
        "state": "quarantined",
        "text_body": "",
        "from_address": "rezerwacje@airline.example",
        "routing_reason": "unknown_sender",
    }
    fields.update(overrides)
    return make_message(db, owner, **fields)


def test_quarantine_shows_headers_and_nothing_else(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """A barrier that renders what it is holding back has become a delivery
    mechanism for exactly the material the owner did not ask to see."""
    message = quarantined(db_session, owner)

    body = owner_client.get(f"{INBOX}/quarantine/{message.id}").json()

    assert body["from_address"] == "rezerwacje@airline.example"
    assert body["subject"] == "Potwierdzenie rezerwacji"
    assert "text_body" not in body
    assert "attachments" not in body


def test_quarantine_offers_trusting_only_for_an_authenticated_unknown_sender(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    message = quarantined(db_session, owner)

    body = owner_client.get(f"{INBOX}/quarantine/{message.id}").json()

    assert body["may_trust_sender"] is True
    assert body["may_release_message"] is False


def test_quarantine_offers_release_only_for_a_failed_authentication(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """And never trusting: that would add a spoofable address to the allow-list
    for ever on the strength of one recognised subject line."""
    message = quarantined(
        db_session, owner, ses_sender_verdict="FAIL", routing_reason="failed_authentication"
    )

    body = owner_client.get(f"{INBOX}/quarantine/{message.id}").json()

    assert body["may_release_message"] is True
    assert body["may_trust_sender"] is False


def test_a_failed_scan_offers_neither_recovery(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """A virus verdict is not a false positive the owner is in a position to overrule."""
    message = quarantined(
        db_session, owner, ses_scan_verdict="FAIL", routing_reason="failed_scan"
    )

    body = owner_client.get(f"{INBOX}/quarantine/{message.id}").json()

    assert body["may_trust_sender"] is False
    assert body["may_release_message"] is False


def test_an_expired_object_is_reported_as_unrecoverable_on_the_row(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Said up front rather than discovered by pressing a button that fails."""
    message = quarantined(db_session, owner, s3_object_key=None)

    assert owner_client.get(f"{INBOX}/quarantine/{message.id}").json()["recoverable"] is False


def test_a_message_that_is_not_quarantined_is_not_on_the_quarantine_route(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    message = make_message(db_session, owner)

    assert owner_client.get(f"{INBOX}/quarantine/{message.id}").status_code == 404


# --------------------------------------------------------------------------- #
# Trusting a sender
# --------------------------------------------------------------------------- #


def test_trusting_a_sender_ingests_the_message_and_remembers_the_address(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    message = quarantined(db_session, owner)
    s3.objects[f"{PREFIX}ses-1"] = mime(
        sender="rezerwacje@airline.example", text="PNR: SX-9912L"
    )

    response = owner_client.post(f"{INBOX}/quarantine/{message.id}/trust-sender")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "received"

    db_session.expire_all()
    stored = db_session.get(InboundMessage, message.id)
    assert stored is not None and stored.text_body == "PNR: SX-9912L"
    assert (
        db_session.execute(
            sa.select(InboundTrustedSender).where(
                InboundTrustedSender.owner_id == owner.id,
                InboundTrustedSender.address == "rezerwacje@airline.example",
            )
        ).scalar_one_or_none()
        is not None
    )


def test_trusting_uses_only_the_recorded_ses_key(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    """The key comes back out of the database, so nothing the request carries can
    point this deployment at a different object."""
    message = quarantined(db_session, owner)
    s3.objects[f"{PREFIX}ses-1"] = mime(sender="rezerwacje@airline.example")

    owner_client.post(f"{INBOX}/quarantine/{message.id}/trust-sender")

    assert s3.fetched == [f"{PREFIX}ses-1"]


def test_trusting_is_refused_where_authentication_failed(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    message = quarantined(
        db_session, owner, ses_sender_verdict="FAIL", routing_reason="failed_authentication"
    )

    response = owner_client.post(f"{INBOX}/quarantine/{message.id}/trust-sender")

    assert response.status_code == 422


def test_trusting_answers_explicitly_when_the_object_has_expired(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """409 `inbox_object_unavailable`, so the screen can say what actually happened."""
    message = quarantined(db_session, owner, s3_object_key=None)

    response = owner_client.post(f"{INBOX}/quarantine/{message.id}/trust-sender")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inbox_object_unavailable"


def test_trusting_answers_explicitly_when_the_object_is_gone_from_s3(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    """The locator is still on the row, but the bucket no longer holds it."""
    message = quarantined(db_session, owner)

    response = owner_client.post(f"{INBOX}/quarantine/{message.id}/trust-sender")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "inbox_object_unavailable"


# --------------------------------------------------------------------------- #
# Releasing one message
# --------------------------------------------------------------------------- #


def test_releasing_accepts_this_message_and_trusts_nobody(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    """The narrowness is the control: one stored object, no address added, and
    the next message from the same sender is quarantined exactly as this was."""
    message = quarantined(
        db_session, owner, ses_sender_verdict="FAIL", routing_reason="failed_authentication"
    )
    s3.objects[f"{PREFIX}ses-1"] = mime(
        sender="rezerwacje@airline.example", text="PNR: SX-9912L"
    )

    response = owner_client.post(f"{INBOX}/quarantine/{message.id}/release")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "received"

    db_session.expire_all()
    assert (
        db_session.execute(
            sa.select(sa.func.count())
            .select_from(InboundTrustedSender)
            .where(InboundTrustedSender.owner_id == owner.id)
        ).scalar_one()
        == 0
    )


def test_releasing_updates_the_same_row_rather_than_creating_a_second(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    """`(owner_id, ses_message_id)` stays one row through recovery."""
    message = quarantined(
        db_session, owner, ses_sender_verdict="FAIL", routing_reason="failed_authentication"
    )
    ses_id = message.ses_message_id
    s3.objects[f"{PREFIX}ses-1"] = mime(sender="rezerwacje@airline.example")

    owner_client.post(f"{INBOX}/quarantine/{message.id}/release")
    db_session.expire_all()

    rows = list(
        db_session.execute(
            sa.select(InboundMessage).where(InboundMessage.ses_message_id == ses_id)
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].id == message.id
    assert rows[0].state == "received"


def test_releasing_is_refused_for_a_failed_scan(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    message = quarantined(
        db_session, owner, ses_scan_verdict="FAIL", routing_reason="failed_scan"
    )
    s3.objects[f"{PREFIX}ses-1"] = mime(sender="rezerwacje@airline.example")

    response = owner_client.post(f"{INBOX}/quarantine/{message.id}/release")

    assert response.status_code == 422
    assert s3.fetched == []


def test_releasing_is_refused_for_a_merely_unknown_sender(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """Trusting is the right action there, and offering both would let the owner
    pick the weaker one by accident."""
    message = quarantined(db_session, owner)

    assert owner_client.post(f"{INBOX}/quarantine/{message.id}/release").status_code == 422


def test_a_released_message_becomes_an_ordinary_one(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    """It appears in the list, its detail serves its text, and its documents are
    readable — nothing about it stays second-class."""
    message = quarantined(
        db_session, owner, ses_sender_verdict="FAIL", routing_reason="failed_authentication"
    )
    s3.objects[f"{PREFIX}ses-1"] = mime(
        sender="rezerwacje@airline.example",
        text="PNR: SX-9912L",
        documents=[("voucher.pdf", make_pdf(), "application/pdf")],
    )

    owner_client.post(f"{INBOX}/quarantine/{message.id}/release")

    listed = owner_client.get(f"{INBOX}/messages").json()
    assert [one["id"] for one in listed] == [str(message.id)]

    detail = owner_client.get(f"{INBOX}/messages/{message.id}").json()
    assert detail["text_body"] == "PNR: SX-9912L"
    attachment_id = detail["attachments"][0]["id"]

    content = owner_client.get(
        f"{INBOX}/messages/{message.id}/attachments/{attachment_id}/content"
    )
    assert content.status_code == 200
    assert content.content == make_pdf()


def test_recovery_deletes_the_raw_object_once_the_message_is_stored(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    message = quarantined(db_session, owner)
    s3.objects[f"{PREFIX}ses-1"] = mime(sender="rezerwacje@airline.example")

    owner_client.post(f"{INBOX}/quarantine/{message.id}/trust-sender")

    assert s3.deleted == [f"{PREFIX}ses-1"]
    db_session.expire_all()
    stored = db_session.get(InboundMessage, message.id)
    assert stored is not None and stored.s3_object_key is None


def test_an_exhausted_window_answers_429_rather_than_deferring_silently(
    owner_client: TestClient, db_session: OrmSession, owner: Owner, s3: StubS3
) -> None:
    """He is standing there waiting, so "queued, come back later" needs saying."""
    from trip_planner.security.quota import InboxQuota, set_inbox_quota

    message = quarantined(db_session, owner)
    s3.objects[f"{PREFIX}ses-1"] = mime(sender="rezerwacje@airline.example")

    set_inbox_quota(InboxQuota(max_messages_per_window=1))
    try:
        response = owner_client.post(f"{INBOX}/quarantine/{message.id}/trust-sender")
    finally:
        set_inbox_quota(InboxQuota())

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "inbox_rate_limited"


# --------------------------------------------------------------------------- #
# Every owner route on an unconfigured deployment
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/messages"),
        ("get", "/messages/{id}"),
        ("post", "/messages/{id}/place"),
        ("delete", "/messages/{id}"),
        ("get", "/quarantine/{id}"),
        ("post", "/quarantine/{id}/trust-sender"),
        ("post", "/quarantine/{id}/release"),
    ],
)
def test_every_inbox_route_answers_not_configured_without_settings(
    signed_in_client: TestClient, db_session: OrmSession, owner: Owner, method: str, path: str
) -> None:
    """A shared dependency rather than a line per handler, so a route added later
    cannot forget and answer a confusing 500 from inside an AWS client."""
    message = make_message(db_session, owner)
    url = f"{INBOX}{path.format(id=message.id)}"

    call = getattr(signed_in_client, method)
    response = call(url, json={"trip_id": str(uuid.uuid4())}) if method == "post" else call(url)

    assert response.status_code == 409, url
    assert response.json()["error"]["code"] == "inbox_not_configured"


def test_the_quarantine_list_serves_headers_only(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """A list route beside the singular one, because *Show* has to render a list.

    Separate from `GET /inbox/messages` rather than a filter on it, and the
    separation is the control: showing quarantined mail is a distinct,
    explicit act, so it is a distinct, explicit route.
    """
    quarantined(db_session, owner, subject="Potwierdzenie z linii lotniczej")

    body = owner_client.get(f"{INBOX}/quarantine").json()

    assert len(body) == 1
    assert body[0]["from_address"] == "rezerwacje@airline.example"
    assert "text_body" not in body[0]
    assert "attachments" not in body[0]


def test_the_quarantine_list_holds_nothing_that_is_not_quarantined(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    make_message(db_session, owner, state="received")
    make_message(db_session, owner, state="unrouted")

    assert owner_client.get(f"{INBOX}/quarantine").json() == []


def test_the_quarantine_list_is_owner_scoped(
    owner_client: TestClient, db_session: OrmSession, other_owner: Owner
) -> None:
    quarantined(db_session, other_owner)

    assert owner_client.get(f"{INBOX}/quarantine").json() == []


def test_the_summary_carries_no_sender_addresses(
    owner_client: TestClient, db_session: OrmSession, owner: Owner
) -> None:
    """It is the badge's cheap poll, and every page load makes it.

    Putting strangers' headers in it would mean fetching them whether or not
    anyone asked to see them — which is the opposite of what *Show* is for.
    """
    quarantined(db_session, owner)

    body = owner_client.get(f"{INBOX}/summary").json()

    assert "rezerwacje@airline.example" not in json.dumps(body)
