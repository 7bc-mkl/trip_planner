"""The inbox endpoints.

**One of these routes is public and the rest are not**, and the difference is
the whole of this module's security story.

`POST /inbox/receipts/sns` is the single permission R10 grants: an unauthenticated
HTTPS endpoint that AWS SNS posts to. It is registered on its own router, without
the session dependency, and its path is named in `PUBLIC_PATHS` deliberately —
`tests/test_route_protection.py` fails if that list grows by anything else.

What makes that safe is not that the route does little; it is what the route
*cannot* do. It verifies an SNS signature against a certificate fetched only
from AWS's own host, checks the topic ARN, the SES action type, the bucket, the
key prefix and the recipient, and then writes **one row saying mail arrived**.
It fetches no MIME, stores no body, touches no attachment and changes no plan.
Every one of those happens later, in the background worker, behind the sender
policy. A perfectly forged notification therefore buys an attacker a row in a
table nobody renders, and the tests in `tests/test_inbox_receipts.py` assert
exactly that.

The status codes are a control too. Everything the endpoint can decide from the
event itself is a **permanent** refusal — `400`/`403`, so SNS stops retrying
something no retry will fix — while a failure of *ours* (the database, a missing
owner) is a `5xx`, so SNS does retry and its dead-letter queue catches what is
left. Getting this backwards means either a hot loop of forged traffic or mail
silently dropped during a database blip.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as OrmSession

from trip_planner.api.attachments import _matches_etag, _serving_headers
from trip_planner.api.deps import AppSettings, CurrentOwner, DbSession
from trip_planner.config import InboxSettings
from trip_planner.db.models import (
    Attachment,
    AttachmentBlob,
    InboundDeliveryStatus,
    InboundMessage,
    InboundTrustedSender,
    Owner,
    Trip,
)
from trip_planner.domain.inbound import (
    SenderDecision,
    decide_stored_sender,
    normalise_address,
    normalise_subject,
    normalise_verdict,
)
from trip_planner.errors import ApiError, ErrorCode
from trip_planner.inbound.ingest import (
    allowed_senders_for,
    delete_ingested_object,
    ingest_message,
)
from trip_planner.inbound.ses import S3Fetcher, SignatureVerifier, verify_event
from trip_planner.inbound.transport import (
    MAX_SNS_BODY_BYTES,
    DeliveryNotice,
    RejectedEvent,
    SubscriptionRequest,
)

logger = logging.getLogger(__name__)


class NoOwnerYet(RuntimeError):
    """There is no account for this mail to belong to — yet.

    Deliberately **retryable**. A deployment that has taken delivery before its
    owner row exists is a real, temporary state (a fresh install, mail already
    in flight), and the mail is genuine. Answering a permanent refusal would
    make SNS stop retrying and the confirmation would be gone for good.
    """

#: Public. Included **without** the session dependency; see the module docstring.
public_router = APIRouter(prefix="/inbox", tags=["inbox"])

#: Everything else. Included with the shared `AUTHENTICATED` dependency list, so
#: these routes carry `get_current_session` — and therefore the CSRF check —
#: without any of them having to remember, and `get_current_owner` on top so the
#: owner is reachable in the handler at all.
owner_router = APIRouter(prefix="/inbox", tags=["inbox"])

#: One verifier for the process, so the signing certificate is fetched once
#: rather than once per notification — which would put a synchronous outbound
#: request on the path of every inbound mail.
_verifier = SignatureVerifier()


def get_signature_verifier() -> SignatureVerifier:
    """The seam tests override so no suite run fetches a certificate over the network."""
    return _verifier


def set_signature_verifier(verifier: SignatureVerifier) -> None:
    global _verifier
    _verifier = verifier


def require_inbox(settings: AppSettings) -> InboxSettings:
    """The inbox's configuration, or `409 inbox_not_configured`.

    A dependency rather than a line in each handler: the failure mode of the
    per-handler version is a route added later that forgets, and then answers a
    confusing `500` from deep inside an AWS client on a deployment that simply
    has no inbox.

    409 rather than 404 — the routes exist and the request is well-formed; what
    is missing is deployment configuration the caller cannot fix by changing the
    request.
    """
    if settings.inbox is None:
        raise ApiError(ErrorCode.INBOX_NOT_CONFIGURED)
    return settings.inbox


ConfiguredInbox = Annotated[InboxSettings, Depends(require_inbox)]


def find_message(db: OrmSession, owner: Owner, message_id: uuid.UUID) -> InboundMessage:
    """One of **this owner's** messages, or 404.

    Every inbox read goes through this rather than querying by id: a handler
    that writes its own query can forget the `owner_id` clause, which is the
    same failure `get_owned_trip` exists to prevent one level up. A discarded
    message is a 404 too — it is hidden from the UI, and a route that still
    served it would make "deleted" mean "invisible in one place".
    """
    message = db.execute(
        sa.select(InboundMessage).where(
            InboundMessage.id == message_id,
            InboundMessage.owner_id == owner.id,
            InboundMessage.state != "discarded",
        )
    ).scalar_one_or_none()

    if message is None:
        raise ApiError(ErrorCode.NOT_FOUND, field="message_id")
    return message


@owner_router.get("/messages/{message_id}/attachments/{attachment_id}/content")
def get_inbox_attachment_content(
    message_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
) -> Response:
    """The bytes of a document still in the inbox.

    **A new route rather than the shipped one**, and the reason is structural
    rather than stylistic: `api/attachments.py`'s content route is mounted under
    `/trips/{trip_id}` and resolves ownership through `item → trip_day → trip` or
    `trip_day → trip`. A message in the unrouted queue has no trip, so that chain
    has nothing to resolve. Ownership is established here through the message
    instead.

    What is **not** new is the header set: `_serving_headers` is imported and
    called, so there is exactly one answer in this product to "how is a stored
    file served" — the derived `Content-Type`, `Content-Disposition: attachment`,
    `nosniff`, the sandbox CSP, `Cross-Origin-Resource-Policy`, `private,
    no-cache` and the strong `ETag`. A test asserts both routes' headers are
    byte-identical for the same file, so a change to one cannot quietly leave
    the other behind.

    The conditional branch answers before the blob is selected, which is the
    whole point of the `ETag`: a revalidation costs one metadata row rather than
    ten megabytes off the disk and down the wire.
    """
    message = find_message(db, owner, message_id)

    attachment = db.execute(
        sa.select(Attachment).where(
            Attachment.id == attachment_id,
            # Scoped to *this* message, not merely to the owner: an attachment id
            # from another of his messages is still not this message's document,
            # and a route that served it would make the message id decorative.
            Attachment.inbound_message_id == message.id,
        )
    ).scalar_one_or_none()
    if attachment is None:
        raise ApiError(ErrorCode.NOT_FOUND, field="attachment_id")

    headers = _serving_headers(attachment)
    if _matches_etag(request.headers.get("if-none-match"), headers["etag"]):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)

    data = db.execute(
        sa.select(AttachmentBlob.data).where(AttachmentBlob.attachment_id == attachment.id)
    ).scalar_one()

    return Response(content=data, headers=headers)


# --------------------------------------------------------------------------- #
# Wire shapes
# --------------------------------------------------------------------------- #


class InboxAttachmentRead(BaseModel):
    """A document still in the inbox.

    A shape of its own rather than the shipped `AttachmentRead`, deliberately.
    That model carries `item_id` and `trip_day_id` and documents that exactly one
    of them is non-null; on an inbox row neither is, so reusing it would make its
    own contract false everywhere it already appears. Adding a third field to it
    instead would push an always-null `inbound_message_id` into every trip and
    day payload in the product to save one small class here.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    byte_size: int
    sha256: str
    created_at: datetime
    #: When sending this document to a model provider was attempted. Always
    #: `None` in Phase 1 — there is no model — and on the shape now so the screen
    #: does not change contract when Phase 4 starts writing it.
    sent_externally_at: datetime | None


