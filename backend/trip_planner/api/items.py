"""The day detail and the item CRUD it drives.

Every route here is nested under `/trips/{trip_id}` and takes `get_owned_trip`.
The nesting is for readability; the dependency is the enforcement. It also makes
a cross-*trip* item move unreachable by construction — the trip id is in the
path, so an item id belonging to another trip is a `404`, not a case to handle.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date as date_type
from datetime import time
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session as OrmSession

from trip_planner.api.deps import DbSession, OwnedTrip
from trip_planner.api.schemas import (
    AttachmentRead,
    DayDetail,
    ItemDetail,
    ItemKind,
    ItemRead,
    ItemStatus,
    StageRead,
)
from trip_planner.db.models import Attachment, Item, Trip, TripDay
from trip_planner.domain.items import sorted_items, validate_span
from trip_planner.domain.money import validate_cost
from trip_planner.domain.stages import stages_for_day
from trip_planner.errors import ApiError, ErrorCode

router = APIRouter(prefix="/trips/{trip_id}", tags=["items"])

TITLE_MAX = 200
NOTES_MAX = 5000
#: The bound the `ck_item_confirmation_number` CHECK also states. Far beyond any
#: real voucher code; it exists because this is the one otherwise-unbounded input.
CONFIRMATION_NUMBER_MAX = 500

#: The nullable fields a PATCH can either clear or leave alone.
#:
#: `{"end_date": null}` must clear the span while omitting the key leaves it
#: untouched — two different intentions. Pydantic v2's `model_fields_set` records
#: which keys the request actually carried, which distinguishes them exactly. A
#: string sentinel default would not: a client could send that very string.
#:
#: The three reservation fields join the list rather than getting a mechanism of
#: their own: clearing a confirmation number is the same question as clearing a
#: note, and a second sentinel scheme beside this one would be two answers to it.
NULLABLE_FIELDS = (
    "start_time",
    "end_time",
    "end_date",
    "notes",
    "confirmation_number",
    "cost_amount",
    "cost_currency",
)


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
    #: Bounded exactly as on create: a boundary the POST guards and the PATCH does
    #: not is a hole, not an asymmetry.
    notes: str | None = Field(default=None, max_length=NOTES_MAX)
    #: The day to move the item to, within the same trip.
    date: date_type | None = None
    #: The reservation fields. Optional, like everything else here — **none is
    #: required**, which is R04 expressed in the contract rather than only in the
    #: UI. Adding optional request fields is non-breaking; adding required ones
    #: would not be.
    #:
    #: There is deliberately no `reservation_start` / `reservation_end`: a
    #: reservation's dates are the item's own `start_time` / `end_time` /
    #: `end_date`, written through the fields a few lines above and validated by
    #: the same `validate_span`.
    confirmation_number: str | None = None
    #: A `Decimal`, never a `float`: `float` cannot represent `10.10`, and a
    #: third decimal place `NUMERIC(12,2)` cannot hold would slip past a naive
    #: float comparison. `domain/money.py` decides what a valid amount is; no
    #: `max_digits` here, so there is one place that rule is written.
    cost_amount: Decimal | None = None
    cost_currency: str | None = None


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


# --------------------------------------------------------------------------- #
# Attachments on the item payloads
# --------------------------------------------------------------------------- #
#
# Every function below reads `attachment` and **never** `attachment_blob`. The
# bytes live in their own table precisely so that a listing cannot read them by
# accident (`db/models.py` argues the split), and
# `tests/test_attachments_api.py` records the statements a payload emits and
# fails if the blob table appears in one.
#
# All of them take *every* id of the payload at once and answer in one
# statement. A per-item count would be an N+1 on the screen a year-long trip
# opens first: three hundred items, three hundred `SELECT count(*)`.


def attachment_counts(
    db: OrmSession, item_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """How many attachments each of `item_ids` has — one `GROUP BY`, never one per item.

    Items with none are simply absent from the result; callers default to `0`
    rather than this padding the map, so the query stays a plain aggregate.
    """
    if not item_ids:
        return {}

    rows = db.execute(
        sa.select(Attachment.item_id, sa.func.count())
        .where(Attachment.item_id.in_(item_ids))
        .group_by(Attachment.item_id)
    ).all()

    return {item_id: count for item_id, count in rows if item_id is not None}


def attachments_by_item(
    db: OrmSession, item_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[Attachment]]:
    """The attachments of `item_ids`, grouped — one statement for the whole day.

    Every id gets a key, including the items with no files, so a serialiser reads
    the map directly instead of remembering to default.
    """
    grouped: dict[uuid.UUID, list[Attachment]] = {item_id: [] for item_id in item_ids}
    if not item_ids:
        return grouped

    rows = db.execute(
        sa.select(Attachment)
        .where(Attachment.item_id.in_(item_ids))
        # `created_at` alone is not a total order — two files uploaded inside the
        # same clock tick would swap places between requests — so the id breaks
        # the tie and the list is stable.
        .order_by(Attachment.created_at, Attachment.id)
    ).scalars()

    for attachment in rows:
        if attachment.item_id is not None:
            grouped[attachment.item_id].append(attachment)

    return grouped


def day_attachments(db: OrmSession, day: TripDay) -> list[Attachment]:
    """The files pinned to the day itself, which is not the same set as its items'."""
    return list(
        db.execute(
            sa.select(Attachment)
            .where(Attachment.trip_day_id == day.id)
            .order_by(Attachment.created_at, Attachment.id)
        ).scalars()
    )


