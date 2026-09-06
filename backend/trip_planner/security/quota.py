"""The upload limits: per-owner windows, per-parent counts and locked byte quotas.

Modelled on `security/rate_limit.py`, and for the same reason: the counters live
in PostgreSQL rather than in a process-local dictionary because a public
deployment runs more than one worker, and an in-process counter would be
decorative — a caller would simply be load-balanced onto a fresh one.

The module has **two groups of checks and the distinction between them is the
whole point**:

- `check_rate` is the **memory control**, and it is callable with nothing but the
  owner and the session — deliberately, so it can run *before* the request body
  is read. See its docstring for why running it after the read would be a
  different, weaker control.
- `check_parent_capacity` and `check_byte_quotas` are the **correctness
  controls**, run inside the upload's transaction. The byte quotas take
  `pg_advisory_xact_lock` before summing; see `check_byte_quotas` for why a
  transaction alone is not enough.

Every limit value is a named constant with the reasoning for its value beside it
(spec assumption **A4**): the *shape* is what matters, not the number, and each
is changeable by a one-line PR.

Rejections are returned, not raised, and they carry the wire code rather than an
`ErrorCode` member: this module predates the members Step 1.5 adds, and the same
ordering is already resolved this way by `domain/uploads.py`'s `UploadRejection`
and `domain/money.py`'s `CostRejection`. The endpoints map them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import Attachment, Item, TripDay, UploadEvent

__all__ = [
    "INSTALLATION_LOCK_KEY",
    "MAX_ATTACHMENTS_PER_PARENT",
    "MAX_INSTALLATION_BYTES",
    "MAX_TRIP_BYTES",
    "MAX_UPLOADS_PER_RATE_WINDOW",
    "MAX_VOLUME_BYTES_PER_WINDOW",
    "RATE_WINDOW",
    "VOLUME_WINDOW",
    "QuotaRejection",
    "UploadQuota",
    "get_upload_quota",
    "set_upload_quota",
]

#: How long an upload counts against the *count* window.
RATE_WINDOW = timedelta(minutes=10)

#: Uploads allowed per owner inside `RATE_WINDOW`.
#:
#: Three a minute sustained. Attaching a day's boarding passes is a handful of
#: files; nothing an owner does by hand approaches thirty in ten minutes, so the
#: number is where a script becomes visible and a person does not.
MAX_UPLOADS_PER_RATE_WINDOW = 30

#: How long an upload's bytes count against the *volume* window.
#:
#: Longer than `RATE_WINDOW` on purpose: the two limits catch different shapes.
#: Thirty small files in ten minutes is a burst; two hundred megabytes spread
#: over an hour is a drain that the count window would never notice.
VOLUME_WINDOW = timedelta(hours=1)

#: Bytes allowed per owner inside `VOLUME_WINDOW`. 200 MB is twenty files at the
#: 10 MB per-file cap — well past a trip's worth of documents in one sitting,
#: and far below what would make the database's backup someone's problem.
MAX_VOLUME_BYTES_PER_WINDOW = 200 * 1024 * 1024

#: Attachments allowed on one parent — 20 per item, 20 per day (A4).
#:
#: A day with twenty documents on it is already past what the panel can show
#: usefully; the limit exists so a runaway client cannot turn one day into an
#: unbounded list, not because the twenty-first would be wrong in principle.
MAX_ATTACHMENTS_PER_PARENT = 20

#: Bytes allowed across one trip (A4). The files live in the application's own
#: PostgreSQL database, so this bound is a backup-size decision as much as an
#: abuse one: 250 MB per trip is a restorable dump on any hosted plan.
MAX_TRIP_BYTES = 250 * 1024 * 1024

#: Bytes allowed across the whole installation (A4), for the same reason one
#: size larger. Ten trips at their own cap, and a hard ceiling on how big the
#: database can get however many trips exist.
MAX_INSTALLATION_BYTES = 2 * 1024 * 1024 * 1024

#: The advisory key the installation-wide cap serialises on.
#:
#: Fixed, arbitrary, and picked to sit far away from anything `hashtext` of a
#: UUID string is likely to produce, since the two share one advisory-lock
#: namespace. A collision would only over-serialise — two unrelated uploads
#: waiting for each other — never under-serialise, but there is no reason to
#: invite it.
INSTALLATION_LOCK_KEY = 0x7A11_0C0D_E001


class QuotaRejection(StrEnum):
    """Why an upload was refused by a limit. The value is the wire code."""

    #: A per-owner window is full — the count window, the volume window, or both.
    #: Answered `429` by the endpoint.
    RATE_LIMITED = "rate_limited"
    #: The parent day or item already holds `MAX_ATTACHMENTS_PER_PARENT` files.
    ATTACHMENT_LIMIT_REACHED = "attachment_limit_reached"
    #: The trip's or the installation's byte quota would be exceeded. One code
    #: for both, as the spec's error table specifies: the owner's remedy is the
    #: same either way, and naming which ceiling was hit would tell an
    #: unauthenticated-adjacent caller how full the deployment is.
    TRIP_STORAGE_QUOTA_EXCEEDED = "trip_storage_quota_exceeded"


@dataclass(frozen=True, slots=True)
class UploadQuota:
    """Every upload limit, as data, so a test can shrink one without touching code."""

    rate_window: timedelta = RATE_WINDOW
    max_uploads_per_rate_window: int = MAX_UPLOADS_PER_RATE_WINDOW
    volume_window: timedelta = VOLUME_WINDOW
    max_volume_bytes_per_window: int = MAX_VOLUME_BYTES_PER_WINDOW
    max_attachments_per_parent: int = MAX_ATTACHMENTS_PER_PARENT
    max_trip_bytes: int = MAX_TRIP_BYTES
    max_installation_bytes: int = MAX_INSTALLATION_BYTES

    # ---------------------------------------------------------------- windows

    def _now(self, now: datetime | None) -> datetime:
        return now or datetime.now(UTC)

    def prune(self, db: OrmSession, *, now: datetime | None = None) -> None:
        """Delete `upload_event` rows outside every window.

        Lazily, on each check, exactly as `login_attempt` is pruned: there is no
        scheduler in this milestone, and a table that only grows is a slow leak
        rather than a limit. The cut-off is the *longest* window — pruning to the
        shorter one would silently disarm the volume limit.
        """
        oldest = self._now(now) - max(self.rate_window, self.volume_window)
        db.execute(sa.delete(UploadEvent).where(UploadEvent.occurred_at < oldest))

    def check_rate(
        self, db: OrmSession, *, owner_id: uuid.UUID, now: datetime | None = None
    ) -> QuotaRejection | None:
        """Whether this owner has filled either per-owner window. **Call before the read.**

        The signature is the point: an owner and a session, never the payload.
        This check must run *before* the request body is pulled into memory,
        because a limiter that runs after 10 MB has already been read refuses to
        *store* the flood but not to *absorb* it — a stolen session, the named
        adversary, could force unbounded repeated 10 MB reads while every quota
        politely declined. The endpoint calls it again inside the transaction,
        where it is the correctness check rather than the memory one.

        Both windows are counted in one pass over the same rows, because both
        are questions about the same events.
        """
        self.prune(db, now=now)
        moment = self._now(now)

        counted = db.execute(
            sa.select(
                sa.func.count().filter(UploadEvent.occurred_at >= moment - self.rate_window),
                sa.func.coalesce(
                    sa.func.sum(UploadEvent.byte_size).filter(
                        UploadEvent.occurred_at >= moment - self.volume_window
                    ),
                    0,
                ),
            )
            .select_from(UploadEvent)
            .where(UploadEvent.owner_id == owner_id)
        ).one()

        uploads, volume = int(counted[0]), int(counted[1])
        if uploads >= self.max_uploads_per_rate_window:
            return QuotaRejection.RATE_LIMITED
        if volume >= self.max_volume_bytes_per_window:
            return QuotaRejection.RATE_LIMITED
        return None

    def record_upload(
        self,
        db: OrmSession,
        *,
        owner_id: uuid.UUID,
        byte_size: int,
        now: datetime | None = None,
    ) -> None:
        """Log an upload against both windows, and prune what has aged out of them."""
        db.add(UploadEvent(owner_id=owner_id, byte_size=byte_size, occurred_at=self._now(now)))
        self.prune(db, now=now)
        db.flush()

    # ------------------------------------------------- in-transaction quotas

    def check_parent_capacity(
        self,
        db: OrmSession,
        *,
        item_id: uuid.UUID | None = None,
        trip_day_id: uuid.UUID | None = None,
    ) -> QuotaRejection | None:
        """Whether the parent day or item can hold one more attachment.

        Exactly one parent, mirroring the `attachment` table's own
        `CHECK ((item_id IS NULL) <> (trip_day_id IS NULL))` — a caller that
        passed both or neither would be asking a question the schema says has no
        answer, so it is a programming error rather than a rejection.
        """
        if (item_id is None) == (trip_day_id is None):
            raise ValueError("exactly one of item_id / trip_day_id must be given")

        parent = Attachment.item_id == item_id if item_id else Attachment.trip_day_id == trip_day_id
        count = db.execute(
            sa.select(sa.func.count()).select_from(Attachment).where(parent)
        ).scalar_one()

        if int(count) >= self.max_attachments_per_parent:
            return QuotaRejection.ATTACHMENT_LIMIT_REACHED
        return None

    def check_byte_quotas(
        self, db: OrmSession, *, trip_id: uuid.UUID, incoming_bytes: int
    ) -> QuotaRejection | None:
        """Whether `incoming_bytes` fit inside the trip's and the installation's caps.

        **Both quotas take an advisory lock before summing, and the lock is the
        whole reason this function exists rather than two inline `SUM`s.** Under
        PostgreSQL's default `READ COMMITTED`, two concurrent uploads each sum
        over committed rows, neither sees the other's uncommitted insert, and
        both pass a quota only one of them fits in — atomicity is not mutual
        exclusion. `pg_advisory_xact_lock` makes the read-then-write a critical
        section; it is released by the commit, so nothing has to remember to
        unlock, and it serialises uploads *within one trip* and nothing else.

        `SERIALIZABLE` with a retry loop was the alternative and it loses: it
        makes every unrelated request in the application a potential
        serialisation failure to handle, in exchange for a guarantee two
        advisory locks already give.

        **This must be called inside the upload's transaction.** An advisory
        *xact* lock taken in an autocommitted statement is released immediately,
        which would leave the sums exactly as racy as they were without it.
        """
        # The per-trip key. `hashtext` of the trip's id text, as the spec fixes
        # it, so the key is derived and no table of lock numbers has to exist.
        db.execute(
            sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtext(str(trip_id))))
        ).scalar_one()

        if self._trip_bytes(db, trip_id=trip_id) + incoming_bytes > self.max_trip_bytes:
            return QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED

        # A second, fixed key for the installation-wide cap. Taken after the
        # per-trip one, always in this order, because two locks acquired in
        # opposite orders by two transactions is the textbook deadlock.
        db.execute(
            sa.select(sa.func.pg_advisory_xact_lock(sa.literal(INSTALLATION_LOCK_KEY)))
        ).scalar_one()

        if self._installation_bytes(db) + incoming_bytes > self.max_installation_bytes:
            return QuotaRejection.TRIP_STORAGE_QUOTA_EXCEEDED

        return None

    def _trip_bytes(self, db: OrmSession, *, trip_id: uuid.UUID) -> int:
        """The bytes already stored under one trip.

        `attachment` deliberately carries no `trip_id` (see its model docstring),
        so the trip is reached through whichever parent the row has: a day
        directly, or an item's day. `COALESCE` over the two joins is that "one
        of two parents" expressed once.
        """
        day_id = sa.func.coalesce(Attachment.trip_day_id, Item.trip_day_id)
        return int(
            db.execute(
                sa.select(sa.func.coalesce(sa.func.sum(Attachment.byte_size), 0))
                .select_from(Attachment)
                .outerjoin(Item, Item.id == Attachment.item_id)
                .join(TripDay, TripDay.id == day_id)
                .where(TripDay.trip_id == trip_id)
            ).scalar_one()
        )

    def _installation_bytes(self, db: OrmSession) -> int:
        return int(
            db.execute(
                sa.select(sa.func.coalesce(sa.func.sum(Attachment.byte_size), 0)).select_from(
                    Attachment
                )
            ).scalar_one()
        )

    def check_within_transaction(
        self,
        db: OrmSession,
        *,
        owner_id: uuid.UUID,
        trip_id: uuid.UUID,
        incoming_bytes: int,
        item_id: uuid.UUID | None = None,
        trip_day_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> QuotaRejection | None:
        """Every in-transaction check, in the order the spec fixes.

        The cheap per-owner and per-parent counts first, the locked sums last, so
        a request that was going to be refused anyway does not take a lock other
        uploads then wait behind.
        """
        rejection = self.check_rate(db, owner_id=owner_id, now=now)
        if rejection is not None:
            return rejection

        rejection = self.check_parent_capacity(db, item_id=item_id, trip_day_id=trip_day_id)
        if rejection is not None:
            return rejection

        return self.check_byte_quotas(db, trip_id=trip_id, incoming_bytes=incoming_bytes)


_upload_quota = UploadQuota()


def get_upload_quota() -> UploadQuota:
    return _upload_quota


def set_upload_quota(quota: UploadQuota) -> None:
    """Override the quota. Tests use this to shrink a limit; nothing in production calls it."""
    global _upload_quota
    _upload_quota = quota
