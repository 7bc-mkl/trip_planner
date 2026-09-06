"""Stage endpoints — adding, editing and removing a trip's bases.

The interesting part is `position`. It must stay **dense** — 0, 1, 2, … with no
gaps — because it is the itinerary's display order and a gap would eventually be
visible as a hole in whatever renders it by index. Keeping it dense after a
delete from the middle means shifting every later stage down by one.

That shift is a **single `UPDATE`**, which only works because
`uq_trip_stage_position` is `DEFERRABLE INITIALLY DEFERRED`: mid-statement the
rows transiently collide, and an ordinary UNIQUE constraint would abort. Doing it
row by row with a temporary sentinel would need three statements and a value that
must not clash with a real one.

Deleting a stage does **not** touch days or items: days belong to the trip, not
to the stage, so only the derived label changes.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as OrmSession

from trip_planner.api.deps import DbSession, OwnedTrip
from trip_planner.api.schemas import StageRead
from trip_planner.db.models import Trip, TripStage
from trip_planner.domain.stages import validate_stage_range
from trip_planner.errors import ApiError, ErrorCode

router = APIRouter(prefix="/trips/{trip_id}/stages", tags=["stages"])

PLACE_MAX = 200


class StageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place: str = Field(min_length=1, max_length=PLACE_MAX)
    #: Optional by design (R03): a base whose days are undecided is still a base.
    start_date: date | None = None
    end_date: date | None = None


class StageUpdate(BaseModel):
    """A partial update.

    The dates are nullable, so which keys were sent matters: omitting
    `start_date` leaves it alone, sending `null` clears it back to undecided.
    `model_fields_set` is what distinguishes the two.
    """

    model_config = ConfigDict(extra="forbid")

    place: str | None = Field(default=None, min_length=1, max_length=PLACE_MAX)
    start_date: date | None = None
    end_date: date | None = None


def find_stage(trip: Trip, stage_id: uuid.UUID) -> TripStage:
    for stage in trip.stages:
        if stage.id == stage_id:
            return stage
    raise ApiError(ErrorCode.NOT_FOUND, field="stage_id")


def renumber_after_delete(db: OrmSession, trip: Trip, removed_position: int) -> None:
    """Shift every stage after `removed_position` down by one, in one statement.

    Relies on the deferred unique constraint: while this UPDATE runs, a row that
    has already moved shares its new position with one that has not yet. Under an
    ordinary UNIQUE this aborts.
    """
    db.execute(
        sa.update(TripStage)
        .where(TripStage.trip_id == trip.id, TripStage.position > removed_position)
        .values(position=TripStage.position - 1)
    )


@router.post("", response_model=StageRead, status_code=status.HTTP_201_CREATED)
def create_stage(trip: OwnedTrip, payload: StageCreate, db: DbSession) -> TripStage:
    """Append a stage at the end of the trip's list."""
    validate_stage_range(
        payload.start_date,
        payload.end_date,
        trip_start=trip.start_date,
        trip_end=trip.end_date,
        place=payload.place,
    )

    stage = TripStage(
        trip_id=trip.id,
        position=max((existing.position for existing in trip.stages), default=-1) + 1,
        place=payload.place,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    db.add(stage)
    db.flush()

    return stage


@router.patch("/{stage_id}", response_model=StageRead)
def update_stage(
    trip: OwnedTrip, stage_id: uuid.UUID, payload: StageUpdate, db: DbSession
) -> TripStage:
    stage = find_stage(trip, stage_id)
    sent = payload.model_fields_set

    start = payload.start_date if "start_date" in sent else stage.start_date
    end = payload.end_date if "end_date" in sent else stage.end_date
    place = payload.place if payload.place is not None else stage.place

    validate_stage_range(
        start,
        end,
        trip_start=trip.start_date,
        trip_end=trip.end_date,
        place=place,
    )

    stage.place = place
    stage.start_date = start
    stage.end_date = end
    db.flush()

    return stage


@router.delete("/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stage(trip: OwnedTrip, stage_id: uuid.UUID, db: DbSession) -> Response:
    """Remove a stage, keeping the remaining positions dense.

    R03 requires one or more stages, so the last one cannot be removed — a trip
    with no bases is not a multi-stop trip, it is a gap in the data.
    """
    stage = find_stage(trip, stage_id)

    if len(trip.stages) == 1:
        raise ApiError(ErrorCode.STAGES_REQUIRED, field="stage_id")

    position = stage.position
    db.delete(stage)
    # Flushed before the renumbering so the row is gone when the shift runs;
    # otherwise the UPDATE would move rows into the position it still occupies.
    db.flush()
    renumber_after_delete(db, trip, position)
    db.flush()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
