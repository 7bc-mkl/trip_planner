"""The approval service — the one place inbound content may write to a plan.

**D21 as code.** A forwarded confirmation never writes to `item`: routing and
extraction produce an `inbound_action_item`, and this module's `approve` is the
only writer, field by field, of exactly what the owner named.
`tests/test_inbox_boundary.py` asserts that nothing under `inbound/`,
`integrations/` or the worker references a plan table at all, so an
inbound-originated write has nowhere else to come from.

It lives outside `inbound/` for that reason rather than despite it: building a
proposal has to *read* the routed trip's items to target one, and the module
that reads them is the same module that — on approval only — writes them.

Four layers stand between a proposal and a value the owner typed, and each one
is tested on its own:

1. **The default tick** (`domain/inbound.diff_proposal`): a non-empty current
   value is never ticked by default.
2. **The allow-list body**: only the fields the approval names are written.
3. **The revision token**: a sheet opened before the proposal was regenerated
   or re-targeted is refused rather than applied to values it never showed.
4. **The re-diff**: each named field's live value is compared with the value
   recorded when the proposal was made. A difference refuses the whole
   approval, and the snapshot is refreshed so the reloaded sheet shows what is
   true now.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import (
    ITEM_KINDS,
    ITEM_STATUSES,
    Attachment,
    InboundActionItem,
    InboundMessage,
    Item,
    Owner,
    Trip,
    TripDay,
)
from trip_planner.domain.extraction import (
    APPROVABLE_FIELDS,
    ExtractedFields,
    ProposalValues,
    coerce,
)
from trip_planner.domain.inbound import (
    PROPOSED_STATUS,
    DayCandidate,
    ItemCandidate,
    choose_target,
    fallback_title,
    field_value,
)
from trip_planner.domain.items import validate_span
from trip_planner.errors import ApiError, ErrorCode
from trip_planner.security.quota import QuotaRejection, get_upload_quota

__all__ = [
    "Alternative",
    "ApprovalSelection",
    "StoredProposal",
    "approve",
    "find_action_item",
    "propose_by_hand",
    "propose_from_routing",
    "read_proposal",
    "reject",
    "retarget",
    "snapshot_of",
    "supersede_pending",
    "undo",
]

#: The `proposal` JSONB's current shape. A version integer is the cheap half of
#: BACKWARD_COMPATIBILITY.md §3's "a stored document stays readable"; the
#: rejecting reader below is the expensive half.
SCHEMA_VERSION = 1


class Alternative(BaseModel):
    """Another candidate trip routing considered — a one-click re-target."""

    model_config = ConfigDict(extra="forbid")

    trip_id: uuid.UUID
    title: str


class StoredProposal(BaseModel):
    """The `proposal` column, read back. **Rejects unknown fields.**

    An unreadable proposal fails loudly here rather than being half-applied.
    """

    model_config = ConfigDict(extra="forbid")

    #: `model` for a routed message, `owner` for one he proposed by hand.
    source: Literal["model", "owner"]
    proposed: ProposalValues
    #: The target item's values when the proposal was made or last re-targeted:
    #: what the approval re-diffs against. `None` for a new item.
    snapshot: ProposalValues | None = None
    snapshot_status: str | None = None
    proposed_status: str | None = None
    attachment_ids: list[uuid.UUID] = []
    alternatives: list[Alternative] = []
    #: Why the proposal points where it does — a translation key.
    target_reason: str


class ApprovalSelection(BaseModel):
    """The approval body: **the selection**, an explicit allow-list (spec, API).

    `extra="forbid"` per AGENTS.md. `fields` is not typed as a `Literal` so that
    a field name outside the proposal answers the spec's
    `invalid_action_selection` rather than a generic validation error.
    """

    model_config = ConfigDict(extra="forbid")

    target_item_id: uuid.UUID | None = None
    target_trip_day_id: uuid.UUID | None = None
    fields: list[str] = []
    attachment_ids: list[uuid.UUID] = []
    set_status: str | None = None
    expected_revision: int


def read_proposal(action_item: InboundActionItem) -> StoredProposal:
    return StoredProposal.model_validate(action_item.proposal)


def _store(action_item: InboundActionItem, proposal: StoredProposal) -> None:
    action_item.proposal = proposal.model_dump(mode="json")


def snapshot_of(item: Item, day: TripDay) -> ProposalValues:
    """An item's current values in the shape a proposal compares against."""
    return ProposalValues(
        title=item.title,
        kind=item.kind,
        confirmation_number=item.confirmation_number,
        start_date=day.date,
        end_date=item.end_date,
        start_time=item.start_time,
        end_time=item.end_time,
        cost_amount=item.cost_amount,
        cost_currency=item.cost_currency,
    )


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Lookups, every one scoped to the owner
# --------------------------------------------------------------------------- #