class InboxMessageRow(BaseModel):
    """A row of the inbox list: metadata only, **never** the body.

    The body is deliberately absent rather than truncated. A list that carried
    200 000 characters per message would be a payload nobody asked for, and a
    list that carried a preview would be a second, subtly different rendering of
    the same text to keep in step with the detail view.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    received_at: datetime
    from_address: str
    subject: str
    state: str
    trip_id: uuid.UUID | None
    routing_reason: str | None
    last_error: str | None
    attachment_count: int


class InboxMessageDetail(InboxMessageRow):
    """One message, with its text and its documents."""

    text_body: str
    attachments: list[InboxAttachmentRead]


class QuarantineRead(BaseModel):
    """A quarantined message: **headers only, and that is the control.**

    No body, no attachment, no preview — ever. Quarantine is a barrier, and a
    barrier that renders the content it is holding back has become a delivery
    mechanism for exactly the material the owner did not ask to see.

    The headers are here for the one case that matters: a mailbox rule that
    auto-forwards an airline's confirmation while preserving the airline's
    `From` lands in quarantine, and a bare count would make that a silent loss.
    The two recovery flags say which action this reason permits, so the screen
    offers the right one rather than both.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    received_at: datetime
    from_address: str
    subject: str
    reason: str | None
    may_trust_sender: bool
    may_release_message: bool
    recoverable: bool


