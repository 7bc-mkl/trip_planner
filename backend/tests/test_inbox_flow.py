"""The brief's own flow, end to end — Phase 3 step 8.

Forward a confirmation → it is ingested → routed (stubbed provider, no network)
→ an action item appears → the owner approves the confirmation number, the cost
and the document → the item moves to *gotowe* and the readiness counter
changes. Each hop runs the real code path: ingestion, the worker's routing step
(which is what creates the proposal), and the approval endpoint.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests import test_inbox_api as _inbox_api
from tests.test_domain_uploads import make_pdf
from tests.test_inbox_api import INBOX
from tests.test_inbox_ingest import INBOX as INBOX_CONFIG
from tests.test_inbox_ingest import PREFIX, StubS3, mime
from tests.test_integrations_model import CapturingTransport, answer, settings_for
from tests.test_models_item import make_item
from tests.test_models_trip import make_trip
from trip_planner.config import Settings
from trip_planner.db.models import (
    Attachment,
    InboundActionItem,
    InboundMessage,
    Item,
    Owner,
    TripDay,
)
from trip_planner.inbound.ingest import ingest_message
from trip_planner.integrations.model import ModelClient, build_adapter
from trip_planner.scheduler import InboxWorker

s3 = _inbox_api.s3
inbox_settings = _inbox_api.inbox_settings
inbox_app = _inbox_api.inbox_app
owner_client = _inbox_api.owner_client

CONFIRMATION = """\
Dear guest,

Your booking at Hotel Majestic Kuala Lumpur is confirmed.
Check-in: 17 October 2026, 15:00
Booking reference: HM-77
Total paid: MYR 480.00

