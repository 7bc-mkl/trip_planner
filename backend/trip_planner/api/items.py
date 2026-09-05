"""The day detail and the item CRUD it drives.

Every route here is nested under `/trips/{trip_id}` and takes `get_owned_trip`.
The nesting is for readability; the dependency is the enforcement. It also makes
a cross-*trip* item move unreachable by construction — the trip id is in the
path, so an item id belonging to another trip is a `404`, not a case to handle.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import time

import sqlalchemy as sa
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as OrmSession

from trip_planner.api.deps import DbSession, OwnedTrip
from trip_planner.api.schemas import DayDetail, ItemKind, ItemRead, ItemStatus, StageRead
from trip_planner.db.models import Item, Trip, TripDay
from trip_planner.domain.items import sorted_items, validate_span
from trip_planner.domain.stages import stages_for_day
from trip_planner.errors import ApiError, ErrorCode

router = APIRouter(prefix="/trips/{trip_id}", tags=["items"])

TITLE_MAX = 200
NOTES_MAX = 5000

#: The nullable fields a PATCH can either clear or leave alone.
#:
#: `{"end_date": null}` must clear the span while omitting the key leaves it
#: untouched — two different intentions. Pydantic v2's `model_fields_set` records
#: which keys the request actually carried, which distinguishes them exactly. A
#: string sentinel default would not: a client could send that very string.
NULLABLE_FIELDS = ("start_time", "end_time", "end_date", "notes")


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ItemKind
    #: Defaults to `to_plan`: a new item is something nothing has been decided about.
    status: ItemStatus = "to_plan"
    start_time: time | None = None
    end_time: time | None = None
    end_date: date_type | None = None
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)


class ItemUpdate(BaseModel):
    """A partial update. Every field is optional; `date` moves the item to another day.

    Which keys were actually sent is read from `model_fields_set`, so a `null`
    that clears a field is distinguishable from an absent key that leaves it be.
    """

    model_config = ConfigDict(extra="forbid")

    kind: ItemKind | None = None
    status: ItemStatus | None = None
    start_time: time | None = None
    end_time: time | None = None
    end_date: date_type | None = None
    title: str | None = Field(default=None, min_length=1, max_length=TITLE_MAX)
    notes: str | None = None
    #: The day to move the item to, within the same trip.
    date: date_type | None = None


def days_by_date(trip: Trip) -> dict[date_type, TripDay]:
    return {day.date: day for day in trip.days}


def get_day(trip: Trip, day_date: date_type) -> TripDay:
    """The trip's day for `day_date`, or 404.

    A date outside the trip has no row, and answering 404 rather than inventing an
    empty day is what keeps "this day is empty" distinguishable from "this day is
    not part of the trip".
    """
    day = days_by_date(trip).get(day_date)
    if day is None:
        raise ApiError(ErrorCode.NOT_FOUND, field="date")
    return day


def find_item(db: OrmSession, trip: Trip, item_id: uuid.UUID) -> Item:
    """An item of *this* trip, or 404.

    Joined to `trip_day` and filtered on the trip rather than fetched by id alone:
    that join is what makes a cross-trip reference a 404 instead of a successful
    edit of another trip's day. Queried rather than searched in the loaded
    relationships so the answer does not depend on what happens to be in the
    session's identity map.
    """
    item = db.execute(
        sa.select(Item)
        .join(TripDay, Item.trip_day_id == TripDay.id)
        .where(Item.id == item_id, TripDay.trip_id == trip.id)
    ).scalar_one_or_none()

    if item is None:
        raise ApiError(ErrorCode.NOT_FOUND, field="item_id")
    return item


def day_items(db: OrmSession, day: TripDay) -> list[Item]:
    """The day's items, read from the database rather than a loaded collection."""
    return list(
        db.execute(sa.select(Item).where(Item.trip_day_id == day.id)).scalars()
    )