class InboxSummary(BaseModel):
    """The badge's query, cheap enough to poll.

    `pending_action_items` is **not** here. Action items arrive with Phase 3, and
    a field reporting zero for a concept that does not exist yet is a contract
    that says something false — worse than an absent field, which a consumer can
    see is absent. It is additive when it arrives.
    """

    inbox_enabled: bool
    #: The address to forward to, so the empty state can name it and offer a copy.
    address: str | None
    unrouted: int
    quarantined: int
    #: Honest freshness. An empty inbox and a broken inbox must not look alike.
    last_received_at: datetime | None
    last_error_at: datetime | None
    last_error: str | None


class PlaceRequest(BaseModel):
    """Hand placement's body. `extra="forbid"` per AGENTS.md."""

    model_config = ConfigDict(extra="forbid")

    trip_id: uuid.UUID


async def _read_bounded_body(request: Request) -> bytes | None:
    """The request body, refused the moment it passes the cap. `None` when it does.

    Both halves, as on the upload path: `Content-Length` is checked before a byte
    is read, and the bytes are counted *while* they are read, because a chunked
    request can lie about or omit its length. This route is reachable by anyone
    who learns the URL, so "how much memory can a stranger make this process
    hold" needs an answer here and not in the server's defaults.
    """
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_SNS_BODY_BYTES:
        return None

    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_SNS_BODY_BYTES:
            return None
    return bytes(body)


@public_router.post("/receipts/sns", status_code=status.HTTP_200_OK)
async def receive_sns_notification(
    request: Request, db: DbSession, settings: AppSettings
) -> Response:
    """Verify an SNS envelope and durably record that mail arrived. Nothing else.

    Answers `2xx` only **after** the row is committed (including an idempotent
    repeat), because acknowledging first and writing afterwards is how a crash
    between the two loses a confirmation with SNS believing it delivered.
    """
    inbox = settings.inbox
    if inbox is None:
        # Not configured, so there is no topic to check a signature against. A
        # permanent refusal: no retry makes an unconfigured deployment accept it.
        return _refused("not_configured")

    body = await _read_bounded_body(request)
    if body is None:
        return _refused("oversized_body")

    try:
        payload: Any = json.loads(body)
    except ValueError:
        return _refused("malformed_json")

    outcome = verify_event(payload, settings=inbox, verifier=get_signature_verifier())
    if isinstance(outcome, RejectedEvent):
        # Logged as a code, never with the body: a forged event is
        # attacker-authored text, and echoing it into our logs is how a log
        # viewer becomes the injection's actual target.
        logger.warning("inbox: refused an SNS event (%s)", outcome.reason.value)
        return _refused(outcome.reason.value)

    if outcome.subscription is not None:
        _confirm_subscription(outcome.subscription)
        return Response(status_code=status.HTTP_200_OK)

    if outcome.notice is None:
        # A verified envelope this endpoint has nothing to do with — an
        # unsubscribe confirmation. Acknowledged, deliberately not acted on.
        return Response(status_code=status.HTTP_200_OK)

    try:
        _record_delivery(db, outcome.notice)
    except (OperationalError, NoOwnerYet):
        # Ours, not theirs: a retryable 5xx so SNS tries again and its
        # dead-letter queue catches what survives the retry schedule.
        logger.exception("inbox: could not record a verified delivery")
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(status_code=status.HTTP_200_OK)


