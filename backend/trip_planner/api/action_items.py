"""The action-item endpoints — where D21 becomes something the owner clicks.

Every route here is owner-authenticated: included with the shared
`AUTHENTICATED` dependency list (so the session and its CSRF check), and each
handler takes `CurrentOwner` so every lookup can carry an `owner_id` clause.
Account-scoped rather than trip-scoped, like the rest of the inbox; the one
moment a trip *is* touched — approval — resolves it through its owner in
`approvals.py` before writing.

The handlers are deliberately thin. What may be written, and when, is decided in
`approvals.py`; what the review sheet shows is decided by the pure diff in
`domain/inbound.py`. This module only turns both into wire shapes.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as OrmSession

from trip_planner import approvals
from trip_planner.api.deps import CurrentOwner, DbSession
from trip_planner.api.inbox import ConfiguredInbox, InboxAttachmentRead, find_message
from trip_planner.db.models import (
    Attachment,
    InboundActionItem,
    InboundMessage,
    Item,
    Owner,
    Trip,
    TripDay,
)
from trip_planner.domain.inbound import diff_proposal, diff_status
from trip_planner.errors import ApiError, ErrorCode

router = APIRouter(prefix="/inbox", tags=["inbox"])


# --------------------------------------------------------------------------- #
# Wire shapes
# --------------------------------------------------------------------------- #


class FieldRowRead(BaseModel):
    """One row of the review sheet: what the item says, what the message says.

    `current` and `proposed` are typed values rendered for the wire — ISO dates,
    `HH:MM` times, and `{"amount": "480.00", "currency": "MYR"}` for a cost —
    never prose, so nothing a model wrote can reach the screen as a sentence.
    """

    name: str
    current: Any
    proposed: Any
    changed: bool
    default_ticked: bool


class StatusRowRead(BaseModel):
    current: str | None
    proposed: str
    changed: bool
    default_ticked: bool


class AlternativeRead(BaseModel):
    trip_id: uuid.UUID
    title: str


class AppliedRead(BaseModel):
    """What one approval wrote — and therefore what *Undo* would restore."""

    item_id: uuid.UUID
    created: bool
    fields: list[str]
    status_changed: bool
    attachment_count: int


class ActionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    subject: str
    from_address: str
    received_at: datetime
    kind: str
    state: str
    #: Sent back as `expected_revision` on approve and re-target.
    revision: int
    source: str
    trip_id: uuid.UUID | None
    trip_title: str | None
    target_item_id: uuid.UUID | None
    target_item_title: str | None
    target_trip_day_id: uuid.UUID | None
    #: The day the target sits on — the item's start day, or the day a new item
    #: would land on.
    target_date: date | None
    #: A translation key: why the proposal points where it does.
    target_reason: str
    fields: list[FieldRowRead]
    status: StatusRowRead | None
    attachments: list[InboxAttachmentRead]
    alternatives: list[AlternativeRead]
    applied: AppliedRead | None
    decided_at: datetime | None
    created_at: datetime


class ProposeRequest(BaseModel):
    """The owner names a target for a routed message. Exactly one of the two."""

    model_config = ConfigDict(extra="forbid")

    target_item_id: uuid.UUID | None = None
    target_trip_day_id: uuid.UUID | None = None


class RetargetRequest(ProposeRequest):
    expected_revision: int


# --------------------------------------------------------------------------- #
# Building the view
# --------------------------------------------------------------------------- #


def _wire(value: object) -> object:
    if isinstance(value, tuple):
        amount, currency = value
        return {"amount": str(amount), "currency": currency}
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def action_item_read(db: OrmSession, action_item: InboundActionItem) -> ActionItemRead:
    proposal = approvals.read_proposal(action_item)
    message = db.execute(
        sa.select(InboundMessage).where(InboundMessage.id == action_item.inbound_message_id)
    ).scalar_one()
    trip = (
        db.execute(sa.select(Trip).where(Trip.id == message.trip_id)).scalar_one_or_none()
        if message.trip_id is not None
        else None
    )

    target_title: str | None = None
    target_date: date | None = None
    if action_item.target_item_id is not None:
        row = db.execute(
            sa.select(Item.title, TripDay.date)
            .join(TripDay, TripDay.id == Item.trip_day_id)
            .where(Item.id == action_item.target_item_id)
        ).one_or_none()
        if row is not None:
            target_title, target_date = row[0], row[1]
    elif action_item.target_trip_day_id is not None:
        target_date = db.execute(
            sa.select(TripDay.date).where(TripDay.id == action_item.target_trip_day_id)
        ).scalar_one_or_none()

    snapshot = proposal.snapshot if action_item.kind == "update_item" else None
    fields = diff_proposal(proposal.proposed, snapshot)
    status_row = diff_status(
        proposal.proposed_status,
        proposal.snapshot_status if action_item.kind == "update_item" else None,
    )

    applied = action_item.applied
    applied_item = uuid.UUID(str(applied["item_id"])) if applied else None
    parent = Attachment.inbound_message_id == message.id
    if applied_item is not None:
        parent = sa.or_(parent, Attachment.item_id == applied_item)
    attachments = (
        list(
            db.execute(
                sa.select(Attachment)
                .where(Attachment.id.in_(proposal.attachment_ids), parent)
                .order_by(Attachment.created_at, Attachment.id)
            ).scalars()
        )
        if proposal.attachment_ids
        else []
    )

    return ActionItemRead(
        id=action_item.id,
        message_id=message.id,
        subject=message.subject,
        from_address=message.from_address,
        received_at=message.received_at,
        kind=action_item.kind,
        state=action_item.state,
        revision=action_item.revision,
        source=proposal.source,
        trip_id=trip.id if trip else None,
        trip_title=trip.title if trip else None,
        target_item_id=action_item.target_item_id,
        target_item_title=target_title,
        target_trip_day_id=action_item.target_trip_day_id,
        target_date=target_date,
        target_reason=proposal.target_reason,
        fields=[
            FieldRowRead(
                name=row.name,
                current=_wire(row.current),
                proposed=_wire(row.proposed),
                changed=row.changed,
                default_ticked=row.default_ticked,
            )
            for row in fields
        ],
        status=(
            StatusRowRead(
                current=status_row.current,
                proposed=status_row.proposed or "",
                changed=status_row.changed,
                default_ticked=status_row.default_ticked,
            )
            if status_row is not None
            else None
        ),
        attachments=[InboxAttachmentRead.model_validate(one) for one in attachments],
        alternatives=[
            AlternativeRead(trip_id=one.trip_id, title=one.title) for one in proposal.alternatives
        ],
        applied=(
            AppliedRead(
                item_id=uuid.UUID(str(applied["item_id"])),
                created=bool(applied["created"]),
                fields=[str(one) for one in applied["fields"]],  # type: ignore[union-attr]
                status_changed=applied["status_after"] is not None
                and applied["status_after"] != applied["status_before"],
                attachment_count=len(applied["attachment_ids"]),  # type: ignore[arg-type]
            )
            if applied
            else None
        ),
        decided_at=action_item.decided_at,
        created_at=action_item.created_at,
    )


def pending_count(db: OrmSession, owner: Owner) -> int:
    """The badge's number — served by the partial `state = 'pending'` index."""
    return int(
        db.execute(
            sa.select(sa.func.count())
            .select_from(InboundActionItem)
            .join(InboundMessage, InboundMessage.id == InboundActionItem.inbound_message_id)
            .where(
                InboundActionItem.owner_id == owner.id,
                InboundActionItem.state == "pending",
                InboundMessage.state != "discarded",
            )
        ).scalar_one()
    )


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