def find_action_item(
    db: OrmSession, owner: Owner, action_item_id: uuid.UUID, *, for_update: bool = False
) -> InboundActionItem:
    """One of **this owner's** action items, or 404 — never by id alone."""
    query = (
        sa.select(InboundActionItem)
        .join(InboundMessage, InboundMessage.id == InboundActionItem.inbound_message_id)
        .where(
            InboundActionItem.id == action_item_id,
            InboundActionItem.owner_id == owner.id,
            InboundMessage.state != "discarded",
        )
    )
    if for_update:
        query = query.with_for_update(of=InboundActionItem)
    action_item = db.execute(query).scalar_one_or_none()
    if action_item is None:
        raise ApiError(ErrorCode.NOT_FOUND, field="action_item_id")
    return action_item


def _owned_item(
    db: OrmSession, owner: Owner, item_id: uuid.UUID, *, for_update: bool = False
) -> tuple[Item, TripDay, Trip] | None:
    """An item resolved through its trip's owner — `get_owned_trip`'s rule, one hop down."""
    query = (
        sa.select(Item, TripDay, Trip)
        .join(TripDay, TripDay.id == Item.trip_day_id)
        .join(Trip, Trip.id == TripDay.trip_id)
        .where(Item.id == item_id, Trip.owner_id == owner.id)
    )
    if for_update:
        query = query.with_for_update(of=Item)
    row = db.execute(query).one_or_none()
    return None if row is None else (row[0], row[1], row[2])


def _owned_day(db: OrmSession, owner: Owner, day_id: uuid.UUID) -> tuple[TripDay, Trip] | None:
    row = db.execute(
        sa.select(TripDay, Trip)
        .join(Trip, Trip.id == TripDay.trip_id)
        .where(TripDay.id == day_id, Trip.owner_id == owner.id)
    ).one_or_none()
    return None if row is None else (row[0], row[1])


def _message_document_ids(db: OrmSession, message: InboundMessage) -> list[uuid.UUID]:
    return list(
        db.execute(
            sa.select(Attachment.id)
            .where(Attachment.inbound_message_id == message.id)
            .order_by(Attachment.created_at, Attachment.id)
        ).scalars()
    )


# --------------------------------------------------------------------------- #
# Creating proposals
# --------------------------------------------------------------------------- #


def supersede_pending(db: OrmSession, message: InboundMessage) -> None:
    """Retire this message's pending proposals — it has been placed again."""
    db.execute(
        sa.update(InboundActionItem)
        .where(
            InboundActionItem.inbound_message_id == message.id,
            InboundActionItem.state == "pending",
        )
        .values(state="superseded", decided_at=_now())
    )


