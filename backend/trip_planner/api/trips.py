"""Trip endpoints: the list, the creator, and the timeline payload.

Three shapes of trip come out of this module, and they are separate response
models on purpose rather than one model with optional fields:

- `TripSummary` — a row of `/trips`. Enough to render the list, no days, no stages.
- `TripDetail` — the timeline payload for `/trips/{id}`: the trip, its ordered
  stages, and every day with its **derived** `stage_ids`.

The alternative — one model whose heavy fields are null in list context — makes
"absent because this is the list" indistinguishable from "absent because there
are none", which is exactly the ambiguity BACKWARD_COMPATIBILITY.md warns about.

There are no filter query parameters here. A11 puts filtering in the browser and
the timeline payload is complete, so `?status=` would be a contract surface with
no caller.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from trip_planner.api.deps import CurrentOwner, DbSession, OwnedTrip
from trip_planner.db.models import Trip, TripDay, TripStage
from trip_planner.domain.days import generate_days
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


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    place: str
    start_date: date | None
    end_date: date | None


class DayRead(BaseModel):
    """One day of the timeline.

    `stage_ids` is derived at read time from the stages' dates, never stored — see
    `domain/stages.py`. `items` is present and always empty until Phase 3 fills it;
    shipping the key from the start means the SPA's rendering path is the same on
    both sides of that change.
    """

    id: uuid.UUID
    date: date
    stage_ids: list[uuid.UUID]
    items: list[dict[str, object]] = Field(default_factory=list)


class TripSummary(BaseModel):
    """A row of the trip list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    start_date: date
    end_date: date
    departure_place: str
    return_place: str | None


class TripDetail(TripSummary):
    """The timeline payload."""

    stages: list[StageRead]
    days: list[DayRead]


def timeline(trip: Trip) -> TripDetail:
    """Build the timeline payload, deriving each day's stages once.

    The stages are read from the already-loaded relationship, so a trip of any
    length costs the two queries `get_owned_trip` already issued.
    """
    stages = sorted(trip.stages, key=lambda stage: stage.position)

    return TripDetail(
        id=trip.id,
        title=trip.title,
        start_date=trip.start_date,
        end_date=trip.end_date,
        departure_place=trip.departure_place,
        return_place=trip.return_place,
        stages=[StageRead.model_validate(stage) for stage in stages],
        days=[
            DayRead(
                id=day.id,
                date=day.date,
                stage_ids=[stage.id for stage in stages_for_day(stages, day.date)],
                items=[],
            )
            for day in sorted(trip.days, key=lambda day: day.date)
        ],
    )


@router.get("", response_model=list[TripSummary])
def list_trips(db: DbSession, owner: CurrentOwner) -> list[Trip]:
    """The owner's trips, soonest first.

    Ordered by start date rather than by creation: the list answers "what is
    coming up", and creation order is an implementation detail of when the owner
    happened to type them in.
    """
    return list(
        db.execute(
            sa.select(Trip)
            .where(Trip.owner_id == owner.id)
            .order_by(Trip.start_date, Trip.created_at)
        ).scalars()
    )


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