#: The states a client may filter by. `superseded` is housekeeping, not a list.
LISTABLE_STATES = ("pending", "approved", "rejected")


@router.get("/action-items", response_model=list[ActionItemRead])
def list_action_items(
    db: DbSession, owner: CurrentOwner, inbox: ConfiguredInbox, state: str = "pending"
) -> list[ActionItemRead]:
    """Newest first. Pending by default — the "awaiting you" region."""
    if state not in LISTABLE_STATES:
        return []
    rows = db.execute(
        sa.select(InboundActionItem)
        .join(InboundMessage, InboundMessage.id == InboundActionItem.inbound_message_id)
        .where(
            InboundActionItem.owner_id == owner.id,
            InboundActionItem.state == state,
            InboundMessage.state != "discarded",
        )
        .order_by(InboundActionItem.created_at.desc(), InboundActionItem.id)
        .limit(50)
    ).scalars()
    return [action_item_read(db, one) for one in rows]


@router.get("/action-items/{action_item_id}", response_model=ActionItemRead)
def get_action_item(
    action_item_id: uuid.UUID, db: DbSession, owner: CurrentOwner, inbox: ConfiguredInbox
) -> ActionItemRead:
    return action_item_read(db, approvals.find_action_item(db, owner, action_item_id))


@router.post("/action-items/{action_item_id}/approve", response_model=ActionItemRead)
def approve_action_item(
    action_item_id: uuid.UUID,
    body: approvals.ApprovalSelection,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
) -> ActionItemRead:
    """Write exactly the selection. The body is the allow-list (spec, API Contracts)."""
    return action_item_read(db, approvals.approve(db, owner, action_item_id, body))


@router.post(
    "/action-items/{action_item_id}/reject", status_code=status.HTTP_204_NO_CONTENT
)
def reject_action_item(
    action_item_id: uuid.UUID, db: DbSession, owner: CurrentOwner, inbox: ConfiguredInbox
) -> Response:
    """Rejecting destroys nothing — the message stays readable."""
    approvals.reject(db, owner, action_item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/action-items/{action_item_id}/undo", response_model=ActionItemRead)
def undo_action_item(
    action_item_id: uuid.UUID, db: DbSession, owner: CurrentOwner, inbox: ConfiguredInbox
) -> ActionItemRead:
    return action_item_read(db, approvals.undo(db, owner, action_item_id))


@router.post("/action-items/{action_item_id}/retarget", response_model=ActionItemRead)
def retarget_action_item(
    action_item_id: uuid.UUID,
    body: RetargetRequest,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
) -> ActionItemRead:
    return action_item_read(
        db,
        approvals.retarget(
            db,
            owner,
            action_item_id,
            target_item_id=body.target_item_id,
            target_trip_day_id=body.target_trip_day_id,
            expected_revision=body.expected_revision,
        ),
    )


@router.post(
    "/messages/{message_id}/action-items",
    response_model=ActionItemRead,
    status_code=status.HTTP_201_CREATED,
)
def propose_for_message(
    message_id: uuid.UUID,
    body: ProposeRequest,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
) -> ActionItemRead:
    """The owner's explicit "put this message's documents on…" act."""
    message = find_message(db, owner, message_id)
    if message.state == "quarantined":
        raise ApiError(ErrorCode.NOT_FOUND, field="message_id")
    return action_item_read(
        db,
        approvals.propose_by_hand(
            db,
            message,
            owner=owner,
            target_item_id=body.target_item_id,
            target_trip_day_id=body.target_trip_day_id,
        ),
    )