def propose_from_routing(
    db: OrmSession,
    message: InboundMessage,
    *,
    owner: Owner,
    fields: ExtractedFields | None,
    alternatives: tuple[tuple[str, str], ...] = (),
) -> InboundActionItem | None:
    """Turn a routed message and the model's claim into one pending action item.

    **Writes no plan value.** The trip's items are read to choose a target, and
    nothing about any of them changes until the owner approves.

    A message with nothing to propose — no field survived coercion and no
    document arrived — produces no action item: a proposal with nothing to tick
    is noise, and the routed message is still there for the owner to read and
    propose by hand.
    """
    if message.trip_id is None:
        return None
    trip = db.execute(
        sa.select(Trip).where(Trip.id == message.trip_id, Trip.owner_id == owner.id)
    ).scalar_one_or_none()
    if trip is None:
        return None

    proposed = (
        coerce(fields, trip_start=trip.start_date, trip_end=trip.end_date, kinds=ITEM_KINDS)
        if fields is not None
        else ProposalValues()
    )
    documents = _message_document_ids(db, message)
    if proposed.is_empty() and not documents:
        return None

    days = list(db.execute(sa.select(TripDay).where(TripDay.trip_id == trip.id)).scalars())
    rows = db.execute(
        sa.select(Item, TripDay)
        .join(TripDay, TripDay.id == Item.trip_day_id)
        .where(TripDay.trip_id == trip.id)
    ).all()
    target = choose_target(
        proposed,
        items=[
            ItemCandidate(
                id=str(item.id),
                day_id=str(day.id),
                date=day.date,
                end_date=item.end_date,
                title=item.title,
                confirmation_number=item.confirmation_number,
            )
            for item, day in rows
        ],
        days=[DayCandidate(id=str(day.id), date=day.date) for day in days],
    )

    snapshot = None
    snapshot_status = None
    if target.item_id is not None:
        item, day = next((one, d) for one, d in rows if str(one.id) == target.item_id)
        snapshot = snapshot_of(item, day)
        snapshot_status = item.status

    supersede_pending(db, message)
    action_item = InboundActionItem(
        inbound_message_id=message.id,
        owner_id=owner.id,
        kind=target.kind,
        target_item_id=uuid.UUID(target.item_id) if target.item_id else None,
        target_trip_day_id=uuid.UUID(target.day_id) if target.day_id else None,
        schema_version=SCHEMA_VERSION,
        proposal={},
    )
    _store(
        action_item,
        StoredProposal(
            source="model",
            proposed=proposed,
            snapshot=snapshot,
            snapshot_status=snapshot_status,
            proposed_status=PROPOSED_STATUS,
            attachment_ids=documents,
            alternatives=[
                Alternative(trip_id=uuid.UUID(trip_id), title=title)
                for trip_id, title in alternatives
            ],
            target_reason=target.reason,
        ),
    )
    db.add(action_item)
    db.flush()
    return action_item


def propose_by_hand(
    db: OrmSession,
    message: InboundMessage,
    *,
    owner: Owner,
    target_item_id: uuid.UUID | None,
    target_trip_day_id: uuid.UUID | None,
) -> InboundActionItem:
    """The owner's explicit act of proposing a placement for a routed message.

    Zero fields and the message's documents — the "document-only message" case.
    Still an action item, still approved: putting a document on an item *is* a
    write. Hand classification (`place`) creates nothing; this does, because the
    owner asked for it.
    """
    if message.trip_id is None:
        raise ApiError(ErrorCode.MESSAGE_NOT_ROUTABLE, field="trip_id")

    action_item = InboundActionItem(
        inbound_message_id=message.id,
        owner_id=owner.id,
        kind="create_item",
        schema_version=SCHEMA_VERSION,
        proposal={},
    )
    _store(
        action_item,
        StoredProposal(
            source="owner",
            proposed=ProposalValues(),
            proposed_status=None,
            attachment_ids=_message_document_ids(db, message),
            target_reason="chosen_by_owner",
        ),
    )
    _point_at(
        db,
        action_item,
        owner=owner,
        target_item_id=target_item_id,
        target_trip_day_id=target_trip_day_id,
        message=message,
    )
    supersede_pending(db, message)
    db.add(action_item)
    db.flush()
    return action_item