def item_read(item: Item, attachment_count: int) -> ItemRead:
    """The timeline's shape of an item, carrying its counted attachments.

    The count is injected rather than read off the row: `Item` has no such column
    — it is an aggregate over another table — and the aggregate belongs to the
    payload as a whole, not to one row of it.
    """
    return ItemRead.model_validate(item).model_copy(
        update={"attachment_count": attachment_count}
    )


def item_detail(item: Item, attachments: Sequence[Attachment]) -> ItemDetail:
    """The day detail's shape: the same item, plus the files themselves.

    The count is `len()` of the list already loaded, so the day detail never pays
    for a second aggregate to answer a question it is holding the answer to.
    """
    return ItemDetail(
        **item_read(item, len(attachments)).model_dump(),
        attachments=[AttachmentRead.model_validate(one) for one in attachments],
    )


def cleared_when_blank(confirmation_number: str | None) -> str | None:
    """`""` — and any all-whitespace string — means *clear the field*, not store it.

    The `ck_item_confirmation_number` CHECK refuses `''`, so an empty string has
    to become something. `NULL` is the only honest choice: a field the user
    emptied is a field with no confirmation number, which is exactly what `NULL`
    already means everywhere else. Answering `422` instead would make clearing a
    field the user *can* clear an error, and storing `''` would give "not
    recorded" two representations that every reader would then have to test for.

    Whitespace is not stripped from a value that survives — a voucher code is
    stored verbatim — only used to decide whether anything was typed at all.
    """
    if confirmation_number is None or not confirmation_number.strip():
        return None
    return confirmation_number


def validate_reservation(
    *,
    confirmation_number: str | None,
    cost_amount: Decimal | None,
    cost_currency: str | None,
) -> None:
    """Refuse a reservation the `item` row could not hold, before trying to store it.

    The cost rules are **not** restated here: `domain/money.py` owns what a valid
    cost is, so the two halves cannot be judged differently by two callers, and
    the paired-nullability rule is stated once in the domain and once by the
    database's own `ck_item_cost_paired`.

    Both are checked against the *resolved* row — the fields the item will have
    after the patch, not just the keys the request carried. That is the same
    question the CHECK asks. It also means `{"cost_amount": "80.00"}` on an item
    that already has a currency is a legitimate price correction rather than a
    refusal, while the same key alone on an item with no cost is the `422` the
    spec's Edge Cases table calls for.
    """
    if confirmation_number is not None and len(confirmation_number) > CONFIRMATION_NUMBER_MAX:
        raise ApiError(ErrorCode.INVALID_RESERVATION_FIELD, field="confirmation_number")

    if validate_cost(cost_amount=cost_amount, cost_currency=cost_currency) is not None:
        raise ApiError(ErrorCode.INVALID_COST, field="cost_amount")


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
    """The day detail, with its derived stages, its files and its prev/next neighbours.

    Two statements cover every attachment on the payload however many items the
    day holds: one for the day's own files, one for all of its items' — never one
    per item.
    """
    dates = sorted(existing.date for existing in trip.days)
    index = dates.index(day.date)
    stages = sorted(trip.stages, key=lambda stage: stage.position)
    items = sorted_items(day_items(db, day))
    per_item = attachments_by_item(db, [item.id for item in items])

    return DayDetail(
        id=day.id,
        trip_id=trip.id,
        date=day.date,
        stages=[StageRead.model_validate(stage) for stage in stages_for_day(stages, day.date)],
        items=[item_detail(item, per_item[item.id]) for item in items],
        attachments=[
            AttachmentRead.model_validate(one) for one in day_attachments(db, day)
        ],
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
) -> ItemRead:
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

    # Zero, by construction: an item that did not exist a line ago has no files,
    # so this is the counted truth rather than an assumed default.
    return item_read(item, 0)


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(
    trip: OwnedTrip, item_id: uuid.UUID, payload: ItemUpdate, db: DbSession
) -> ItemRead:
    """Update any field of an item, including moving it to another day.

    The span is re-validated against the item's *resulting* day, not its current
    one: moving an item forward can push its `end_date` past the trip's end, and
    checking before the move would miss it.

    A move carries the item's attachments with it and nothing here has to arrange
    that: an attachment points at the *item*, so the file follows the item to its
    new day for the same reason its title does. A day's own files stay on the day
    they were pinned to — they are the day's, not any item's.
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

    resolved["confirmation_number"] = cleared_when_blank(resolved["confirmation_number"])

    validate_span(
        start_date=target_day.date,
        start_time=resolved["start_time"],
        end_time=resolved["end_time"],
        end_date=resolved["end_date"],
        trip_end=trip.end_date,
    )
    validate_reservation(
        confirmation_number=resolved["confirmation_number"],
        cost_amount=resolved["cost_amount"],
        cost_currency=resolved["cost_currency"],
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

    return item_read(item, attachment_counts(db, [item.id]).get(item.id, 0))


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
