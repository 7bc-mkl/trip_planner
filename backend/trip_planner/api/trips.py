"""Trip endpoints: the list, the creator, and the timeline payload.

The response models live in `api/schemas.py`, shared with the item router — the
timeline payload embeds items and the day-detail payload embeds stages, so any
other arrangement makes the two routers import each other.

There are no filter query parameters here. A11 puts filtering in the browser and
the timeline payload is complete, so `?status=` would be a contract surface with
no caller.
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import selectinload

from trip_planner.api.deps import CurrentOwner, DbSession, OwnedTrip
from trip_planner.api.schemas import (
    DayRead,
    ItemRead,
    ReadinessRead,
    StageRead,
    TripDetail,
    TripSummary,
)
from trip_planner.db.models import Item, Trip, TripDay, TripStage
from trip_planner.domain.days import generate_days
from trip_planner.domain.items import sorted_items
from trip_planner.domain.readiness import readiness
from trip_planner.domain.stages import stages_for_day, validate_stage_range
from trip_planner.errors import ApiError, ErrorCode

router = APIRouter(prefix="/trips", tags=["trips"])

#: Free-text fields are bounded so a paste accident cannot store a megabyte. The
#: limits are generous enough that no real title or place name reaches them.
TITLE_MAX = 200
PLACE_MAX = 200


class StageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place: str = Field(min_length=1, max_length=PLACE_MAX)
    #: Optional by design (R03): a base whose days are undecided is still a base.
    start_date: date | None = None
    end_date: date | None = None


class TripCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=TITLE_MAX)
    start_date: date
    end_date: date
    departure_place: str = Field(min_length=1, max_length=PLACE_MAX)
    #: NULL means one-way. Omitting the field and sending null are the same thing.
    return_place: str | None = Field(default=None, max_length=PLACE_MAX)
    #: Deliberately not `min_length=1`: an empty list must answer the specific
    #: `stages_required` code rather than a generic `validation_error`, because the
    #: creator surfaces it against the stage list rather than against a field.
    stages: list[StageCreate] = Field(default_factory=list)


class TripUpdate(BaseModel):
    """A partial update. Every field is optional.

    `return_place` is nullable and its absence is meaningful, so which keys were
    sent is read from `model_fields_set`: omitting it lets the mode-stability
    rule run, while sending `null` is an explicit switch to one-way.
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    start_date: date | None = None
    end_date: date | None = None
    departure_place: str | None = Field(default=None, min_length=1, max_length=PLACE_MAX)
    return_place: str | None = Field(default=None, max_length=PLACE_MAX)


def all_items(trip: Trip) -> list[Item]:
    """Every item of the trip, across its days.

    The readiness arithmetic is over the whole trip, not a day, so both payloads
    flatten the days here rather than each summing their own way.
    """
    return [item for day in trip.days for item in day.items]


def summary(trip: Trip) -> TripSummary:
    """A list row, with its counter."""
    arranged, tracked = readiness(all_items(trip))

    return TripSummary(
        id=trip.id,
        title=trip.title,
        start_date=trip.start_date,
        end_date=trip.end_date,
        departure_place=trip.departure_place,
        return_place=trip.return_place,
        readiness=ReadinessRead(arranged=arranged, tracked=tracked),
    )


def timeline(trip: Trip) -> TripDetail:
    """Build the timeline payload, deriving each day's stages once.

    Everything is read from the already-loaded relationships, so a trip of any
    length costs the queries `get_owned_trip` already issued rather than one per
    day.
    """
    stages = sorted(trip.stages, key=lambda stage: stage.position)

    return TripDetail(
        **summary(trip).model_dump(),
        stages=[StageRead.model_validate(stage) for stage in stages],
        days=[
            DayRead(
                id=day.id,
                date=day.date,
                stage_ids=[stage.id for stage in stages_for_day(stages, day.date)],
                items=[ItemRead.model_validate(item) for item in sorted_items(day.items)],
            )
            for day in sorted(trip.days, key=lambda day: day.date)
        ],
    )


@router.get("", response_model=list[TripSummary])
def list_trips(db: DbSession, owner: CurrentOwner) -> list[TripSummary]:
    """The owner's trips, soonest first.

    Ordered by start date rather than by creation: the list answers "what is
    coming up", and creation order is an implementation detail of when the owner
    happened to type them in.

    Days and their items are eager-loaded because each row carries a readiness
    counter, which is computed from the trip's items. Lazily loaded, a list of ten
    trips would issue one query per trip and then one per day of each — the
    classic N+1, on the screen the owner opens first.
    """
    trips = db.execute(
        sa.select(Trip)
        .where(Trip.owner_id == owner.id)
        .options(selectinload(Trip.days).selectinload(TripDay.items))
        .order_by(Trip.start_date, Trip.created_at)
    ).scalars()

    return [summary(trip) for trip in trips]


