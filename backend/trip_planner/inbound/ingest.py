"""Taking one recorded delivery and turning it into a message the owner can read.

This is the half of the inbound path that does real work, and it runs **off the
request path** — the SNS endpoint records that mail arrived and returns; the
worker in `scheduler.py` calls into this module. A slow S3 GET therefore cannot
delay an SNS acknowledgement or `GET /health`.

The order of operations is the security control, and two steps of it are not
interchangeable:

1. **The sender policy runs before the S3 GET.** Everything it needs — the SES
   verdicts and the `From` SES saw — is already on the row, committed by the
   endpoint from a signed notification. A rejected sender therefore costs one
   `UPDATE` and **no download at all**: nothing an unknown sender writes reaches
   this application's storage, and the private S3 copy expires on its own.
2. **The database commit happens before the S3 delete.** The other order risks a
   deleted object and no message, which is the one outcome that loses the
   owner's mail outright. This order risks an orphaned object instead, which the
   bucket's lifecycle rule expires and which the cleanup pass retries.

The failure modes are deliberately different from one another, because they mean
different things to the owner:

- **transient** (S3 timed out, the network blinked) — `attempts` goes up, the row
  stays where it is, and the loop tries again. Past the cap it lands in the
  unrouted queue with a reason he can read, so a broken integration degrades to
  a queue rather than to lost mail.
- **gone** (the object expired under the 30-day lifecycle, or was deleted) — not
  retryable, so retrying would burn the cap for nothing. It goes straight to the
  queue with `inbox_object_unavailable`, headers intact.
- **refused** (the sender policy said no) — quarantined, with no body and no
  document stored, and with whichever recovery action the reason permits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.config import InboxSettings
from trip_planner.db.models import (
    InboundDeliveryStatus,
    InboundMessage,
    InboundTrustedSender,
    Owner,
)
from trip_planner.domain.inbound import decide_stored_sender, select_content
from trip_planner.inbound.ses import ObjectGone, S3Fetcher
from trip_planner.inbound.storage import store_inbound_attachment
from trip_planner.security.quota import QuotaRejection, get_inbox_quota

logger = logging.getLogger(__name__)

__all__ = [
    "INGESTABLE_STATES",
    "MAX_INGEST_ATTEMPTS",
    "IngestOutcome",
    "allowed_senders_for",
    "delete_ingested_object",
    "claim_pending",
    "ingest_message",
]

#: How many transient failures one message is given before it lands in the queue.
#:
#: Five, spread over the loop's interval, covers a restart or a brief S3 blip
#: comfortably. The cap exists because a retry loop with no end is how a single
#: poisonous message keeps a worker permanently busy — and because "still
#: retrying" is indistinguishable from "working" to the owner, whereas a message
#: in the unrouted queue with a reason is not.
MAX_INGEST_ATTEMPTS = 5

#: The states the worker will pick up. `deferred` is here because an exhausted
#: inbound window is a *later* retry, not a refusal.
INGESTABLE_STATES = ("pending_ingest", "deferred")


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    """What happened to one message, for the worker's log and for tests to assert on."""

    state: str
    #: Set when the sender policy or a failure gave a reason. A translation key
    #: suffix, never prose — the screen renders it through i18next.
    reason: str | None = None
    documents_stored: int = 0
    documents_dropped: int = 0
    fetched_from_s3: bool = False


def allowed_senders_for(db: OrmSession, owner: Owner, inbox: InboxSettings) -> frozenset[str]:
    """The union of the three things that make an address acceptable.

    The owner's own account address is always in it and is **not** configuration:
    an installation where the owner cannot forward his own mail to himself would
    be broken out of the box, and requiring him to list himself is a step whose
    only possible outcome is forgetting it.

    The configured list is the deployment's; the trusted table is what the owner
    added through quarantine recovery. A new deployment with an empty table
    therefore still trusts exactly what is configured — the control's default
    does not depend on a table having rows.
    """
    trusted = db.execute(
        sa.select(InboundTrustedSender.address).where(InboundTrustedSender.owner_id == owner.id)
    ).scalars()

    return frozenset({owner.email.strip().lower(), *inbox.allowed_senders, *trusted})


