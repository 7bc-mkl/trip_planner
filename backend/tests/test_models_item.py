"""The `item` table's constraints, asserted against the database.

The status constraint is the one that matters most: R02's arithmetic counts
`done` and `to_book` and excludes `to_plan`, which is only a well-defined sum if
those three are the *only* values that can exist. A test that checked the API
instead would leave the guarantee resting on every write path remembering.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from sqlalchemy.orm import Session as OrmSession

from tests.test_models_trip import make_trip, rejected_by
from trip_planner.db.models import ITEM_KINDS, ITEM_STATUSES, Item, Owner, TripDay


@pytest.fixture
def trip_day(db_session: OrmSession, owner: Owner) -> TripDay:
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    day = TripDay(trip_id=trip.id, date=date(2026, 10, 10))
    db_session.add(day)
    db_session.flush()
    return day


def make_item(day: TripDay, **overrides: object) -> Item:
    fields: dict[str, object] = {
        "trip_day_id": day.id,
        "position": 0,
        "kind": "accommodation",
        "status": "to_plan",
        "title": "Nocleg: Memmo Alfama",
    }
    fields.update(overrides)
    return Item(**fields)


def test_the_database_rejects_a_fourth_status(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    """The constraint that makes R02 structural rather than conventional.

    With a fourth value storable, "arranged out of tracked" stops being a
    well-defined sum, and the number the whole product exists to show becomes a
    guess about what the extra value means.
    """
    with rejected_by(db_session, "ck_item_status"):
        db_session.add(make_item(trip_day, status="maybe"))


@pytest.mark.parametrize("status", ITEM_STATUSES)
def test_each_of_the_three_statuses_is_accepted(
    db_session: OrmSession, trip_day: TripDay, status: str
) -> None:
    db_session.add(make_item(trip_day, status=status))
    db_session.flush()  # no exception


def test_the_database_rejects_an_unknown_kind(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    with rejected_by(db_session, "ck_item_kind"):
        db_session.add(make_item(trip_day, kind="submarine"))


@pytest.mark.parametrize("kind", ITEM_KINDS)
def test_each_declared_kind_is_accepted(
    db_session: OrmSession, trip_day: TripDay, kind: str
) -> None:
    db_session.add(make_item(trip_day, kind=kind))
    db_session.flush()  # no exception


def test_status_defaults_to_to_plan(db_session: OrmSession, trip_day: TripDay) -> None:
    """A new item starts as something the owner has not decided anything about."""
    item = Item(trip_day_id=trip_day.id, position=0, kind="activity", title="Batu Caves")
    db_session.add(item)
    db_session.flush()
    db_session.refresh(item)

    assert item.status == "to_plan"


def test_an_item_may_have_no_times_at_all(db_session: OrmSession, trip_day: TripDay) -> None:
    """"Sometime that day" is a real plan, and the commonest one early on."""
    item = make_item(trip_day, start_time=None, end_time=None, end_date=None)
    db_session.add(item)
    db_session.flush()

    assert item.start_time is None


def test_an_item_may_span_into_a_later_day(db_session: OrmSession, trip_day: TripDay) -> None:
    """The overnight flight the span columns exist for.

    Leaves Warsaw at 23:50 on the 10th, lands in Kuala Lumpur at 14:00 on the
    11th — one item, counted once, not two halves counted twice.
    """
    item = make_item(
        trip_day,
        kind="transport",
        title="LOT LO79 WAW → KUL",
        start_time=time(23, 50),
        end_time=time(14, 0),
        end_date=date(2026, 10, 11),
    )
    db_session.add(item)
    db_session.flush()
    db_session.refresh(item)

    assert item.end_date == date(2026, 10, 11)
    assert item.end_time == time(14, 0)


def test_a_negative_position_is_rejected(db_session: OrmSession, trip_day: TripDay) -> None:
    with rejected_by(db_session, "ck_item_position"):
        db_session.add(make_item(trip_day, position=-1))


def test_two_items_may_share_a_position(db_session: OrmSession, trip_day: TripDay) -> None:
    """Unlike `trip_stage`, there is no uniqueness on position.

    Nothing renumbers items in bulk in this milestone — manual reordering is out
    of scope — so a unique constraint would buy nothing and cost every insert a
    lookup. The ordering rule tolerates a tie.
    """
    db_session.add_all([make_item(trip_day, position=0), make_item(trip_day, position=0)])
    db_session.flush()  # no exception


def test_deleting_a_day_cascades_to_its_items(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    db_session.add(make_item(trip_day))
    db_session.flush()
    day_id = trip_day.id

    db_session.delete(trip_day)
    db_session.flush()

    assert db_session.query(Item).filter_by(trip_day_id=day_id).count() == 0


def test_deleting_a_trip_cascades_all_the_way_to_items(
    db_session: OrmSession, owner: Owner
) -> None:
    """Two levels of cascade — trip → day → item — which a single FK does not prove."""
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    day = TripDay(trip_id=trip.id, date=date(2026, 10, 10))
    db_session.add(day)
    db_session.flush()
    db_session.add(make_item(day))
    db_session.flush()

    db_session.delete(trip)
    db_session.flush()

    assert db_session.query(Item).count() == 0
    assert db_session.query(TripDay).count() == 0


def test_the_status_constant_and_the_constraint_agree(
    db_session: OrmSession, trip_day: TripDay
) -> None:
    """The application's idea of the allowed values must be the database's.

    `ITEM_STATUSES` drives the CHECK clause, the Pydantic literal and the locale
    keys. If the constant grew a value the constraint did not, every one of those
    would accept a status the database refuses — so this asserts the round trip
    for whatever the constant currently says.
    """
    for index, status in enumerate(ITEM_STATUSES):
        db_session.add(make_item(trip_day, position=index, status=status))
    db_session.flush()

    stored = {item.status for item in db_session.query(Item).all()}
    assert stored == set(ITEM_STATUSES)