Free cancellation until 13 October 2026.
"""


def test_a_forwarded_confirmation_becomes_an_approved_booking(
    db_session: OrmSession,
    owner: Owner,
    owner_client: TestClient,
    inbox_settings: Settings,
) -> None:
    # A trip the owner planned by hand, with the hotel decided but not booked.
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    days = {}
    current = trip.start_date
    while current <= trip.end_date:
        days[current] = TripDay(trip_id=trip.id, date=current)
        db_session.add(days[current])
        current += timedelta(days=1)
    db_session.flush()
    hotel = make_item(days[date(2026, 10, 17)], title="Hotel Majestic", status="to_book")
    db_session.add(hotel)
    db_session.flush()

    before = owner_client.get(f"/api/v1/trips/{trip.id}").json()["readiness"]
    assert before == {"arranged": 0, "tracked": 1}

    # 1. Forwarded: SES delivered, the worker ingests the MIME.
    voucher = make_pdf()
    message = InboundMessage(
        owner_id=owner.id,
        ses_message_id=f"ses-{uuid.uuid4().hex}",
        s3_object_key=f"{PREFIX}ses-flow",
        ses_sender_verdict="PASS",
        ses_scan_verdict="PASS",
        received_at=datetime.now(UTC),
        from_address=owner.email,
        subject="Fwd: Booking confirmation",
        state="pending_ingest",
    )
    db_session.add(message)
    db_session.flush()
    fetcher = StubS3(
        {
            f"{PREFIX}ses-flow": mime(
                sender=owner.email,
                text=CONFIRMATION,
                documents=[("voucher.pdf", voucher, "application/pdf")],
            )
        }
    )
    assert ingest_message(
        db_session, message, owner=owner, inbox=INBOX_CONFIG, fetcher=fetcher  # type: ignore[arg-type]
    ).state == "received"

    # 2. Routed by the worker, with a stubbed provider that also extracts.
    claim = {
        "trip_id": str(trip.id),
        "fields": {
            "title": "Hotel Majestic",
            "kind": "accommodation",
            "confirmation_number": "HM-77",
            "start_date": "2026-10-17",
            "start_time": "15:00",
            "cost_amount": "480.00",
            "cost_currency": "MYR",
        },
    }
    model = settings_for("anthropic")
    transport = CapturingTransport(200, answer("anthropic", json.dumps(claim)))
    worker = InboxWorker(
        dataclasses.replace(inbox_settings, model=model),
        lambda: db_session,
        fetcher=fetcher,  # type: ignore[arg-type]
        model_client=ModelClient(
            settings=model, adapter=build_adapter(model), transport=transport, retry_pause=0
        ),
    )
    worker._route(db_session, message, owner)

    db_session.expire_all()
    assert db_session.get(InboundMessage, message.id).state == "routed"
    # Nothing on the plan has changed yet: routing proposes, it never writes.
    untouched = db_session.get(Item, hotel.id)
    assert (untouched.status, untouched.confirmation_number) == ("to_book", None)

    # 3. The action item is waiting, aimed at the hotel by its title and day.
    summary = owner_client.get(f"{INBOX}/summary").json()
    assert summary["pending_action_items"] == 1
    (pending,) = owner_client.get(f"{INBOX}/action-items").json()
    assert (pending["kind"], pending["target_item_id"]) == ("update_item", str(hotel.id))
    assert {row["name"] for row in pending["fields"]} >= {"confirmation_number", "cost"}
    (document,) = pending["attachments"]

    # 4. Approve the reference, the cost and the document; mark it booked.
    approved = owner_client.post(
        f"{INBOX}/action-items/{pending['id']}/approve",
        json={
            "target_item_id": str(hotel.id),
            "fields": ["confirmation_number", "cost"],
            "attachment_ids": [document["id"]],
            "set_status": "done",
            "expected_revision": pending["revision"],
        },
    )
    assert approved.status_code == 200, approved.text

    # 5. The plan moved, and the counter with it.
    db_session.expire_all()
    booked = db_session.get(Item, hotel.id)
    assert booked.status == "done"
    assert booked.confirmation_number == "HM-77"
    assert (booked.cost_amount, booked.cost_currency) == (Decimal("480.00"), "MYR")
    assert booked.start_time is None  # claimed, not ticked, not written
    on_item = db_session.execute(
        sa.select(Attachment).where(Attachment.item_id == hotel.id)
    ).scalar_one()
    assert on_item.filename == "voucher.pdf"
    assert on_item.inbound_message_id is None

    after = owner_client.get(f"/api/v1/trips/{trip.id}").json()["readiness"]
    assert after == {"arranged": 1, "tracked": 1}
    assert owner_client.get(f"{INBOX}/summary").json()["pending_action_items"] == 0
    assert db_session.get(InboundActionItem, uuid.UUID(pending["id"])).state == "approved"


def test_a_failing_proposal_keeps_the_route_and_sends_nothing_twice(
    db_session: OrmSession,
    owner: Owner,
    inbox_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bug in building the proposal must not undo the routing it follows.

    Rolling the route back would leave the message `received`, and the next
    pass would send the owner's text to the provider a second time for the
    same answer. The route is committed first; a failed proposal leaves a
    routed message the owner can still propose by hand.
    """
    import trip_planner.scheduler as scheduler_module

    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    message = InboundMessage(
        owner_id=owner.id,
        ses_message_id=f"ses-{uuid.uuid4().hex}",
        ses_sender_verdict="PASS",
        ses_scan_verdict="PASS",
        received_at=datetime.now(UTC),
        from_address=owner.email,
        subject="Booking",
        state="received",
        text_body="Check-in 17 October 2026",
    )
    db_session.add(message)
    db_session.flush()

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("a bug in the proposal builder")

    monkeypatch.setattr(scheduler_module, "propose_from_routing", broken)
    model = settings_for("anthropic")
    transport = CapturingTransport(
        200, answer("anthropic", json.dumps({"trip_id": str(trip.id)}))
    )
    worker = InboxWorker(
        dataclasses.replace(inbox_settings, model=model),
        lambda: db_session,
        fetcher=StubS3(),  # type: ignore[arg-type]
        model_client=ModelClient(
            settings=model, adapter=build_adapter(model), transport=transport, retry_pause=0
        ),
    )

    worker._route(db_session, message, owner)

    db_session.expire_all()
    routed = db_session.get(InboundMessage, message.id)
    assert (routed.state, routed.trip_id) == ("routed", trip.id)