def _point_at(
    db: OrmSession,
    action_item: InboundActionItem,
    *,
    owner: Owner,
    target_item_id: uuid.UUID | None,
    target_trip_day_id: uuid.UUID | None,
    message: InboundMessage,
) -> None:
    """Aim a proposal at one owned item or day, and re-take the snapshot.

    The snapshot is taken **here**, at the moment the owner sees the target,
    which is what lets the approval's re-diff protect a re-targeted proposal
    exactly as it protects the original one.
    """
    if (target_item_id is None) == (target_trip_day_id is None):
        raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="target")

    proposal = read_proposal(action_item)
    if target_item_id is not None:
        owned = _owned_item(db, owner, target_item_id)
        if owned is None:
            raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="target_item_id")
        item, day, trip = owned
        action_item.kind = "update_item"
        action_item.target_item_id = item.id
        action_item.target_trip_day_id = None
        proposal.snapshot = snapshot_of(item, day)
        proposal.snapshot_status = item.status
    else:
        assert target_trip_day_id is not None
        owned_day = _owned_day(db, owner, target_trip_day_id)
        if owned_day is None:
            raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="target_trip_day_id")
        day, trip = owned_day
        action_item.kind = "create_item"
        action_item.target_item_id = None
        action_item.target_trip_day_id = day.id
        proposal.snapshot = None
        proposal.snapshot_status = None

    proposal.target_reason = "chosen_by_owner"
    _store(action_item, proposal)
    if message.trip_id != trip.id:
        # Re-targeting onto an alternative trip is the owner re-routing his own
        # mail — the same single column hand placement writes.
        message.trip_id = trip.id
        message.state = "routed"
        message.routing_reason = "placed_by_hand"
        message.routing_reason_args = None


def _message_of(db: OrmSession, action_item: InboundActionItem) -> InboundMessage:
    return db.execute(
        sa.select(InboundMessage).where(InboundMessage.id == action_item.inbound_message_id)
    ).scalar_one()


def retarget(
    db: OrmSession,
    owner: Owner,
    action_item_id: uuid.UUID,
    *,
    target_item_id: uuid.UUID | None,
    target_trip_day_id: uuid.UUID | None,
    expected_revision: int,
) -> InboundActionItem:
    """Point a pending proposal somewhere else; bumps `revision`."""
    action_item = find_action_item(db, owner, action_item_id, for_update=True)
    _require_pending(action_item)
    _require_revision(action_item, expected_revision)
    _point_at(
        db,
        action_item,
        owner=owner,
        target_item_id=target_item_id,
        target_trip_day_id=target_trip_day_id,
        message=_message_of(db, action_item),
    )
    action_item.revision += 1
    db.flush()
    return action_item


# --------------------------------------------------------------------------- #
# Deciding
# --------------------------------------------------------------------------- #


def _require_pending(action_item: InboundActionItem) -> None:
    if action_item.state != "pending":
        raise ApiError(ErrorCode.ACTION_ITEM_ALREADY_DECIDED)


def _require_revision(action_item: InboundActionItem, expected: int) -> None:
    if action_item.revision != expected:
        raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="revision")


def _validate_selection(
    proposal: StoredProposal, selection: ApprovalSelection
) -> None:
    """Every name in the body must be something the proposal actually claims."""
    for name in selection.fields:
        if name not in APPROVABLE_FIELDS or field_value(proposal.proposed, name) is None:
            raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field=name)
    if len(set(selection.fields)) != len(selection.fields):
        raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="fields")
    for attachment_id in selection.attachment_ids:
        if attachment_id not in proposal.attachment_ids:
            raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="attachment_ids")
    if len(set(selection.attachment_ids)) != len(selection.attachment_ids):
        raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="attachment_ids")
    if selection.set_status is not None and selection.set_status not in ITEM_STATUSES:
        raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="set_status")


