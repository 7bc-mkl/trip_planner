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
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request, Response, status
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
    Owner,
)
from trip_planner.domain.inbound import normalise_subject, normalise_verdict
from trip_planner.errors import ApiError, ErrorCode
from trip_planner.inbound.ses import SignatureVerifier, verify_event
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
