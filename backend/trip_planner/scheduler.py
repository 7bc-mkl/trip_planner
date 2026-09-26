"""The in-process ingestion loop.

**Why a thread and not a worker process.** A12 fixes the deployment at one
container and one managed database, and the spec rejects Celery, RQ or a second
container for exactly that reason. SNS already provides the durability a queue
would have bought — it retries, and its dead-letter queue catches what the
retries do not — so what is left for this application to do is drain rows that
are already committed in Postgres. That is a loop, and a loop needs a thread.

**Why its own `sessionmaker`.** The request-scoped session in `api/deps.py` is
tied to a request that does not exist here, and sharing a SQLAlchemy `Session`
across threads is a data race rather than a style preference. This loop opens
and closes its own.

**Why an advisory lock.** The deployment runs one `uvicorn --factory` process
today, so on paper one loop exists. But a rolling deploy runs two for a few
seconds, and two loops fetching the same object would both store its documents.
`pg_try_advisory_lock` means the second loop finds the lock taken and does
nothing at all, rather than doing the same work twice. It is *try*, not the
blocking form: a loop that blocked on the lock would hold a connection for the
whole of the other's run and then immediately do redundant work.

**Why a hung S3 call cannot take the application down.** The loop is on its own
thread with its own connection, so `GET /health` and the SNS endpoint are served
by the event loop and the threadpool untouched. The bound that remains — and it
is named here rather than left to be rediscovered — is one database connection
and one thread held for as long as the S3 read takes, which `S3Fetcher` caps
with a connect and read timeout.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.config import Settings
from trip_planner.db.models import Owner
from trip_planner.inbound.cleanup import CleanupReport, run_cleanup
from trip_planner.inbound.ingest import claim_pending, delete_ingested_object, ingest_message
from trip_planner.inbound.ses import S3Fetcher

logger = logging.getLogger(__name__)

__all__ = ["DEFAULT_INTERVAL", "INBOX_WORKER_LOCK_KEY", "InboxWorker", "start_inbox_worker"]

#: How long the loop sleeps between passes.
#:
#: Thirty seconds, because the latency that matters is a human one: the owner
#: forwards a confirmation and then goes to look at the app. Polling faster
#: would spend a database round trip a minute to shave seconds off a wait nobody
#: is timing; polling slower would make the inbox feel broken.
DEFAULT_INTERVAL = timedelta(seconds=30)

#: The advisory key the loop serialises on. In the same namespace as the upload
#: quota's keys, so it is picked to sit well away from them.
INBOX_WORKER_LOCK_KEY = 0x7A11_0C0D_E003

#: How many messages one pass handles before sleeping again. Bounded so a large
#: backlog is drained over several passes rather than in one transaction that
#: holds a connection for minutes.
BATCH_SIZE = 10


class InboxWorker:
    """The loop, as an object, so it can be started, stopped and — mostly — run once.

    `run_once` is the unit the tests drive. Everything the loop does happens
    there; `_loop` only adds sleeping and the stop check, which is the part worth
    having no assertions about.
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: Callable[[], OrmSession],
        *,
        fetcher: S3Fetcher | None = None,
        interval: timedelta = DEFAULT_INTERVAL,
    ) -> None:
        if settings.inbox is None:
            raise ValueError("the inbox worker cannot run on a deployment with no inbox settings")

        self._settings = settings
        self._inbox = settings.inbox
        self._session_factory = session_factory
        self._fetcher = fetcher if fetcher is not None else S3Fetcher(settings.inbox)
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ loop

    def start(self) -> None:
        if self._thread is not None:
            return
        # A daemon thread so a crashed or shutting-down process is never held
        # open by a loop mid-sleep; `stop()` is the orderly path and is what the
        # lifespan calls.
        self._thread = threading.Thread(target=self._loop, name="inbox-worker", daemon=True)
        self._thread.start()
        logger.info("inbox: ingestion loop started")

    def stop(self, timeout: float = 10.0) -> None:
        """Ask the loop to finish its current pass and exit.

        The event is checked between messages as well as between passes, so a
        shutdown during a backlog waits for one message rather than for the
        whole batch.
        """
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)
        logger.info("inbox: ingestion loop stopped")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                # Never let one bad pass end the loop: the next message is
                # probably fine, and a dead worker is indistinguishable from a
                # quiet inbox until somebody notices the backlog.
                logger.exception("inbox: an ingestion pass failed")
            self._stop.wait(self._interval.total_seconds())

    # ------------------------------------------------------------- one pass

    def run_once(self) -> int:
        """Ingest up to `BATCH_SIZE` messages. Returns how many were processed.

        **The lock is held on a session of its own, and that is not tidiness.**
        A session-level advisory lock belongs to the *connection* that took it,
        and SQLAlchemy returns a `Session`'s connection to the pool on every
        `commit()`. This pass commits several times — once per message, and once
        for the cleanup — so a lock taken and released through the working
        session can easily be released on a **different** connection than the one
        holding it. `pg_advisory_unlock` then answers false, the lock stays held
        for the life of that pooled connection, and every later pass finds it
        taken: the inbox silently stops ingesting until the process restarts.
        That is a permanent, silent outage, so the lock gets a session that never
        commits and therefore never lets go of its connection.

        The cost is one connection sitting idle in a transaction for the length
        of the pass. It is bounded by `BATCH_SIZE` and by `S3Fetcher`'s read
        timeout, it holds no row locks, and it is the cheap half of the trade.
        """
        with self._session_factory() as lock_session:
            if not self._take_lock(lock_session):
                # Another worker owns this pass. Doing nothing is the correct
                # outcome, not a failure.
                return 0
            try:
                with self._session_factory() as db:
                    return self._drain(db)
            finally:
                self._release_lock(lock_session)

    def _take_lock(self, db: OrmSession) -> bool:
        return bool(
            db.execute(
                sa.select(sa.func.pg_try_advisory_lock(sa.literal(INBOX_WORKER_LOCK_KEY)))
            ).scalar_one()
        )

    def _release_lock(self, db: OrmSession) -> None:
        db.execute(
            sa.select(sa.func.pg_advisory_unlock(sa.literal(INBOX_WORKER_LOCK_KEY)))
        ).scalar_one()

    def _drain(self, db: OrmSession) -> int:
        owner = db.execute(
            sa.select(Owner).order_by(Owner.created_at).limit(1)
        ).scalar_one_or_none()
        if owner is None:
            return 0

        processed = 0
        for message in claim_pending(db, limit=BATCH_SIZE):
            if self._stop.is_set():
                break

            outcome = ingest_message(
                db, message, owner=owner, inbox=self._inbox, fetcher=self._fetcher
            )
            key = message.s3_object_key

            # Commit **before** the delete. A crash between the two leaves an
            # orphaned private object that the bucket's lifecycle expires; the
            # other order would leave no object and no message.
            db.commit()
            processed += 1

            if outcome.state == "received" and key and delete_ingested_object(self._fetcher, key):
                message.s3_object_key = None
                db.commit()

        # After the ingestion, and in the same pass: the quarantine timer, the
        # deletes the owner asked for, the objects a failed delete left behind,
        # and the alarm. Its own transaction, so a cleanup failure cannot roll
        # back messages that were successfully ingested a moment ago.
        try:
            report = run_cleanup(db, self._fetcher)
            db.commit()
            if report != CleanupReport():
                logger.info("inbox: cleanup %s", report)
        except Exception:
            db.rollback()
            logger.exception("inbox: the cleanup pass failed; it will run again")

        return processed


def start_inbox_worker(settings: Settings) -> InboxWorker | None:
    """Start the loop, or don't — an unconfigured deployment gets `None`.

    Returning `None` rather than a worker that does nothing keeps "the inbox is
    off" genuinely inert: no thread, no connection, no AWS client and no
    credential resolution.
    """
    if settings.inbox is None:
        return None

    from trip_planner.db.session import get_sessionmaker

    worker = InboxWorker(settings, get_sessionmaker())
    worker.start()
    return worker