def _write(item: Item, values: ProposalValues, name: str) -> None:
    if name == "cost":
        item.cost_amount = values.cost_amount
        item.cost_currency = values.cost_currency
    else:
        setattr(item, name, getattr(values, name))


def _refuse_with_fresh_snapshot(
    db: OrmSession,
    action_item: InboundActionItem,
    proposal: StoredProposal,
    *,
    item: Item,
    day: TripDay,
    field: str,
) -> None:
    """`409 action_item_conflict`, after recording what is true now.

    Committed **before** the refusal: the request's own transaction is rolled
    back by the error, and without the commit the reloaded sheet would show the
    same stale values and refuse again forever. Nothing about the item has been
    written at this point — the check runs before any write.
    """
    proposal.snapshot = snapshot_of(item, day)
    proposal.snapshot_status = item.status
    _store(action_item, proposal)
    action_item.revision += 1
    db.commit()
    raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field=field)


@dataclass(frozen=True, slots=True)
class _Documents:
    rows: list[Attachment]

    @property
    def total_bytes(self) -> int:
        return sum(one.byte_size for one in self.rows)


def _documents_for(
    db: OrmSession, message: InboundMessage, attachment_ids: list[uuid.UUID]
) -> _Documents:
    if not attachment_ids:
        return _Documents([])
    rows = list(
        db.execute(
            sa.select(Attachment)
            .where(
                Attachment.id.in_(attachment_ids),
                Attachment.inbound_message_id == message.id,
            )
            .with_for_update()
        ).scalars()
    )
    if len(rows) != len(attachment_ids):
        # Listed in the proposal but no longer in the inbox — already approved
        # onto something else, or deleted with its message.
        raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="attachment_ids")
    return _Documents(rows)


def _check_capacity(
    db: OrmSession, *, item: Item, trip: Trip, documents: _Documents
) -> None:
    """The shipped limits, re-checked — a re-point is an `UPDATE` no limiter sees.

    The per-parent cap is checked for *all* the incoming documents at once
    (`check_parent_capacity` asks about one more), and the byte quotas through
    the shipped locked sums, so the inbox cannot walk an item past twenty files
    or a trip past its 250 MB.
    """
    if not documents.rows:
        return
    quota = get_upload_quota()
    existing = db.execute(
        sa.select(sa.func.count()).select_from(Attachment).where(Attachment.item_id == item.id)
    ).scalar_one()
    if int(existing) + len(documents.rows) > quota.max_attachments_per_parent:
        raise ApiError(ErrorCode.ATTACHMENT_LIMIT_REACHED)
    rejection = quota.check_byte_quotas(db, trip_id=trip.id, incoming_bytes=documents.total_bytes)
    if rejection is QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED:
        raise ApiError(ErrorCode.TRIP_STORAGE_QUOTA_EXCEEDED)
    if rejection is not None:  # pragma: no cover - byte quotas return only the one
        raise ApiError(ErrorCode(rejection.value))


def approve(
    db: OrmSession, owner: Owner, action_item_id: uuid.UUID, selection: ApprovalSelection
) -> InboundActionItem:
    """Write exactly what the owner selected, and record what it replaced."""
    action_item = find_action_item(db, owner, action_item_id, for_update=True)
    _require_pending(action_item)
    _require_revision(action_item, selection.expected_revision)
    proposal = read_proposal(action_item)
    _validate_selection(proposal, selection)
    message = _message_of(db, action_item)

    if action_item.kind == "update_item":
        if action_item.target_item_id is None:
            raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="target")
        if selection.target_trip_day_id is not None or (
            selection.target_item_id not in (None, action_item.target_item_id)
        ):
            # The sheet was showing another target than the one stored — a
            # re-target the server never recorded a snapshot for.
            raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="target_item_id")
        applied = _apply_update(db, owner, action_item, proposal, selection, message)
    else:
        if action_item.target_trip_day_id is None:
            raise ApiError(ErrorCode.INVALID_ACTION_SELECTION, field="target")
        if selection.target_item_id is not None or (
            selection.target_trip_day_id not in (None, action_item.target_trip_day_id)
        ):
            raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="target_trip_day_id")
        applied = _apply_create(db, owner, action_item, proposal, selection, message)

    action_item.state = "approved"
    action_item.applied = applied
    action_item.decided_at = _now()
    db.flush()
    return action_item


