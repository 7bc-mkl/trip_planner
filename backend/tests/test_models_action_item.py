"""`inbound_action_item` at the database level.

The constraints are what make D21's "exactly two paths" structural: a third
kind, an unknown state, or an `update_item` that names a day cannot be written
even by a path that forgets the rule.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from tests.test_inbox_api import make_message
from tests.test_models_item import make_item
from tests.test_models_trip import make_trip, rejected_by
from trip_planner.db.models import InboundActionItem, InboundMessage, Item, Owner, TripDay


@pytest.fixture
def day(db_session: OrmSession, owner: Owner) -> TripDay:
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    one = TripDay(trip_id=trip.id, date=trip.start_date)
    db_session.add(one)
    db_session.flush()
    return one


def _action_item(db: OrmSession, owner: Owner, **overrides: Any) -> InboundActionItem:
    message = make_message(db, owner, state="routed")
    values: dict[str, Any] = {
        "inbound_message_id": message.id,
        "owner_id": owner.id,
        "kind": "create_item",
        "proposal": {"fields": {}},
    }
    values.update(overrides)
    return InboundActionItem(**values)


def test_a_valid_action_item_defaults_to_pending_revision_one(
    db_session: OrmSession, owner: Owner, day: TripDay
) -> None:
    row = _action_item(db_session, owner, target_trip_day_id=day.id)
    db_session.add(row)
    db_session.flush()
    db_session.refresh(row)

    assert (row.state, row.revision, row.schema_version) == ("pending", 1, 1)


@pytest.mark.parametrize(
    ("column", "value"),
    [("kind", "delete_item"), ("state", "maybe")],
)
def test_the_database_refuses_an_unknown_kind_or_state(
    db_session: OrmSession, owner: Owner, column: str, value: str
) -> None:
    row = _action_item(db_session, owner)
    db_session.add(row)
    db_session.flush()

    with rejected_by(db_session, f"ck_inbound_action_item_{column}"):
        db_session.execute(
            sa.update(InboundActionItem)
            .where(InboundActionItem.id == row.id)
            .values({column: value})
        )


def test_an_update_item_cannot_name_a_day(
    db_session: OrmSession, owner: Owner, day: TripDay
) -> None:
    row = _action_item(db_session, owner, kind="update_item", target_trip_day_id=day.id)

    with rejected_by(db_session, "ck_inbound_action_item_target_matches_kind"):
        db_session.add(row)


def test_a_create_item_cannot_name_an_item(
    db_session: OrmSession, owner: Owner, day: TripDay
) -> None:
    item = make_item(day)
    db_session.add(item)
    db_session.flush()
    row = _action_item(db_session, owner, kind="create_item", target_item_id=item.id)

    with rejected_by(db_session, "ck_inbound_action_item_target_matches_kind"):
        db_session.add(row)


def test_deleting_the_target_item_takes_the_proposal_with_it(
    db_session: OrmSession, owner: Owner, day: TripDay
) -> None:
    item = make_item(day)
    db_session.add(item)
    db_session.flush()
    row = _action_item(db_session, owner, kind="update_item", target_item_id=item.id)
    db_session.add(row)
    db_session.flush()
    row_id, message_id = row.id, row.inbound_message_id

    db_session.execute(sa.delete(Item).where(Item.id == item.id))
    db_session.expire_all()

    assert db_session.scalar(
        sa.select(sa.func.count()).where(InboundActionItem.id == row_id)
    ) == 0
    assert db_session.scalar(
        sa.select(sa.func.count()).where(InboundMessage.id == message_id)
    ) == 1