def _refused(reason: str) -> Response:
    """A permanent refusal, so SNS stops retrying something no retry will fix."""
    return Response(status_code=status.HTTP_403_FORBIDDEN, content=reason.encode("ascii"))


def _confirm_subscription(subscription: SubscriptionRequest) -> None:
    """Confirm, by fetching the URL SNS supplied — after it has been verified.

    Two things had to be true before this line is reached: the envelope's
    signature checked out, and `SubscribeURL`'s host is AWS's own. Without the
    second, this call is a request-forgery primitive pointed at anything a
    stranger names in a request body.

    A failure is swallowed deliberately. SNS retries the confirmation, and an
    exception here would answer `5xx` to an envelope that was perfectly valid.
    """
    import urllib.request

    try:
        with urllib.request.urlopen(subscription.subscribe_url, timeout=5.0) as response:
            response.read(1024)
    except Exception:
        logger.warning("inbox: subscription confirmation could not be completed")


def _record_delivery(db: OrmSession, notice: DeliveryNotice) -> None:
    """Insert one `pending_ingest` row, idempotently, and stamp the delivery status.

    **Idempotency is the database's job, not a `SELECT` first.** Checking for an
    existing row and inserting if absent is a race two concurrent redeliveries
    both win; `ON CONFLICT DO NOTHING` against `uq_inbound_message_ses_id` is the
    same intent expressed where it is actually atomic.

    The row carries no body and no attachment. The sender policy has not run
    yet — it runs in the worker, before the S3 GET — so what is committed here
    is only *that mail arrived*, which is exactly what makes a forged
    notification worth nothing.
    """
    owner_id = db.execute(
        sa.select(Owner.id).order_by(Owner.created_at).limit(1)
    ).scalar_one_or_none()
    if owner_id is None:
        raise NoOwnerYet("no owner account exists yet")

    db.execute(
        pg_insert(InboundMessage)
        .values(
            owner_id=owner_id,
            ses_message_id=notice.ses_message_id,
            s3_object_key=notice.s3_object_key,
            ses_sender_verdict=normalise_verdict(notice.dmarc_verdict),
            ses_scan_verdict=_scan_verdict(notice),
            received_at=notice.received_at,
            from_address=notice.from_address,
            subject=normalise_subject(notice.subject),
            state="pending_ingest",
        )
        .on_conflict_do_nothing(constraint="uq_inbound_message_ses_id")
    )

    db.execute(
        pg_insert(InboundDeliveryStatus)
        .values(owner_id=owner_id, last_received_at=notice.received_at)
        .on_conflict_do_update(
            index_elements=[InboundDeliveryStatus.owner_id],
            set_={"last_received_at": notice.received_at},
        )
    )
    db.flush()


def _scan_verdict(notice: DeliveryNotice) -> str:
    """One stored scan verdict out of SES's two, the worse of them winning.

    Stored as one column because the owner's remedy is identical either way and
    the policy treats them identically; keeping the *failing* one means the row
    says why it was quarantined rather than that something was fine.
    """
    spam = normalise_verdict(notice.spam_verdict)
    virus = normalise_verdict(notice.virus_verdict)
    return spam if spam != "PASS" else virus


__all__ = ["owner_router", "public_router"]


# --------------------------------------------------------------------------- #
# The owner's inbox
# --------------------------------------------------------------------------- #

