"""Response models shared by the trip and item routers.

They live here rather than in whichever router happened to need them first: the
timeline payload embeds items and the day-detail payload embeds stages, so any
other arrangement makes `api/trips.py` and `api/items.py` import each other.

Three shapes of trip, kept separate on purpose rather than one model with
optional fields — otherwise "absent because this is the list" is
indistinguishable from "absent because there are none", which is the ambiguity
`BACKWARD_COMPATIBILITY.md` warns about:

- `TripSummary` — a row of `/trips`.
- `TripDetail`  — the timeline payload for `/trips/{id}`.
- `DayDetail`   — the day-detail payload for `/trips/{id}/days/{date}`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict

from trip_planner.db.models import ITEM_KINDS, ITEM_STATUSES

__all__ = [
    "AttachmentRead",
    "DayDetail",
    "DayRead",
    "ItemKind",
    "ItemRead",
    "ItemStatus",
    "ReadinessRead",
    "StageRead",
    "TripDetail",
    "TripSummary",
]

#: Derived from the tuples that build the database CHECK constraints, so the
#: request models, the wire contract and the constraint cannot disagree about
#: which values exist.
#:
#: `Literal[some_tuple]` is equivalent to spelling the members out —
#: `Literal[ITEM_KINDS]` is `Literal["accommodation", "transport", …]` — which is
#: what lets the single tuple in `db/models.py` drive the CHECK clause, these
#: request models and the SPA's own constant. Type checkers cannot follow the
#: indirection through a name, hence the ignore; `tests/test_models_item.py`
#: covers the round trip instead.
ItemKind = Literal[ITEM_KINDS]  # type: ignore[valid-type]
ItemStatus = Literal[ITEM_STATUSES]  # type: ignore[valid-type]


class ReadinessRead(BaseModel):
    """The counter (R02).

    `tracked`, never `total`: a trip with ten items all still `to_plan` has
    `tracked = 0`, so a consumer reading it as the item count would be wrong in
    exactly the case the counter exists to describe.
    """

    arranged: int
    tracked: int


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    place: str
    start_date: date | None
    end_date: date | None


class AttachmentRead(BaseModel):
    """One attachment's metadata — the shape served wherever an attachment appears.

    Defined once, in the module both the upload router and the day/timeline
    serialisers import, because the spec says this object is "identical wherever
    an attachment is serialised" and two definitions of one wire shape drift.

    `content_type` is the type **derived from the bytes** on upload, never
    anything the client claimed, and `byte_size` is the length that was actually
    counted while reading. Both parents are always present, exactly one of them
    non-null, so a consumer can tell a day's document from an item's without
    knowing which endpoint it came from.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    byte_size: int
    sha256: str
    created_at: datetime
    item_id: uuid.UUID | None
    trip_day_id: uuid.UUID | None


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    kind: ItemKind
    status: ItemStatus
    #: Local wall-clock, serialised as `HH:MM`; there is no timezone, deliberately.
    start_time: time | None
    end_time: time | None
    #: `null` means the item ends on its start day.
    end_date: date | None
    title: str
    notes: str | None


class DayRead(BaseModel):
    """One day of the timeline.

    `stage_ids` is derived at read time from the stages' dates, never stored.
    """

    id: uuid.UUID
    date: date
    stage_ids: list[uuid.UUID]
    items: list[ItemRead]


class TripSummary(BaseModel):
    """A row of the trip list — no days, no stages.

    A list of ten year-long trips must not ship three thousand day objects.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    start_date: date
    end_date: date
    departure_place: str
    #: `null` means one-way: the trip does not return.
    return_place: str | None
    readiness: ReadinessRead


class TripDetail(TripSummary):
    """The timeline payload: everything the SPA needs to render and filter.

    Complete on purpose — A11 puts filtering in the browser, so there are no
    filter query parameters and no second request per day.
    """

    stages: list[StageRead]
    days: list[DayRead]


class DayDetail(BaseModel):
    """The day-detail payload.

    `previous_date` and `next_date` are computed server-side rather than by the
    SPA adding a day: the trip's first and last days have no neighbour, and that
    boundary is the server's to know.
    """

    id: uuid.UUID
    trip_id: uuid.UUID
    date: date
    stages: list[StageRead]
    items: list[ItemRead]
    previous_date: date | None
    next_date: date | None