@router.post("", response_model=TripDetail, status_code=status.HTTP_201_CREATED)
def create_trip(payload: TripCreate, db: DbSession, owner: CurrentOwner) -> TripDetail:
    """Create the trip, its stages and its days in one transaction.

    This single call is the design export's "Utwórz pustą oś czasu do ręcznego
    planowania" — the button the whole creator screen exists to deliver. One
    transaction because a trip with no days is not a partial success, it is a
    broken timeline: the request handler's session commits or rolls back as a unit
    (see `get_db`), so a stage validated late cannot leave a half-built trip.

    Validation runs *before* anything is added to the session, so the failure path
    never depends on the rollback being correct.
    """
    if not payload.stages:
        raise ApiError(ErrorCode.STAGES_REQUIRED, field="stages")

    # Raises invalid_date_range or trip_too_long, and gives us the days to insert.
    days = generate_days(payload.start_date, payload.end_date)

    for stage in payload.stages:
        validate_stage_range(
            stage.start_date,
            stage.end_date,
            trip_start=payload.start_date,
            trip_end=payload.end_date,
            place=stage.place,
        )

    trip = Trip(
        owner_id=owner.id,
        title=payload.title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        departure_place=payload.departure_place,
        return_place=payload.return_place,
    )
    trip.stages = [
        TripStage(
            position=position,
            place=stage.place,
            start_date=stage.start_date,
            end_date=stage.end_date,
        )
        for position, stage in enumerate(payload.stages)
    ]
    trip.days = [TripDay(date=day) for day in days]

    db.add(trip)
    db.flush()

    return timeline(trip)


@router.get("/{trip_id}", response_model=TripDetail)
def get_trip(trip: OwnedTrip) -> TripDetail:
    """The timeline payload. Ownership is resolved by the dependency, never here."""
    return timeline(trip)


@router.patch("/{trip_id}", response_model=TripDetail)
def update_trip(trip: OwnedTrip, payload: TripUpdate, db: DbSession) -> TripDetail:
    """Edit a trip's title, dates and places.

    Two rules do the work here, and both exist to stop an edit from destroying
    something the owner did not ask to lose.

    **No item is ever destroyed by a date edit.** Shortening the range past a day
    that carries items answers `409 days_have_items` listing those dates and
    changes *nothing*; shortening past a stage answers `409
    stages_outside_new_range` naming the stages. Days that are empty are removed
    silently, because an empty day carries no decision. Both checks run before
    any mutation, so a refusal cannot leave the trip half-edited.

    **The mode-stability rule.** The route mode is derived from `return_place`, so
    editing `departure_place` on a round trip would silently convert it to
    open-jaw — correcting a typo in the departure city would change what kind of
    trip it is. When the trip is in round-trip mode and `departure_place` changes
    without an explicit `return_place`, the server rewrites `return_place` to
    match, in the same transaction.
    """
    sent = payload.model_fields_set
    start = payload.start_date if payload.start_date is not None else trip.start_date
    end = payload.end_date if payload.end_date is not None else trip.end_date

    # Raises invalid_date_range / trip_too_long before anything is touched.
    wanted_dates = set(generate_days(start, end))

    if start != trip.start_date or end != trip.end_date:
        _refuse_if_days_would_be_lost(trip, wanted_dates)
        _refuse_if_stages_would_escape(trip, start, end)

    # Read the round-trip state *before* departure_place is changed — afterwards
    # the comparison it is derived from no longer describes the trip as it was.
    was_round_trip = trip.is_round_trip

    if payload.title is not None:
        trip.title = payload.title
    if payload.departure_place is not None:
        trip.departure_place = payload.departure_place
    if "return_place" in sent:
        trip.return_place = payload.return_place
    elif was_round_trip and payload.departure_place is not None:
        # The mode-stability rewrite. An explicit return_place always wins: the
        # owner asked for a specific mode and the server must not overrule it.
        trip.return_place = trip.departure_place

    trip.start_date = start
    trip.end_date = end
    _resize_days(db, trip, wanted_dates)
    db.flush()
    db.refresh(trip)

    return timeline(trip)


def _refuse_if_days_would_be_lost(trip: Trip, wanted: set[date]) -> None:
    """409 when a day that would be dropped still carries items."""
    losing = sorted(
        day.date for day in trip.days if day.date not in wanted and len(day.items) > 0
    )

    if losing:
        # The dates are named so the owner knows what to move, rather than being
        # told "somewhere in this trip there is a problem".
        raise ApiError(
            ErrorCode.DAYS_HAVE_ITEMS,
            field=", ".join(day.isoformat() for day in losing),
        )


def _refuse_if_stages_would_escape(trip: Trip, start: date, end: date) -> None:
    """409 when a stage's own range would fall outside the new trip range.

    Symmetric with the rule above: a stage is a decision too, and silently
    truncating or dropping one would lose it.
    """
    escaping = [
        stage.place
        for stage in trip.stages
        if any(
            boundary is not None and not (start <= boundary <= end)
            for boundary in (stage.start_date, stage.end_date)
        )
    ]

    if escaping:
        raise ApiError(ErrorCode.STAGES_OUTSIDE_NEW_RANGE, field=", ".join(escaping))


def _resize_days(db: DbSession, trip: Trip, wanted: set[date]) -> None:
    """Add the days the new range gained and drop the empty ones it lost.

    Only reached once the two refusals above have passed, so every day removed
    here is known to be empty.
    """
    existing = {day.date for day in trip.days}

    for day in list(trip.days):
        if day.date not in wanted:
            db.delete(day)

    for missing in sorted(wanted - existing):
        db.add(TripDay(trip_id=trip.id, date=missing))


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip: OwnedTrip, db: DbSession) -> Response:
    """Delete a trip and everything under it.

    The cascade is the database's (`ON DELETE CASCADE` on stages, days and
    items), so nothing is orphaned even if this handler is bypassed. There is no
    undo in this milestone, which is why the SPA puts a confirmation dialog
    naming the trip in front of this call.
    """
    db.delete(trip)
    db.flush()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