#: How many messages one list page returns. A page rather than everything
#: because the inbox only grows, and "he has not deleted anything in a year" is
#: a normal state under A10 rather than an exotic one.
PAGE_SIZE = 50

#: The states the inbox list shows. `pending_ingest` and `deferred` are visible
#: on purpose: a message that has arrived but is not yet readable is still news,
#: and hiding it would make a slow ingestion indistinguishable from no mail.
LISTED_STATES = ("pending_ingest", "deferred", "received", "routed", "unrouted")


def _s3_fetcher_factory(inbox: InboxSettings) -> S3Fetcher:
    return S3Fetcher(inbox)


_fetcher_factory: Callable[[InboxSettings], S3Fetcher] = _s3_fetcher_factory


def get_s3_fetcher(inbox: ConfiguredInbox) -> S3Fetcher:
    """The seam the recovery routes reach S3 through, and the one tests replace.

    A dependency rather than a module-level client so the tests that drive
    *Trust this sender* and *Release this message* exercise the real handlers
    without any suite run touching AWS.
    """
    return _fetcher_factory(inbox)


def set_s3_fetcher_factory(factory: Callable[[InboxSettings], S3Fetcher]) -> None:
    global _fetcher_factory
    _fetcher_factory = factory


Fetcher = Annotated["S3Fetcher", Depends(get_s3_fetcher)]