def _apply_update(
    db: OrmSession,
    owner: Owner,
    action_item: InboundActionItem,
    proposal: StoredProposal,
    selection: ApprovalSelection,
    message: InboundMessage,
) -> dict[str, object]:
    assert action_item.target_item_id is not None
    owned = _owned_item(db, owner, action_item.target_item_id, for_update=True)
    if owned is None:  # pragma: no cover - the FK cascade removes the proposal first
        raise ApiError(ErrorCode.NOT_FOUND, field="target_item_id")
    item, day, trip = owned

    # The re-diff — before a single value is written.
    live = snapshot_of(item, day)
    recorded = proposal.snapshot or ProposalValues()
    for name in selection.fields:
        if field_value(live, name) != field_value(recorded, name):
            _refuse_with_fresh_snapshot(
                db, action_item, proposal, item=item, day=day, field=name
            )
    if selection.set_status is not None and item.status != proposal.snapshot_status:
        _refuse_with_fresh_snapshot(
            db, action_item, proposal, item=item, day=day, field="status"
        )

    documents = _documents_for(db, message, selection.attachment_ids)
    before_status = item.status
    for name in selection.fields:
        _write(item, proposal.proposed, name)
    if selection.set_status is not None:
        item.status = selection.set_status

    validate_span(
        start_date=day.date,
        start_time=item.start_time,
        end_time=item.end_time,
        end_date=item.end_date,
        trip_end=trip.end_date,
    )
    _check_capacity(db, item=item, trip=trip, documents=documents)
    _repoint(documents, item)

    return {
        "item_id": str(item.id),
        "created": False,
        "fields": list(selection.fields),
        "before": live.model_dump(mode="json"),
        "after": snapshot_of(item, day).model_dump(mode="json"),
        "status_before": before_status if selection.set_status is not None else None,
        "status_after": item.status if selection.set_status is not None else None,
        "attachment_ids": [str(one.id) for one in documents.rows],
    }


def _apply_create(
    db: OrmSession,
    owner: Owner,
    action_item: InboundActionItem,
    proposal: StoredProposal,
    selection: ApprovalSelection,
    message: InboundMessage,
) -> dict[str, object]:
    from trip_planner.api.items import next_position

    assert action_item.target_trip_day_id is not None
    owned_day = _owned_day(db, owner, action_item.target_trip_day_id)
    if owned_day is None:  # pragma: no cover - the FK cascade removes the proposal first
        raise ApiError(ErrorCode.NOT_FOUND, field="target_trip_day_id")
    day, trip = owned_day
    documents = _documents_for(db, message, selection.attachment_ids)

    named = set(selection.fields)
    values = proposal.proposed
    item = Item(
        trip_day_id=day.id,
        position=next_position(db, day),
        # A new item needs a title and a kind whatever was ticked. An unticked
        # claim is not written; the neutral fallback is.
        title=values.title
        if "title" in named and values.title
        else fallback_title(
            ProposalValues(), subject=message.subject, from_address=message.from_address
        ),
        kind=values.kind if "kind" in named and values.kind else "other",
        status=selection.set_status or "to_plan",
    )
    for name in named - {"title", "kind"}:
        _write(item, values, name)

    validate_span(
        start_date=day.date,
        start_time=item.start_time,
        end_time=item.end_time,
        end_date=item.end_date,
        trip_end=trip.end_date,
    )
    db.add(item)
    db.flush()
    _check_capacity(db, item=item, trip=trip, documents=documents)
    _repoint(documents, item)

    return {
        "item_id": str(item.id),
        "created": True,
        "fields": list(selection.fields),
        "before": None,
        "after": snapshot_of(item, day).model_dump(mode="json"),
        "status_before": None,
        "status_after": item.status,
        "attachment_ids": [str(one.id) for one in documents.rows],
    }


