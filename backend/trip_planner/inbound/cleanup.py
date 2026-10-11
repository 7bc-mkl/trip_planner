"""Tidying up after the inbox: the quarantine timer, and the objects left in S3.

Four jobs, each with a different reason for existing, and the differences are
worth keeping straight because they are easy to collapse into one "cleanup" that
does the wrong thing to one of them:

1. **The quarantine purge.** Quarantine is the only thing in this product a
   stranger can grow, so it is the only thing with a timer (A10). Thirty days is
   long enough for the owner to notice a false positive and short enough that
   headers from people who are not him do not accumulate for ever. **His own
   mail has no timer at all** — an app deleting a confirmation on a schedule is
   precisely the failure A03 is about.
2. **Finishing a discard.** `DELETE /inbox/messages/{id}` leaves a tombstone
   when a raw object is still outstanding, because hard-deleting the row first
   would lose the only record of which object to delete — leaving a private copy
   of his confirmation in S3 until the lifecycle rule noticed it a month later.
   This is the pass that deletes the object and then the row.
3. **Retrying an orphaned delete.** Ingestion commits before it deletes, so a
   failed delete leaves a stored message still carrying its locator. Retried
   here rather than left to the 30-day lifecycle, which would keep a second copy
   of the owner's mail in AWS for a month for no reason.
4. **The stale-object alarm.** A deferred message's object must be fetched
   before the bucket's lifecycle expires it. Nothing in this application can
   stop that clock, so what it can do is say so loudly while there is still time
   — which is the difference between an operator fixing a full inbox and an
   owner losing mail he never knew had arrived.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import InboundMessage
from trip_planner.inbound.ses import ObjectGone, S3Fetcher

logger = logging.getLogger(__name__)

__all__ = [
    "QUARANTINE_RETENTION",
    "S3_LIFECYCLE",
    "STALE_OBJECT_ALARM_MARGIN",
    "CleanupReport",
    "run_cleanup",
]

#: How long a quarantined message's headers are kept (A10).
QUARANTINE_RETENTION = timedelta(days=30)

#: The bucket lifecycle this application is documented against (README). Not
#: enforced from here — AWS owns that clock — but known, so the alarm below can
#: fire while there is still time to act.
S3_LIFECYCLE = timedelta(days=30)

#: How long before an object's expiry the alarm starts. A week is enough notice
#: to clear a full inbox or fix a broken integration by hand.
STALE_OBJECT_ALARM_MARGIN = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class CleanupReport:
    """What one pass did, for the log and for the tests to assert on."""

    quarantine_purged: int = 0
    discards_completed: int = 0
    orphan_objects_deleted: int = 0
    stale_objects_alarmed: int = 0


def run_cleanup(
    db: OrmSession, fetcher: S3Fetcher, *, now: datetime | None = None
) -> CleanupReport:
    """Every tidy-up job, in one pass. Commits nothing — the caller owns that."""
    moment = now or datetime.now(UTC)

    return CleanupReport(
        quarantine_purged=_purge_quarantine(db, fetcher, moment),
        discards_completed=_complete_discards(db, fetcher),
        orphan_objects_deleted=_retry_orphan_deletes(db, fetcher),
        stale_objects_alarmed=_alarm_on_stale_objects(db, moment),
    )


def _purge_quarantine(db: OrmSession, fetcher: S3Fetcher, moment: datetime) -> int:
    """Delete quarantined rows past their retention, and their private S3 objects.

    The object goes first here, and the order is the opposite of ingestion's on
    purpose. Ingestion commits first because losing the *message* is the
    unacceptable outcome; a purge is deleting the message deliberately, so the
    unacceptable outcome is the reverse — a row gone while a stranger's raw mail
    stays in the bucket. If the delete fails the row survives to the next pass.

    An object already gone is a success, not a failure: the lifecycle rule may
    simply have got there first.
    """
    cutoff = moment - QUARANTINE_RETENTION
    expired = list(
        db.execute(
            sa.select(InboundMessage).where(
                InboundMessage.state == "quarantined",
                InboundMessage.received_at < cutoff,
            )
        ).scalars()
    )

    purged = 0
    for message in expired:
        if message.s3_object_key and not _delete_object(fetcher, message.s3_object_key):
            # Left for the next pass rather than deleted anyway.
            continue
        db.execute(sa.delete(InboundMessage).where(InboundMessage.id == message.id))
        purged += 1

    if purged:
        logger.info("inbox: purged %d expired quarantine row(s)", purged)
    return purged


def _complete_discards(db: OrmSession, fetcher: S3Fetcher) -> int:
    """Finish the deletes the owner asked for, now that the object can go too."""
    tombstones = list(
        db.execute(
            sa.select(InboundMessage).where(InboundMessage.state == "discarded")
        ).scalars()
    )

    completed = 0
    for message in tombstones:
        if message.s3_object_key and not _delete_object(fetcher, message.s3_object_key):
            continue
        db.execute(sa.delete(InboundMessage).where(InboundMessage.id == message.id))
        completed += 1

    return completed


def _retry_orphan_deletes(db: OrmSession, fetcher: S3Fetcher) -> int:
    """Delete objects whose message was stored but whose delete did not land.

    The locator is cleared only on success, so a message that still carries one
    after ingestion is exactly the failed-delete case. Retrying here keeps a
    second copy of the owner's mail out of AWS rather than waiting a month for
    the lifecycle rule.
    """
    stored = list(
        db.execute(
            sa.select(InboundMessage).where(
                InboundMessage.state.in_(("received", "routed", "unrouted")),
                InboundMessage.s3_object_key.isnot(None),
            )
        ).scalars()
    )

    deleted = 0
    for message in stored:
        key = message.s3_object_key
        if key and _delete_object(fetcher, key):
            message.s3_object_key = None
            deleted += 1

    if deleted:
        db.flush()
    return deleted


def _alarm_on_stale_objects(db: OrmSession, moment: datetime) -> int:
    """Warn about deferred messages whose object is approaching its expiry.

    This application cannot stop the bucket's clock, so what it can do is be
    loud while there is still time. A deferred message that expires quietly is
    mail the owner never learns arrived, which is the failure this whole
    feature exists to prevent.
    """
    cutoff = moment - (S3_LIFECYCLE - STALE_OBJECT_ALARM_MARGIN)
    stale = int(
        db.execute(
            sa.select(sa.func.count())
            .select_from(InboundMessage)
            .where(
                InboundMessage.state == "deferred",
                InboundMessage.s3_object_key.isnot(None),
                InboundMessage.received_at < cutoff,
            )
        ).scalar_one()
    )

    if stale:
        logger.error(
            "inbox: %d deferred message(s) have raw objects within %d days of expiring; "
            "they will be lost unless ingestion catches up",
            stale,
            STALE_OBJECT_ALARM_MARGIN.days,
        )
    return stale


def _delete_object(fetcher: S3Fetcher, key: str) -> bool:
    """`True` when the object is gone — including when it already was."""
    try:
        fetcher.delete(key)
    except ObjectGone:
        return True
    except Exception:
        logger.warning("inbox: could not delete an S3 object during cleanup; will retry")
        return False
    return True