def _attachment_counts(db: OrmSession, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """One grouped query for a page of messages, rather than one query per row.

    The list is the screen's first paint, so an N+1 here is the difference
    between an inbox that opens and one that feels broken.
    """
    if not message_ids:
        return {}

    rows = db.execute(
        sa.select(Attachment.inbound_message_id, sa.func.count())
        .where(Attachment.inbound_message_id.in_(message_ids))
        .group_by(Attachment.inbound_message_id)
    ).all()
    return {message_id: int(count) for message_id, count in rows}


def _quarantine_decision(db: OrmSession, message: InboundMessage, owner: Owner,
                         inbox: InboxSettings) -> SenderDecision:
    """Re-run the sender policy now, rather than trusting what was stored.

    The stored `routing_reason` is a record of what was decided when the message
    arrived; the *offer* has to reflect what is true now. An address the owner
    trusted five minutes ago must not still be offered a *Trust this sender*
    button, and a policy that has been tightened since must not have its old,
    laxer answer replayed back at him.
    """
    return decide_stored_sender(
        from_address=message.from_address,
        sender_verdict=message.ses_sender_verdict,
        scan_verdict=message.ses_scan_verdict,
        allowed=allowed_senders_for(db, owner, inbox),
    )


@owner_router.get("/summary", response_model=InboxSummary)
def get_summary(db: DbSession, owner: CurrentOwner, settings: AppSettings) -> InboxSummary:
    """The badge's query.

    Deliberately **not** behind `require_inbox`: the screen has to be able to
    render its "not configured" state, and a summary that answered `409` would
    make the nav badge's absence look like a failure rather than a setting.
    """
    inbox = settings.inbox
    if inbox is None:
        return InboxSummary(
            inbox_enabled=False,
            address=None,
            unrouted=0,
            quarantined=0,
            last_received_at=None,
            last_error_at=None,
            last_error=None,
        )

    counts = dict(
        db.execute(
            sa.select(InboundMessage.state, sa.func.count())
            .where(
                InboundMessage.owner_id == owner.id,
                InboundMessage.state.in_(("unrouted", "quarantined")),
            )
            .group_by(InboundMessage.state)
        ).all()
    )
    status_row = db.get(InboundDeliveryStatus, owner.id)

    return InboxSummary(
        inbox_enabled=True,
        address=inbox.recipient,
        unrouted=int(counts.get("unrouted", 0)),
        quarantined=int(counts.get("quarantined", 0)),
        last_received_at=status_row.last_received_at if status_row else None,
        last_error_at=status_row.last_error_at if status_row else None,
        last_error=status_row.last_error if status_row else None,
    )


@owner_router.get("/messages", response_model=list[InboxMessageRow])
def list_messages(
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
    state: str | None = None,
    limit: int = PAGE_SIZE,
) -> list[InboxMessageRow]:
    """The inbox list, newest first. **Metadata only, never the body.**

    An unknown `state` filter answers an empty list rather than an error: the
    parameter names a state the product has, and a client asking for one it does
    not have is asking about something that legitimately has no rows.
    """
    query = sa.select(InboundMessage).where(
        InboundMessage.owner_id == owner.id,
        InboundMessage.state.in_((state,) if state else LISTED_STATES),
    )
    messages = list(
        db.execute(
            query.order_by(InboundMessage.received_at.desc()).limit(min(max(limit, 1), PAGE_SIZE))
        ).scalars()
    )
    # Quarantined messages are never in this list, whatever `state` asks for:
    # they have their own route precisely so that showing them is a separate,
    # deliberate act.
    messages = [one for one in messages if one.state in LISTED_STATES]

    counts = _attachment_counts(db, [one.id for one in messages])
    return [
        InboxMessageRow.model_validate(
            {**_row_fields(one), "attachment_count": counts.get(one.id, 0)}
        )
        for one in messages
    ]


def _row_fields(message: InboundMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "received_at": message.received_at,
        "from_address": message.from_address,
        "subject": message.subject,
        "state": message.state,
        "trip_id": message.trip_id,
        "routing_reason": message.routing_reason,
        "last_error": message.last_error,
    }


@owner_router.get("/messages/{message_id}", response_model=InboxMessageDetail)
def get_message(
    message_id: uuid.UUID, db: DbSession, owner: CurrentOwner, inbox: ConfiguredInbox
) -> InboxMessageDetail:
    """One message: its headers, its text **as text**, and its documents.

    A quarantined message is a `404` here. Its content is exactly what quarantine
    exists to withhold, and serving it from the detail route "because the owner
    asked" would make the barrier a formality — `/inbox/quarantine/{id}` is the
    route for what he may see, and it carries headers only.
    """
    message = find_message(db, owner, message_id)
    if message.state == "quarantined":
        raise ApiError(ErrorCode.NOT_FOUND, field="message_id")

    attachments = list(
        db.execute(
            sa.select(Attachment)
            .where(Attachment.inbound_message_id == message.id)
            .order_by(Attachment.created_at)
        ).scalars()
    )

    return InboxMessageDetail.model_validate(
        {
            **_row_fields(message),
            "attachment_count": len(attachments),
            "text_body": message.text_body,
            "attachments": [InboxAttachmentRead.model_validate(one) for one in attachments],
        }
    )


@owner_router.post("/messages/{message_id}/place", response_model=InboxMessageRow)
def place_message(
    message_id: uuid.UUID,
    body: PlaceRequest,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
) -> InboxMessageRow:
    """Hand placement out of the unrouted queue.

    **This changes exactly one column: `inbound_message.trip_id`.** It writes
    nothing to the plan, moves no document onto an item and creates no action
    item — which is why `inbound_action_item` does not need to exist for Phase 1
    to be useful. The owner is classifying his own mail, not approving a change
    to a trip, and D21 still governs every later plan write.

    A trip that is not his answers `422 message_not_routable` rather than `404`:
    the message is his and the route is right, so the thing that is wrong is a
    value in the body, which is what 422 means everywhere else in this API.
    """
    message = find_message(db, owner, message_id)
    if message.state == "quarantined":
        raise ApiError(ErrorCode.NOT_FOUND, field="message_id")

    trip = db.execute(
        sa.select(Trip).where(Trip.id == body.trip_id, Trip.owner_id == owner.id)
    ).scalar_one_or_none()
    if trip is None:
        raise ApiError(ErrorCode.MESSAGE_NOT_ROUTABLE, field="trip_id")

    message.trip_id = trip.id
    message.state = "routed"
    # A translation key with no arguments, never prose — the same discipline the
    # routing reasons a model produces will have to follow in Phase 2.
    message.routing_reason = "placed_by_hand"
    db.flush()

    counts = _attachment_counts(db, [message.id])
    return InboxMessageRow.model_validate(
        {**_row_fields(message), "attachment_count": counts.get(message.id, 0)}
    )


@owner_router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: uuid.UUID,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
) -> Response:
    """Delete a message and its documents. His mail, his decision (A10).

    Two shapes, decided by whether a raw S3 object is still outstanding:

    - **nothing left in S3** — the row is hard-deleted immediately, and the
      documents go with it through the cascade. Nothing is left to tidy up.
    - **an object still there** — the row becomes a `discarded` tombstone,
      hidden from every route, and the cleanup pass deletes the object and then
      the row. Deleting the row first would lose the only record of which object
      to delete, leaving a private copy of his confirmation in S3 until the
      lifecycle rule notices it a month later.
    """
    message = find_message(db, owner, message_id)

    if message.s3_object_key is None:
        db.execute(sa.delete(InboundMessage).where(InboundMessage.id == message.id))
    else:
        message.state = "discarded"
        # The documents go now — he asked for them gone, and the tombstone only
        # needs to remember the S3 key.
        db.execute(sa.delete(Attachment).where(Attachment.inbound_message_id == message.id))
    db.flush()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# Quarantine, and the two ways out of it