def next_position(db: OrmSession, day: TripDay) -> int:
    """`max(position) + 1` within the day.

    Assigned server-side, never sent by the client: `position` is the tie-break
    for untimed items, and a client-chosen value would let two tabs disagree about
    an order neither of them owns.

    A `MAX()` against the indexed `trip_day_id` rather than a scan of the day's
    loaded items: the collection may have been loaded before this request added to
    it, and a position computed from a stale collection silently collides.
    """
    highest = db.execute(
        sa.select(sa.func.max(Item.position)).where(Item.trip_day_id == day.id)
    ).scalar()

    return 0 if highest is None else highest + 1


def day_payload(db: OrmSession, trip: Trip, day: TripDay) -> DayDetail:
    """The day detail, with its derived stages and its prev/next neighbours."""
    dates = sorted(existing.date for existing in trip.days)
    index = dates.index(day.date)
    stages = sorted(trip.stages, key=lambda stage: stage.position)

    return DayDetail(
        id=day.id,
        trip_id=trip.id,
        date=day.date,
        stages=[StageRead.model_validate(stage) for stage in stages_for_day(stages, day.date)],
        items=[ItemRead.model_validate(item) for item in sorted_items(day_items(db, day))],
        # None at the boundaries, so the navigator can disable rather than guess.
        previous_date=dates[index - 1] if index > 0 else None,
        next_date=dates[index + 1] if index + 1 < len(dates) else None,
    )


@router.get("/days/{day_date}", response_model=DayDetail)
def get_day_detail(trip: OwnedTrip, day_date: date_type, db: DbSession) -> DayDetail:
    return day_payload(db, trip, get_day(trip, day_date))


@router.post(
    "/days/{day_date}/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED
)
def create_item(
    trip: OwnedTrip, day_date: date_type, payload: ItemCreate, db: DbSession
) -> Item:
    day = get_day(trip, day_date)

    validate_span(
        start_date=day.date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        end_date=payload.end_date,
        trip_end=trip.end_date,
    )

    item = Item(
        trip_day_id=day.id,
        position=next_position(db, day),
        kind=payload.kind,
        status=payload.status,
        start_time=payload.start_time,
        end_time=payload.end_time,
        end_date=payload.end_date,
        title=payload.title,
        notes=payload.notes,
    )
    db.add(item)
    db.flush()

    return item


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(
    trip: OwnedTrip, item_id: uuid.UUID, payload: ItemUpdate, db: DbSession
) -> Item:
    """Update any field of an item, including moving it to another day.

    The span is re-validated against the item's *resulting* day, not its current
    one: moving an item forward can push its `end_date` past the trip's end, and
    checking before the move would miss it.
    """
    item = find_item(db, trip, item_id)

    target_day = item.trip_day
    if payload.date is not None and payload.date != target_day.date:
        moved_to = days_by_date(trip).get(payload.date)
        if moved_to is None:
            # A date with no trip_day is outside the range. Distinct from `404`:
            # the item exists, the destination does not.
            raise ApiError(ErrorCode.DATE_OUTSIDE_TRIP, field="date")
        target_day = moved_to

    sent = payload.model_fields_set
    resolved = {
        field: getattr(payload, field) if field in sent else getattr(item, field)
        for field in NULLABLE_FIELDS
    }

    validate_span(
        start_date=target_day.date,
        start_time=resolved["start_time"],
        end_time=resolved["end_time"],
        end_date=resolved["end_date"],
        trip_end=trip.end_date,
    )

    if target_day.id != item.trip_day_id:
        item.trip_day_id = target_day.id
        # Re-numbered into the destination day rather than keeping a position from
        # a day it has left, where it could collide or leave a gap.
        item.position = next_position(db, target_day)

    for field, value in resolved.items():
        setattr(item, field, value)
    # kind, status and title are never nullable, so "sent" and "not null" agree
    # and no sentinel is needed for them.
    for field in ("kind", "status", "title"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)

    db.flush()
    db.refresh(item)

    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(trip: OwnedTrip, item_id: uuid.UUID, db: DbSession) -> Response:
    """Delete an item.

    The remaining items are *not* renumbered: `position` only has to order them,
    not be dense, and a gap costs nothing while a renumbering UPDATE on every
    delete costs a write per sibling.
    """
    db.delete(find_item(db, trip, item_id))
    db.flush()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