def claim_pending(db: OrmSession, *, limit: int = 10) -> list[InboundMessage]:
    """The next messages to work on, oldest first.

    `SKIP LOCKED` on top of the worker's advisory lock, not instead of it. The
    advisory lock is what makes one worker run the loop; this is the backstop for
    the moment there are two — during a rolling deploy, say — and it costs
    nothing when there is one.
    """
    return list(
        db.execute(
            sa.select(InboundMessage)
            .where(InboundMessage.state.in_(INGESTABLE_STATES))
            .order_by(InboundMessage.received_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).scalars()
    )


def ingest_message(
    db: OrmSession,
    message: InboundMessage,
    *,
    owner: Owner,
    inbox: InboxSettings,
    fetcher: S3Fetcher,
    now: datetime | None = None,
    bypass_sender_policy: bool = False,
) -> IngestOutcome:
    """Apply the sender policy, fetch if allowed, store what is worth keeping.

    Does **not** commit: the caller owns the transaction, so a message and its
    documents land together or not at all, and a crash half way leaves neither a
    body without its attachments nor attachments without their message.

    `bypass_sender_policy` is the *Release this message* action and nothing else.
    It is a parameter rather than a second function so that every other rule —
    the windows, the storage ceiling, the part sniffing, the failure handling —
    is provably the same code on both paths; only the one check the owner
    explicitly overruled is skipped. The caller is responsible for having
    established that he may overrule it (`SenderDecision.may_release_message`)
    and for re-checking the message's stored metadata first.
    """
    moment = now or datetime.now(UTC)

    decision = decide_stored_sender(
        from_address=message.from_address,
        sender_verdict=message.ses_sender_verdict,
        scan_verdict=message.ses_scan_verdict,
        allowed=allowed_senders_for(db, owner, inbox),
    )
    if not decision.accepted and not bypass_sender_policy:
        # No GET. The private S3 copy stays for the recovery actions and expires
        # under the lifecycle rule; nothing this sender wrote enters our storage.
        #
        # `decide_sender` never returns a refusal without a reason, but the
        # fallback is written out rather than asserted: `assert` is stripped
        # under `python -O`, and a quarantine row with no reason renders as a
        # message the owner is given no way to recover.
        reason = decision.reason.value if decision.reason else "unknown_sender"
        message.state = "quarantined"
        message.routing_reason = reason
        return IngestOutcome(state="quarantined", reason=reason)

    quota = get_inbox_quota()

    # Before the GET, exactly like the upload path's `check_rate`: a limiter that
    # runs after the object has been downloaded refuses to *store* a flood but
    # not to *absorb* it.
    if quota.check_window(db, owner_id=owner.id, now=moment) is not None:
        return _defer(message, "inbox_rate_limited")

    # Already at the ceiling, decided before a byte is fetched. Checked again
    # below against the real document sizes, because this one only rules out the
    # case where there was no room for anything at all.
    if quota.check_storage(db, incoming_bytes=0) is not None:
        return _defer(message, "inbox_storage_full")

    key = message.s3_object_key
    if not key:
        return _to_queue(message, "inbox_object_unavailable")

    try:
        raw_mime = fetcher.fetch(key)
    except ObjectGone:
        # Expired or already deleted. Not retryable, so retrying would burn the
        # attempt cap for nothing and keep the message looking merely slow.
        logger.warning("inbox: the S3 object for a pending message is gone")
        return _to_queue(message, "inbox_object_unavailable")
    except Exception:
        return _defer_after_failure(db, message, owner, moment)

    selected = select_content(raw_mime)

    incoming = sum(len(document.data) for document in selected.documents)
    full = quota.check_storage(db, incoming_bytes=incoming)
    if full is QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED:
        # Nothing is stored and the S3 object is **not** deleted, so the message
        # is retried whole once the owner frees space. Storing the text and
        # dropping the documents would be the version that loses a voucher to a
        # ceiling the owner can clear in one click.
        return _defer(message, "inbox_storage_full")

    message.text_body = selected.text
    for document in selected.documents:
        store_inbound_attachment(db, message=message, document=document)

    message.state = "received"
    message.last_error = None
    db.flush()

    return IngestOutcome(
        state="received",
        documents_stored=len(selected.documents),
        documents_dropped=selected.dropped_documents,
        fetched_from_s3=True,
    )


def _defer(message: InboundMessage, reason: str) -> IngestOutcome:
    """An exhausted window or a full inbox: retried later, **never** quarantined.

    The distinction is the spec's and it matters to the owner: quarantine is the
    sender policy's answer and means *we will not take this*, while `deferred`
    means *not right now*. The row keeps its S3 locator, the worker picks it up
    again when capacity returns, and the bucket's lifecycle must outlast the
    deferral window — which is what the stale-object alarm watches for.
    """
    message.state = "deferred"
    message.last_error = reason
    return IngestOutcome(state="deferred", reason=reason)


def _to_queue(message: InboundMessage, reason: str) -> IngestOutcome:
    """Park a message in the unrouted queue with a reason the owner can read.

    Never a lost message and never a failed page: the headers are already
    stored, so what he sees is a real piece of mail he can look at and delete,
    rather than a gap where a confirmation should have been.
    """
    message.state = "unrouted"
    message.last_error = reason
    message.routing_reason = reason
    return IngestOutcome(state="unrouted", reason=reason)


def _defer_after_failure(
    db: OrmSession, message: InboundMessage, owner: Owner, moment: datetime
) -> IngestOutcome:
    """A transient failure: count it, record it, and leave the message retryable."""
    logger.exception("inbox: ingestion failed for a pending message")

    message.attempts += 1
    # A code, never the exception's text: an AWS or provider message can echo
    # the mail's own content back into our logs and our database.
    message.last_error = "ingest_failed"
    record_delivery_error(db, owner, moment, "ingest_failed")

    if message.attempts >= MAX_INGEST_ATTEMPTS:
        return _to_queue(message, "ingest_failed")

    message.state = "pending_ingest"
    return IngestOutcome(state="pending_ingest", reason="ingest_failed")


def record_delivery_error(
    db: OrmSession, owner: Owner, moment: datetime, code: str
) -> None:
    """Stamp the owner's freshness row, so the screen can be honest about failure.

    The screen showing "nothing new" while ingestion has been failing for a day
    is the exact dishonesty this row exists to prevent: an empty inbox and a
    broken inbox must not look the same.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    db.execute(
        pg_insert(InboundDeliveryStatus)
        .values(owner_id=owner.id, last_error_at=moment, last_error=code)
        .on_conflict_do_update(
            index_elements=[InboundDeliveryStatus.owner_id],
            set_={"last_error_at": moment, "last_error": code},
        )
    )
    db.flush()


def delete_ingested_object(fetcher: S3Fetcher, key: str) -> bool:
    """Delete the raw MIME object **after** its message has been committed.

    Best-effort and deliberately outside the transaction. A failure here leaves
    an orphaned private object that the bucket's 30-day lifecycle expires and
    that the cleanup pass retries — the acceptable half of the trade. Deleting
    first would risk an object gone and no message, which is the half that loses
    the owner's mail.
    """
    try:
        fetcher.delete(key)
    except Exception:
        logger.warning("inbox: could not delete an ingested S3 object; it will expire")
        return False
    return True