# --------------------------------------------------------------------------- #


def _find_quarantined(
    db: OrmSession, owner: Owner, message_id: uuid.UUID
) -> InboundMessage:
    message = find_message(db, owner, message_id)
    if message.state != "quarantined":
        raise ApiError(ErrorCode.NOT_FOUND, field="message_id")
    return message


@owner_router.get("/quarantine", response_model=list[QuarantineRead])
def list_quarantined(
    db: DbSession, owner: CurrentOwner, inbox: ConfiguredInbox
) -> list[QuarantineRead]:
    """The quarantined messages, **headers only**, behind the screen's *Show*.

    A list route beside the singular one, because the screen's *Show* action has
    to be able to render the list at all and the summary deliberately carries
    only a count — it is the badge's cheap poll, and putting sender addresses in
    it would mean every page load fetched strangers' headers whether or not
    anyone asked to see them.

    Separate from `GET /inbox/messages` rather than a filter on it, and that
    separation is the control: showing quarantined mail is a distinct, explicit
    act, so it is a distinct, explicit route. This one cannot serve a body or an
    attachment, because `QuarantineRead` has no field for either.
    """
    messages = list(
        db.execute(
            sa.select(InboundMessage)
            .where(
                InboundMessage.owner_id == owner.id,
                InboundMessage.state == "quarantined",
            )
            .order_by(InboundMessage.received_at.desc())
            .limit(PAGE_SIZE)
        ).scalars()
    )

    return [_quarantine_read(db, message, owner, inbox) for message in messages]


@owner_router.get("/quarantine/{message_id}", response_model=QuarantineRead)
def get_quarantined(
    message_id: uuid.UUID, db: DbSession, owner: CurrentOwner, inbox: ConfiguredInbox
) -> QuarantineRead:
    """Sender, subject and date. **Never a body, an attachment or a preview.**"""
    return _quarantine_read(
        db, _find_quarantined(db, owner, message_id), owner, inbox
    )


def _quarantine_read(
    db: OrmSession, message: InboundMessage, owner: Owner, inbox: InboxSettings
) -> QuarantineRead:
    decision = _quarantine_decision(db, message, owner, inbox)

    return QuarantineRead(
        id=message.id,
        received_at=message.received_at,
        from_address=message.from_address,
        subject=message.subject,
        reason=message.routing_reason,
        may_trust_sender=decision.may_trust_sender,
        may_release_message=decision.may_release_message,
        # Both actions need the raw object, so an expired one means neither can
        # work — said on the row rather than discovered by pressing a button.
        recoverable=message.s3_object_key is not None,
    )


