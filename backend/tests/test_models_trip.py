"""The trip tables' constraints, asserted against the database rather than the ORM.

These tests deliberately go through `db_session.flush()` and read the exception
PostgreSQL raises. Validating the same rules in Pydantic would be a test of the
API layer; the point here is that the *database* refuses, so a future write path
that forgets the check — a management command, a migration backfill, a second
service — still cannot produce a trip whose dates run backwards.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import Owner, Trip, TripDay, TripStage, normalise_place


@contextmanager
def rejected_by(db_session: OrmSession, constraint: str) -> Iterator[None]:
    """Assert the database refuses the enclosed write, naming the constraint.

    The write runs inside a SAVEPOINT: a failed statement poisons its transaction
    in PostgreSQL, and without the savepoint the fixture's outer rollback would
    then fail in teardown, reporting an error against a test that actually passed.
    """
    with pytest.raises(IntegrityError, match=constraint), db_session.begin_nested():
        yield
        db_session.flush()


def make_trip(owner: Owner, **overrides: object) -> Trip:
    fields: dict[str, object] = {
        "owner_id": owner.id,
        "title": "Malezja, październik 2026",
        "start_date": date(2026, 10, 10),
        "end_date": date(2026, 10, 24),
        "departure_place": "Warszawa",
        "return_place": "Katowice",
    }
    fields.update(overrides)
    return Trip(**fields)


def test_database_rejects_an_inverted_trip_date_range(
    db_session: OrmSession, owner: Owner
) -> None:
    """`ck_trip_date_range` — a trip that ends before it starts is not a trip."""
    with rejected_by(db_session, "ck_trip_date_range"):
        db_session.add(
            make_trip(owner, start_date=date(2026, 10, 24), end_date=date(2026, 10, 10))
        )


def test_database_rejects_a_duplicate_day_for_one_trip(
    db_session: OrmSession, owner: Owner
) -> None:
    """`uq_trip_day_date` — the timeline must not be able to show one date twice."""
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()

    db_session.add(TripDay(trip_id=trip.id, date=date(2026, 10, 11)))
    db_session.flush()

    with rejected_by(db_session, "uq_trip_day_date"):
        db_session.add(TripDay(trip_id=trip.id, date=date(2026, 10, 11)))


def test_the_same_date_is_allowed_on_two_different_trips(
    db_session: OrmSession, owner: Owner
) -> None:
    """The uniqueness is per trip, not global — two trips can overlap in time."""
    first = make_trip(owner)
    second = make_trip(owner, title="Portugalia")
    db_session.add_all([first, second])
    db_session.flush()

    db_session.add_all(
        [
            TripDay(trip_id=first.id, date=date(2026, 10, 11)),
            TripDay(trip_id=second.id, date=date(2026, 10, 11)),
        ]
    )
    db_session.flush()  # no exception


def test_database_rejects_an_inverted_stage_date_range(
    db_session: OrmSession, owner: Owner
) -> None:
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()

    with rejected_by(db_session, "ck_trip_stage_date_range"):
        db_session.add(
            TripStage(
                trip_id=trip.id,
                position=0,
                place="Kuala Lumpur",
                start_date=date(2026, 10, 20),
                end_date=date(2026, 10, 12),
            )
        )


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (None, None),
        (date(2026, 10, 10), None),
        (None, date(2026, 10, 14)),
    ],
    ids=["no dates at all", "start only", "end only"],
)
def test_a_stage_may_have_partial_or_no_dates(
    db_session: OrmSession, owner: Owner, start: date | None, end: date | None
) -> None:
    """R03 asks the form for the *trip's* dates; a stage's own range is optional.

    A traveller who knows the bases but not yet how to split the days must still be
    able to create the trip. Such a stage simply labels no day.
    """
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()

    db_session.add(
        TripStage(trip_id=trip.id, position=0, place="Penang", start_date=start, end_date=end)
    )
    db_session.flush()  # no exception


def test_database_rejects_a_duplicate_stage_position(
    db_session: OrmSession, owner: Owner
) -> None:
    """`uq_trip_stage_position` still refuses a genuine duplicate.

    The constraint is DEFERRABLE INITIALLY DEFERRED, so PostgreSQL checks it at
    COMMIT rather than at statement time. `SET CONSTRAINTS ... IMMEDIATE` brings
    that check forward into this test's transaction, which the surrounding suite
    never commits. Without this test the deferral could be read as *disabling* the
    uniqueness rather than postponing it.
    """
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    db_session.execute(sa.text("SET CONSTRAINTS uq_trip_stage_position IMMEDIATE"))

    with rejected_by(db_session, "uq_trip_stage_position"):
        db_session.add_all(
            [
                TripStage(trip_id=trip.id, position=0, place="Kuala Lumpur"),
                TripStage(trip_id=trip.id, position=0, place="Penang"),
            ]
        )

    db_session.execute(sa.text("SET CONSTRAINTS uq_trip_stage_position DEFERRED"))


def test_stage_positions_may_collide_mid_transaction(
    db_session: OrmSession, owner: Owner
) -> None:
    """The reason the constraint is deferred at all.

    Swapping two stages' positions takes two UPDATEs, and after the first one both
    rows hold the same position. Under an ordinary UNIQUE constraint that
    intermediate state is fatal and every reorder would need a temporary sentinel
    value. This is what Phase 4's dense renumbering relies on.
    """
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()

    first = TripStage(trip_id=trip.id, position=0, place="Kuala Lumpur")
    second = TripStage(trip_id=trip.id, position=1, place="Penang")
    db_session.add_all([first, second])
    db_session.flush()

    first.position = 1  # both rows are now at position 1 …
    db_session.flush()
    second.position = 0  # … and only now is the state legal again
    db_session.flush()

    db_session.expire_all()
    assert [stage.place for stage in db_session.get_one(Trip, trip.id).stages] == [
        "Penang",
        "Kuala Lumpur",
    ]


def test_stages_may_share_a_boundary_date(db_session: OrmSession, owner: Owner) -> None:
    """There is deliberately no non-overlap constraint (spec, `trip_stage`).

    The design export's own example has Delhi (10.11–13.11) and Agra (13.11–17.11)
    both containing the 13th, because the 13th is the travel day between them.
    """
    trip = make_trip(owner, start_date=date(2026, 11, 10), end_date=date(2026, 11, 17))
    db_session.add(trip)
    db_session.flush()

    db_session.add_all(
        [
            TripStage(
                trip_id=trip.id,
                position=0,
                place="Delhi",
                start_date=date(2026, 11, 10),
                end_date=date(2026, 11, 13),
            ),
            TripStage(
                trip_id=trip.id,
                position=1,
                place="Agra & Jaipur",
                start_date=date(2026, 11, 13),
                end_date=date(2026, 11, 17),
            ),
        ]
    )
    db_session.flush()  # no exception


def test_deleting_a_trip_cascades_to_its_stages_and_days(
    db_session: OrmSession, owner: Owner
) -> None:
    trip = make_trip(owner)
    db_session.add(trip)
    db_session.flush()
    db_session.add_all(
        [
            TripStage(trip_id=trip.id, position=0, place="Kuala Lumpur"),
            TripDay(trip_id=trip.id, date=date(2026, 10, 10)),
        ]
    )
    db_session.flush()
    trip_id = trip.id

    db_session.delete(trip)
    db_session.flush()

    assert db_session.query(TripStage).filter_by(trip_id=trip_id).count() == 0
    assert db_session.query(TripDay).filter_by(trip_id=trip_id).count() == 0


def test_a_trip_needs_a_real_owner(db_session: OrmSession) -> None:
    """Every query scopes on `owner_id`; an orphan trip would be unreachable."""
    with rejected_by(db_session, "trip_owner_id_fkey"):
        db_session.add(
            Trip(
                owner_id=uuid.uuid4(),
                title="Nowhere",
                start_date=date(2026, 10, 10),
                end_date=date(2026, 10, 11),
                departure_place="Warszawa",
            )
        )


class TestRouteModeDerivation:
    """The three route modes are derived from `return_place`, not stored."""

    def test_null_return_place_is_one_way(self, owner: Owner) -> None:
        trip = make_trip(owner, return_place=None)
        assert trip.is_round_trip is False

    def test_matching_return_place_is_a_round_trip(self, owner: Owner) -> None:
        trip = make_trip(owner, departure_place="Warszawa", return_place="Warszawa")
        assert trip.is_round_trip is True

    def test_a_different_return_place_is_open_jaw(self, owner: Owner) -> None:
        trip = make_trip(owner, departure_place="Warszawa", return_place="Katowice")
        assert trip.is_round_trip is False

    @pytest.mark.parametrize(
        "return_place",
        ["Warszawa ", " warszawa", "WARSZAWA", "Warszawa\t"],
        ids=["trailing space", "leading space and case", "upper case", "tab"],
    )
    def test_the_comparison_survives_what_a_human_types(
        self, owner: Owner, return_place: str
    ) -> None:
        """Without normalisation, a trailing space would read as an open-jaw trip."""
        trip = make_trip(owner, departure_place="Warszawa", return_place=return_place)
        assert trip.is_round_trip is True


class TestNormalisePlace:
    def test_it_folds_case_and_collapses_whitespace(self) -> None:
        assert normalise_place("  Kuala   Lumpur  ") == "kuala lumpur"

    def test_it_is_only_a_comparison_form(self) -> None:
        """What is stored is what the owner typed — the header shows it back."""
        assert normalise_place("Warszawa") == normalise_place("warszawa")
        assert normalise_place("Warszawa") != "Warszawa"
