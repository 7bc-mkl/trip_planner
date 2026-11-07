"""Action items, end to end through the API — Phase 3 steps 4 to 6.

Creation from routing and by hand, approval with its four layers of protection,
and reject / undo / re-target. Every test that approves something also asserts
what was **not** written, because "only what the owner named" is the claim.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from tests import test_inbox_api as _inbox_api
from tests.test_domain_uploads import make_pdf
from tests.test_inbox_api import INBOX, make_message
from tests.test_models_item import make_item
from tests.test_models_trip import make_trip
from trip_planner import approvals
from trip_planner.db.models import (
    Attachment,
    InboundActionItem,
    InboundMessage,
    Item,
    Owner,
    Trip,
    TripDay,
)
from trip_planner.domain.extraction import ExtractedFields
from trip_planner.security.quota import UploadQuota, get_upload_quota, set_upload_quota

# The inbox API's own fixtures, re-exported so pytest finds them here. Assigned
# rather than imported: an imported fixture shadowed by a test parameter of the
# same name is exactly what a linter is right to flag.
s3 = _inbox_api.s3
inbox_settings = _inbox_api.inbox_settings
inbox_app = _inbox_api.inbox_app
owner_client = _inbox_api.owner_client

# --------------------------------------------------------------------------- #
# A trip, its days, one booked-by-hand hotel
# --------------------------------------------------------------------------- #


class World:
    def __init__(self, db: OrmSession, owner: Owner) -> None:
        self.db = db
        self.owner = owner
        self.trip = make_trip(owner)
        db.add(self.trip)
        db.flush()
        self.days: dict[date, TripDay] = {}
        current = self.trip.start_date
        while current <= self.trip.end_date:
            day = TripDay(trip_id=self.trip.id, date=current)
            db.add(day)
            self.days[current] = day
            current += timedelta(days=1)
        db.flush()
        self.hotel = make_item(
            self.days[date(2026, 10, 17)],
            title="Hotel Majestic",
            confirmation_number="HM-77",
            notes="Ask for a quiet room",
        )
        db.add(self.hotel)
        db.flush()

    def message(self, **overrides: object) -> InboundMessage:
        values: dict[str, object] = {"state": "routed", "trip_id": self.trip.id}
        values.update(overrides)
        return make_message(self.db, self.owner, **values)

    def document(self, message: InboundMessage, name: str = "voucher.pdf") -> Attachment:
        data = make_pdf()
        attachment = Attachment(
            inbound_message_id=message.id,
            filename=name,
            content_type="application/pdf",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
        self.db.add(attachment)
        self.db.flush()
        return attachment

    def propose(
        self, message: InboundMessage | None = None, **fields: Any
    ) -> InboundActionItem:
        message = message or self.message()
        action_item = approvals.propose_from_routing(
            self.db,
            message,
            owner=self.owner,
            fields=ExtractedFields.model_validate(fields),
        )
        assert action_item is not None
        return action_item


@pytest.fixture
def world(db_session: OrmSession, owner: Owner) -> World:
    return World(db_session, owner)


@pytest.fixture
def quota() -> Iterator[None]:
    previous = get_upload_quota()
    yield
    set_upload_quota(previous)


def approve(client: TestClient, action_item: InboundActionItem, **body: Any) -> Any:
    payload: dict[str, Any] = {"expected_revision": action_item.revision}
    payload.update(body)
    return client.post(f"{INBOX}/action-items/{action_item.id}/approve", json=payload)


def fresh(db: OrmSession, model: type, row_id: uuid.UUID) -> Any:
    db.expire_all()
    return db.get(model, row_id)


# --------------------------------------------------------------------------- #
# Step 4 — created from routing, aimed deterministically
# --------------------------------------------------------------------------- #


def test_one_confirmation_number_match_proposes_an_update(world: World) -> None:
    action_item = world.propose(confirmation_number="hm 77", cost_amount="480", cost_currency="MYR")

    assert (action_item.kind, action_item.target_item_id) == ("update_item", world.hotel.id)
    assert approvals.read_proposal(action_item).target_reason == "matched_confirmation_number"


def test_a_unique_title_and_day_match_proposes_an_update(world: World) -> None:
    action_item = world.propose(title="hotel  majestic", start_date="2026-10-17")

    assert (action_item.kind, action_item.target_item_id) == ("update_item", world.hotel.id)


def test_no_match_proposes_a_new_item_on_the_extracted_day(world: World) -> None:
    action_item = world.propose(
        title="Ferry to Langkawi", kind="spaceship", start_date="2026-10-19"
    )

    assert action_item.kind == "create_item"
    assert action_item.target_trip_day_id == world.days[date(2026, 10, 19)].id
    # The unknown kind was dropped, not proposed; approval falls back to `other`.
    assert approvals.read_proposal(action_item).proposed.kind is None


def test_several_matches_wait_for_the_owner(world: World) -> None:
    world.db.add(
        make_item(world.days[date(2026, 10, 18)], title="Again", confirmation_number="HM77")
    )
    world.db.flush()

    action_item = world.propose(confirmation_number="HM-77")

    assert (action_item.kind, action_item.target_item_id) == ("update_item", None)


def test_no_usable_day_waits_for_the_owner(world: World) -> None:
    action_item = world.propose(title="Somewhere", start_date="2027-01-01")

    assert (action_item.kind, action_item.target_trip_day_id) == ("create_item", None)


def test_an_item_on_another_trip_never_matches(world: World, db_session: OrmSession) -> None:
    other = make_trip(world.owner, title="Another trip")
    db_session.add(other)
    db_session.flush()
    other_day = TripDay(trip_id=other.id, date=other.start_date)
    db_session.add(other_day)
    db_session.flush()
    db_session.add(make_item(other_day, title="Elsewhere", confirmation_number="ZZ-1"))
    db_session.flush()

    action_item = world.propose(confirmation_number="ZZ-1", start_date="2026-10-12")

    assert action_item.kind == "create_item"


def test_a_message_with_nothing_to_propose_produces_no_action_item(world: World) -> None:
    message = world.message()

    assert approvals.propose_from_routing(
        world.db, message, owner=world.owner, fields=ExtractedFields()
    ) is None


def test_proposing_writes_nothing_to_the_plan(world: World) -> None:
    before = (world.hotel.title, world.hotel.confirmation_number, world.hotel.status)
    world.propose(
        confirmation_number="HM-77", title="Overwritten?", cost_amount="1", cost_currency="EUR"
    )

    hotel = fresh(world.db, Item, world.hotel.id)
    assert (hotel.title, hotel.confirmation_number, hotel.status) == before
    assert hotel.cost_amount is None


def test_the_document_only_case_is_an_owner_proposal_with_zero_fields(
    world: World, owner_client: TestClient
) -> None:
    message = world.message()
    document = world.document(message)

    created = owner_client.post(
        f"{INBOX}/messages/{message.id}/action-items",
        json={"target_item_id": str(world.hotel.id)},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["kind"], body["fields"], body["status"]) == ("update_item", [], None)
    assert [one["id"] for one in body["attachments"]] == [str(document.id)]

    approved = owner_client.post(
        f"{INBOX}/action-items/{body['id']}/approve",
        json={"attachment_ids": [str(document.id)], "expected_revision": body["revision"]},
    )
    assert approved.status_code == 200, approved.text
    moved = fresh(world.db, Attachment, document.id)
    assert (moved.item_id, moved.inbound_message_id) == (world.hotel.id, None)


def test_the_summary_counts_only_pending_items(world: World, owner_client: TestClient) -> None:
    world.propose(title="One", start_date="2026-10-19")
    rejected = world.propose(title="Two", start_date="2026-10-20")
    rejected.state = "rejected"
    world.db.flush()

    assert owner_client.get(f"{INBOX}/summary").json()["pending_action_items"] == 1


# --------------------------------------------------------------------------- #
# Step 5 — approve
# --------------------------------------------------------------------------- #


def test_the_view_ticks_empty_fields_and_leaves_typed_ones_unticked(
    world: World, owner_client: TestClient
) -> None:
    action_item = world.propose(
        confirmation_number="HM-77",
        title="Majestic Hotel KL",
        cost_amount="480.00",
        cost_currency="MYR",
    )

    body = owner_client.get(f"{INBOX}/action-items/{action_item.id}").json()
    rows = {row["name"]: row for row in body["fields"]}

    assert rows["title"]["default_ticked"] is False
    assert rows["title"]["current"] == "Hotel Majestic"
    assert rows["cost"]["default_ticked"] is True
    assert rows["cost"]["proposed"] == {"amount": "480.00", "currency": "MYR"}
    assert rows["confirmation_number"]["changed"] is False
    assert body["status"] == {
        "current": "to_plan",
        "proposed": "done",
        "changed": True,
        "default_ticked": True,
    }


def test_only_the_named_fields_are_written(world: World, owner_client: TestClient) -> None:
    action_item = world.propose(
        confirmation_number="HM-77",
        title="Majestic Hotel KL",
        start_time="15:00",
        cost_amount="480.00",
        cost_currency="MYR",
    )

    response = approve(owner_client, action_item, fields=["cost"], set_status="done")

    assert response.status_code == 200, response.text
    hotel = fresh(world.db, Item, world.hotel.id)
    assert (hotel.cost_amount, hotel.cost_currency) == (Decimal("480.00"), "MYR")
    assert hotel.status == "done"
    # Claimed but not named: untouched. Never claimed: untouched.
    assert hotel.title == "Hotel Majestic"
    assert hotel.start_time is None
    assert hotel.notes == "Ask for a quiet room"
    assert response.json()["state"] == "approved"


def test_a_changed_field_refuses_the_whole_approval_and_reloads_fresh_values(
    world: World, owner_client: TestClient
) -> None:
    action_item = world.propose(
        confirmation_number="HM-77", title="Majestic", cost_amount="480", cost_currency="MYR"
    )
    world.hotel.title = "Edited in another tab"
    world.db.flush()
    opened_at = action_item.revision

    response = approve(owner_client, action_item, fields=["title", "cost"])

    assert response.status_code == 409
    assert response.json()["error"] == {"code": "action_item_conflict", "field": "title"}
    hotel = fresh(world.db, Item, world.hotel.id)
    assert hotel.title == "Edited in another tab"
    assert hotel.cost_amount is None

    reloaded = owner_client.get(f"{INBOX}/action-items/{action_item.id}").json()
    assert reloaded["revision"] == opened_at + 1
    rows = {row["name"]: row for row in reloaded["fields"]}
    assert rows["title"]["current"] == "Edited in another tab"

    again = owner_client.post(
        f"{INBOX}/action-items/{action_item.id}/approve",
        json={"fields": ["title"], "expected_revision": reloaded["revision"]},
    )
    assert again.status_code == 200, again.text
    assert fresh(world.db, Item, world.hotel.id).title == "Majestic"


def test_a_stale_revision_is_refused_and_writes_nothing(
    world: World, owner_client: TestClient
) -> None:
    action_item = world.propose(confirmation_number="HM-77", cost_amount="480", cost_currency="MYR")

    response = owner_client.post(
        f"{INBOX}/action-items/{action_item.id}/approve",
        json={"fields": ["cost"], "expected_revision": action_item.revision + 7},
    )

    assert response.status_code == 409
    assert response.json()["error"]["field"] == "revision"
    assert fresh(world.db, Item, world.hotel.id).cost_amount is None


def test_a_second_approval_is_refused(world: World, owner_client: TestClient) -> None:
    action_item = world.propose(confirmation_number="HM-77", cost_amount="480", cost_currency="MYR")
    assert approve(owner_client, action_item, fields=["cost"]).status_code == 200

    second = approve(owner_client, action_item, fields=["cost"])

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "action_item_already_decided"


def test_approving_only_the_document_changes_no_field(
    world: World, owner_client: TestClient
) -> None:
    message = world.message()
    document = world.document(message)
    action_item = world.propose(
        message, confirmation_number="HM-77", title="Changed?", cost_amount="1", cost_currency="EUR"
    )

    response = approve(owner_client, action_item, attachment_ids=[str(document.id)])

    assert response.status_code == 200, response.text
    hotel = fresh(world.db, Item, world.hotel.id)
    assert (hotel.title, hotel.cost_amount, hotel.status) == ("Hotel Majestic", None, "to_plan")
    assert fresh(world.db, Attachment, document.id).item_id == world.hotel.id


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"fields": ["notes"]}, "notes"),
        ({"fields": ["start_time"]}, "start_time"),
        ({"set_status": "maybe"}, "set_status"),
        ({"attachment_ids": [str(uuid.uuid4())]}, "attachment_ids"),
    ],
)
def test_a_selection_outside_the_proposal_is_refused(
    world: World, owner_client: TestClient, body: dict[str, Any], field: str
) -> None:
    action_item = world.propose(confirmation_number="HM-77", cost_amount="1", cost_currency="EUR")

    response = approve(owner_client, action_item, **body)

    assert response.status_code == 422
    assert response.json()["error"] == {"code": "invalid_action_selection", "field": field}


def test_an_unknown_body_key_is_refused(world: World, owner_client: TestClient) -> None:
    action_item = world.propose(confirmation_number="HM-77", cost_amount="1", cost_currency="EUR")

    assert approve(owner_client, action_item, overwrite_everything=True).status_code == 422


def test_exceeding_the_trip_quota_refuses_and_leaves_the_document_in_the_inbox(
    world: World, owner_client: TestClient, quota: None
) -> None:
    message = world.message()
    document = world.document(message)
    action_item = world.propose(message, confirmation_number="HM-77")
    set_upload_quota(UploadQuota(max_trip_bytes=document.byte_size - 1))

    response = approve(owner_client, action_item, attachment_ids=[str(document.id)])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "trip_storage_quota_exceeded"
    world.db.expire_all()
    still = world.db.get(Attachment, document.id)
    assert (still.inbound_message_id, still.item_id) == (message.id, None)
    assert world.db.get(InboundActionItem, action_item.id).state == "pending"


def test_a_twenty_first_attachment_is_refused(
    world: World, owner_client: TestClient, quota: None
) -> None:
    set_upload_quota(UploadQuota(max_attachments_per_parent=1))
    data = make_pdf()
    world.db.add(
        Attachment(
            item_id=world.hotel.id,
            filename="already.pdf",
            content_type="application/pdf",
            byte_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )
    )
    message = world.message()
    document = world.document(message)
    action_item = world.propose(message, confirmation_number="HM-77")

    response = approve(owner_client, action_item, attachment_ids=[str(document.id)])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "attachment_limit_reached"
    assert fresh(world.db, Attachment, document.id).inbound_message_id == message.id


def test_approving_a_new_item_creates_it_with_the_ticked_fields(
    world: World, owner_client: TestClient
) -> None:
    action_item = world.propose(
        title="Ferry to Langkawi",
        kind="transport",
        start_date="2026-10-19",
        start_time="09:30",
        confirmation_number="FR-1",
    )

    response = approve(
        owner_client,
        action_item,
        fields=["title", "kind", "start_time"],
        set_status="done",
    )

    assert response.status_code == 200, response.text
    item_id = uuid.UUID(response.json()["applied"]["item_id"])
    item = fresh(world.db, Item, item_id)
    assert item.trip_day_id == world.days[date(2026, 10, 19)].id
    assert (item.title, item.kind, item.start_time, item.status) == (
        "Ferry to Langkawi",
        "transport",
        time(9, 30),
        "done",
    )
    assert item.confirmation_number is None


def test_an_impossible_resulting_span_is_refused(world: World, owner_client: TestClient) -> None:
    world.hotel.start_time = time(18, 0)
    world.db.flush()
    action_item = world.propose(confirmation_number="HM-77", end_time="09:00")

    response = approve(owner_client, action_item, fields=["end_time"])

    assert response.status_code == 422
    assert fresh(world.db, Item, world.hotel.id).end_time is None


def test_a_target_the_server_did_not_record_is_refused(
    world: World, owner_client: TestClient
) -> None:
    other = make_item(world.days[date(2026, 10, 18)], title="Other")
    world.db.add(other)
    world.db.flush()
    action_item = world.propose(confirmation_number="HM-77", cost_amount="1", cost_currency="EUR")

    response = approve(owner_client, action_item, fields=["cost"], target_item_id=str(other.id))

    assert response.status_code == 409
    assert response.json()["error"]["field"] == "target_item_id"
    assert fresh(world.db, Item, other.id).cost_amount is None


def test_a_proposal_waiting_for_a_target_cannot_be_approved(
    world: World, owner_client: TestClient
) -> None:
    action_item = world.propose(title="Somewhere", start_date="2027-01-01")

    response = approve(owner_client, action_item, fields=["title"])

    assert response.status_code == 422
    assert response.json()["error"]["field"] == "target"


def test_another_owners_action_item_is_not_found(
    world: World, owner_client: TestClient, other_owner: Owner, db_session: OrmSession
) -> None:
    theirs = World(db_session, other_owner).propose(title="Theirs", start_date="2026-10-19")

    assert owner_client.get(f"{INBOX}/action-items/{theirs.id}").status_code == 404
    assert approve(owner_client, theirs, fields=["title"]).status_code == 404


# --------------------------------------------------------------------------- #
# Step 6 — reject, undo, re-target
# --------------------------------------------------------------------------- #


def test_reject_destroys_nothing(world: World, owner_client: TestClient) -> None:
    message = world.message()
    document = world.document(message)
    action_item = world.propose(
        message, confirmation_number="HM-77", cost_amount="1", cost_currency="EUR"
    )

    response = owner_client.post(f"{INBOX}/action-items/{action_item.id}/reject")

    assert response.status_code == 204
    assert fresh(world.db, InboundActionItem, action_item.id).state == "rejected"
    assert fresh(world.db, Attachment, document.id).inbound_message_id == message.id
    assert owner_client.get(f"{INBOX}/messages/{message.id}").status_code == 200
    assert fresh(world.db, Item, world.hotel.id).cost_amount is None
    assert (
        owner_client.post(f"{INBOX}/action-items/{action_item.id}/reject").status_code == 409
    )


def test_undo_restores_exactly_the_prior_values(world: World, owner_client: TestClient) -> None:
    message = world.message()
    document = world.document(message)
    action_item = world.propose(
        message,
        confirmation_number="HM-77",
        title="Majestic",
        cost_amount="480",
        cost_currency="MYR",
    )
    assert approve(
        owner_client,
        action_item,
        fields=["title", "cost"],
        attachment_ids=[str(document.id)],
        set_status="done",
    ).status_code == 200

    response = owner_client.post(f"{INBOX}/action-items/{action_item.id}/undo")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "pending"
    hotel = fresh(world.db, Item, world.hotel.id)
    assert (hotel.title, hotel.cost_amount, hotel.cost_currency, hotel.status) == (
        "Hotel Majestic",
        None,
        None,
        "to_plan",
    )
    restored = fresh(world.db, Attachment, document.id)
    assert (restored.item_id, restored.inbound_message_id) == (None, message.id)


def test_undo_after_an_unrelated_edit_to_the_same_field_refuses(
    world: World, owner_client: TestClient
) -> None:
    action_item = world.propose(confirmation_number="HM-77", title="Majestic")
    assert approve(owner_client, action_item, fields=["title"]).status_code == 200
    hotel = fresh(world.db, Item, world.hotel.id)
    hotel.title = "Renamed by hand afterwards"
    world.db.flush()

    response = owner_client.post(f"{INBOX}/action-items/{action_item.id}/undo")

    assert response.status_code == 409
    assert response.json()["error"] == {"code": "action_item_conflict", "field": "title"}
    assert fresh(world.db, Item, world.hotel.id).title == "Renamed by hand afterwards"


def test_undo_of_a_created_item_removes_it(world: World, owner_client: TestClient) -> None:
    action_item = world.propose(title="Ferry", start_date="2026-10-19")
    approved = approve(owner_client, action_item, fields=["title"]).json()
    item_id = uuid.UUID(approved["applied"]["item_id"])

    response = owner_client.post(f"{INBOX}/action-items/{action_item.id}/undo")

    assert response.status_code == 200, response.text
    world.db.expire_all()
    assert world.db.scalar(sa.select(sa.func.count()).where(Item.id == item_id)) == 0


def test_undo_of_something_not_approved_is_refused(world: World, owner_client: TestClient) -> None:
    action_item = world.propose(title="Ferry", start_date="2026-10-19")

    response = owner_client.post(f"{INBOX}/action-items/{action_item.id}/undo")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "action_item_already_decided"


def test_retarget_resnapshots_and_bumps_the_revision(
    world: World, owner_client: TestClient
) -> None:
    other = make_item(
        world.days[date(2026, 10, 18)],
        title="Other hotel",
        cost_amount=Decimal("5"),
        cost_currency="EUR",
    )
    world.db.add(other)
    world.db.flush()
    action_item = world.propose(confirmation_number="HM-77", cost_amount="480", cost_currency="MYR")
    old_revision = action_item.revision

    response = owner_client.post(
        f"{INBOX}/action-items/{action_item.id}/retarget",
        json={"target_item_id": str(other.id), "expected_revision": old_revision},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == old_revision + 1
    assert body["target_item_id"] == str(other.id)
    cost = next(row for row in body["fields"] if row["name"] == "cost")
    assert cost["current"] == {"amount": "5.00", "currency": "EUR"}
    assert cost["default_ticked"] is False

    stale = owner_client.post(
        f"{INBOX}/action-items/{action_item.id}/approve",
        json={"fields": ["cost"], "expected_revision": old_revision},
    )
    assert stale.status_code == 409


def test_retarget_to_a_day_turns_an_update_into_a_new_item(
    world: World, owner_client: TestClient
) -> None:
    action_item = world.propose(confirmation_number="HM-77", title="Late checkout")
    day = world.days[date(2026, 10, 20)]

    response = owner_client.post(
        f"{INBOX}/action-items/{action_item.id}/retarget",
        json={"target_trip_day_id": str(day.id), "expected_revision": action_item.revision},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["kind"], body["target_date"]) == ("create_item", "2026-10-20")


def test_retarget_onto_another_owners_item_is_refused(
    world: World, owner_client: TestClient, other_owner: Owner, db_session: OrmSession
) -> None:
    theirs = World(db_session, other_owner)
    action_item = world.propose(confirmation_number="HM-77", title="x")

    response = owner_client.post(
        f"{INBOX}/action-items/{action_item.id}/retarget",
        json={"target_item_id": str(theirs.hotel.id), "expected_revision": action_item.revision},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_action_selection"


def test_placing_a_message_on_another_trip_supersedes_its_proposal(
    world: World, owner_client: TestClient, db_session: OrmSession
) -> None:
    other = make_trip(world.owner, title="Other")
    db_session.add(other)
    db_session.flush()
    message = world.message()
    action_item = world.propose(message, title="Ferry", start_date="2026-10-19")

    response = owner_client.post(
        f"{INBOX}/messages/{message.id}/place", json={"trip_id": str(other.id)}
    )

    assert response.status_code == 200, response.text
    assert fresh(db_session, InboundActionItem, action_item.id).state == "superseded"


def test_the_message_detail_names_its_action_items(world: World, owner_client: TestClient) -> None:
    message = world.message()
    action_item = world.propose(message, title="Ferry", start_date="2026-10-19")

    body = owner_client.get(f"{INBOX}/messages/{message.id}").json()

    assert body["action_item_ids"] == [str(action_item.id)]


def test_deleting_the_trip_removes_a_create_proposal_and_keeps_the_message(
    world: World, db_session: OrmSession
) -> None:
    message = world.message()
    action_item = world.propose(message, title="Ferry", start_date="2026-10-19")
    action_item_id, message_id = action_item.id, message.id

    db_session.execute(sa.delete(Trip).where(Trip.id == world.trip.id))
    db_session.expire_all()

    assert db_session.scalar(
        sa.select(sa.func.count()).where(InboundActionItem.id == action_item_id)
    ) == 0
    survivor = db_session.get(InboundMessage, message_id)
    assert survivor is not None and survivor.trip_id is None


def test_undo_of_a_created_item_refuses_once_the_owner_has_added_to_it(
    world: World, owner_client: TestClient
) -> None:
    """Regression: undo used to delete a created item along with the owner's later notes."""
    action_item = world.propose(title="Ferry", start_date="2026-10-19")
    approved = approve(owner_client, action_item, fields=["title"]).json()
    item_id = uuid.UUID(approved["applied"]["item_id"])
    created = fresh(world.db, Item, item_id)
    created.notes = "Seat 12A, gate B"
    created.kind = "transport"
    world.db.flush()

    response = owner_client.post(f"{INBOX}/action-items/{action_item.id}/undo")

    assert response.status_code == 409
    assert response.json()["error"] == {"code": "action_item_conflict", "field": "item"}
    kept = fresh(world.db, Item, item_id)
    assert kept is not None and kept.notes == "Seat 12A, gate B"


def test_undo_supersedes_a_newer_proposal_for_the_same_message(
    world: World, owner_client: TestClient
) -> None:
    """Regression: undo could leave two pending, approvable proposals for one message."""
    message = world.message()
    world.document(message)
    first = world.propose(message, title="Ferry", start_date="2026-10-19")
    assert approve(owner_client, first, fields=["title"]).status_code == 200
    second = owner_client.post(
        f"{INBOX}/messages/{message.id}/action-items",
        json={"target_item_id": str(world.hotel.id)},
    ).json()

    assert owner_client.post(f"{INBOX}/action-items/{first.id}/undo").status_code == 200

    assert fresh(world.db, InboundActionItem, uuid.UUID(second["id"])).state == "superseded"
    assert owner_client.get(f"{INBOX}/summary").json()["pending_action_items"] == 1