@owner_router.post("/quarantine/{message_id}/trust-sender", response_model=InboxMessageRow)
def trust_sender(
    message_id: uuid.UUID,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
    fetcher: Fetcher,
) -> InboxMessageRow:
    """Add this sender to the allow-list permanently, then ingest this message.

    Offered **only** where SES said the message authenticated and the address was
    simply unknown. Offering it for a DMARC failure would add a spoofable address
    to the allow-list for ever on the strength of one message the owner
    recognised the subject of — a policy change dressed up as a recovery.

    The decision is re-derived here rather than read off the row, so an address
    that has become trusted (or a policy that has been tightened) since the
    message arrived cannot have its old answer replayed.
    """
    message = _find_quarantined(db, owner, message_id)
    decision = _quarantine_decision(db, message, owner, inbox)
    if not decision.may_trust_sender:
        raise ApiError(ErrorCode.MESSAGE_NOT_ROUTABLE, field="message_id")

    db.execute(
        pg_insert(InboundTrustedSender)
        .values(owner_id=owner.id, address=normalise_address(message.from_address))
        .on_conflict_do_nothing()
    )
    db.flush()

    return _recover(db, message, owner, inbox, fetcher, bypass_sender_policy=False)


@owner_router.post("/quarantine/{message_id}/release", response_model=InboxMessageRow)
def release_message(
    message_id: uuid.UUID,
    db: DbSession,
    owner: CurrentOwner,
    inbox: ConfiguredInbox,
    fetcher: Fetcher,
) -> InboxMessageRow:
    """Accept **this one message**, despite its verdict. Trust nobody, change no policy.

    The narrowness is the control. It applies to one stored SES object, it adds
    no address to any list, and the next message from the same sender is
    quarantined exactly as this one was. That is what makes it safe to offer for
    the genuine false positive this exists for — the mailbox rule that
    auto-forwards an airline's confirmation while breaking its DMARC alignment.

    A failed *scan* is never releasable: `may_release_message` is false for it,
    because a virus verdict is not a false positive the owner is in a position
    to overrule.
    """
    message = _find_quarantined(db, owner, message_id)
    decision = _quarantine_decision(db, message, owner, inbox)
    if not decision.may_release_message:
        raise ApiError(ErrorCode.MESSAGE_NOT_ROUTABLE, field="message_id")

    return _recover(db, message, owner, inbox, fetcher, bypass_sender_policy=True)


def _recover(
    db: OrmSession,
    message: InboundMessage,
    owner: Owner,
    inbox: InboxSettings,
    fetcher: S3Fetcher,
    *,
    bypass_sender_policy: bool,
) -> InboxMessageRow:
    """Re-check the recorded metadata, then ingest — the shared half of both actions.

    **The metadata re-check is not ceremony.** Both actions reach S3 with a key
    read back out of the database, so before anything is fetched this confirms
    the row still carries its SES id and a key this deployment owns. A row whose
    locator was cleared, or whose key points outside the configured prefix, is
    refused rather than read.

    Ingestion itself is the **same function the worker calls**, with the same
    windows, the same storage ceiling, the same sniffing and the same failure
    handling. Only the one check the owner explicitly overruled is skipped, and
    only on release.
    """
    if not message.s3_object_key or not inbox.owns_object_key(message.s3_object_key):
        raise ApiError(ErrorCode.INBOX_OBJECT_UNAVAILABLE, field="message_id")

    outcome = ingest_message(
        db,
        message,
        owner=owner,
        inbox=inbox,
        fetcher=fetcher,
        bypass_sender_policy=bypass_sender_policy,
    )

    if outcome.state == "deferred":
        # The owner asked for this one now, and the window said not yet. A 429
        # rather than a silent deferral, because he is standing there waiting.
        raise ApiError(ErrorCode.INBOX_RATE_LIMITED, field="message_id")
    if outcome.reason == "inbox_object_unavailable":
        raise ApiError(ErrorCode.INBOX_OBJECT_UNAVAILABLE, field="message_id")

    key = message.s3_object_key
    db.flush()
    if outcome.state == "received" and key and delete_ingested_object(fetcher, key):
        message.s3_object_key = None
        db.flush()

    counts = _attachment_counts(db, [message.id])
    return InboxMessageRow.model_validate(
        {**_row_fields(message), "attachment_count": counts.get(message.id, 0)}
    )