def _repoint(documents: _Documents, item: Item) -> None:
    """One row per document, re-parented. **No byte is copied.**"""
    for attachment in documents.rows:
        attachment.inbound_message_id = None
        attachment.item_id = item.id


def reject(db: OrmSession, owner: Owner, action_item_id: uuid.UUID) -> None:
    """Decline a proposal. Destroys nothing — the message stays readable."""
    action_item = find_action_item(db, owner, action_item_id, for_update=True)
    _require_pending(action_item)
    action_item.state = "rejected"
    action_item.decided_at = _now()
    db.flush()


def undo(db: OrmSession, owner: Owner, action_item_id: uuid.UUID) -> InboundActionItem:
    """Restore exactly what `applied` recorded — while nothing has moved on.

    Refuses rather than clobbers: if any field it wrote now holds something
    else, or a document it moved is no longer on the item, the owner (or a
    later approval) has touched the result since, and undo is honest about its
    window rather than pretending to be a time machine.
    """
    action_item = find_action_item(db, owner, action_item_id, for_update=True)
    if action_item.state != "approved" or action_item.applied is None:
        raise ApiError(ErrorCode.ACTION_ITEM_ALREADY_DECIDED)
    applied = action_item.applied
    message = _message_of(db, action_item)

    owned = _owned_item(db, owner, uuid.UUID(str(applied["item_id"])), for_update=True)
    if owned is None:
        raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="item")
    item, day, _ = owned

    after = ProposalValues.model_validate(applied["after"])
    live = snapshot_of(item, day)
    names = [str(one) for one in applied["fields"]]  # type: ignore[union-attr]
    for name in names:
        if field_value(live, name) != field_value(after, name):
            raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field=name)
    if applied["status_after"] is not None and item.status != applied["status_after"]:
        raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="status")

    if applied["created"] and (live != after or item.notes is not None):
        # A created item is removed whole, so *every* value on it must still be
        # what the approval wrote — a note, a kind or a day the owner added by
        # hand afterwards is his, and deleting the item would silently lose it.
        raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="item")

    moved = [uuid.UUID(str(one)) for one in applied["attachment_ids"]]  # type: ignore[union-attr]
    documents = list(
        db.execute(
            sa.select(Attachment)
            .where(Attachment.id.in_(moved), Attachment.item_id == item.id)
            .with_for_update()
        ).scalars()
    ) if moved else []
    if len(documents) != len(moved):
        raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="attachment_ids")

    for attachment in documents:
        attachment.item_id = None
        attachment.inbound_message_id = message.id

    if applied["created"]:
        conditions = [Attachment.item_id == item.id]
        if moved:
            conditions.append(Attachment.id.not_in(moved))
        others = db.execute(
            sa.select(sa.func.count()).select_from(Attachment).where(*conditions)
        ).scalar_one()
        if int(others):
            raise ApiError(ErrorCode.ACTION_ITEM_CONFLICT, field="item")
        db.flush()
        db.delete(item)
    else:
        before = ProposalValues.model_validate(applied["before"])
        for name in names:
            _write(item, before, name)
        if applied["status_before"] is not None:
            item.status = str(applied["status_before"])
        proposal = read_proposal(action_item)
        proposal.snapshot = snapshot_of(item, day)
        proposal.snapshot_status = item.status
        _store(action_item, proposal)

    # A proposal the owner made for this message after the approval would
    # otherwise sit beside this one, both pending and both approvable.
    supersede_pending(db, message)
    action_item.state = "pending"
    action_item.applied = None
    action_item.decided_at = None
    action_item.revision += 1
    db.flush()
    return action_item
