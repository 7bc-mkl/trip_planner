"""The ingestion loop: the advisory lock, the commit order, and staying out of the way.

`run_once` is what these drive. The loop around it only adds sleeping and the
stop check, so testing the thread would mostly test `threading.Event`; the two
claims about the thread that *are* worth asserting — that it stops cleanly, and
that a hung S3 call does not delay the rest of the application — are here, and
both are about the loop's relationship to everything else rather than about its
own arithmetic.

The worker gets **real sessions against the test database**, not a stub: the
advisory lock and `SKIP LOCKED` are PostgreSQL behaviours, and a test that mocked
the session would assert that mocks work.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from tests.conftest import TEST_ENVIRONMENT
from tests.test_inbox_ingest import PREFIX, StubS3, mime
from trip_planner.config import Settings, require_settings
from trip_planner.db.models import InboundMessage, Owner
from trip_planner.scheduler import INBOX_WORKER_LOCK_KEY, InboxWorker, start_inbox_worker

INBOX_ENV = {
    "INBOX_RECIPIENT": "inbox@mail.planner.example.com",
    "INBOX_AWS_REGION": "eu-central-1",
    "INBOX_SNS_TOPIC_ARN": "arn:aws:sns:eu-central-1:123456789012:trip-planner-inbound",
    "INBOX_S3_BUCKET": "trip-planner-inbound-mime",
    "INBOX_S3_PREFIX": PREFIX,
}


@pytest.fixture
def inbox_settings(database_url: str) -> Settings:
    return require_settings({"DATABASE_URL": database_url, **TEST_ENVIRONMENT, **INBOX_ENV})


@pytest.fixture
def plain_settings(database_url: str) -> Settings:
    return require_settings({"DATABASE_URL": database_url, **TEST_ENVIRONMENT})


@pytest.fixture
def worker_sessions(engine: sa.Engine) -> Iterator[sessionmaker[OrmSession]]:
    """A real session factory, so the worker behaves as it does in production.

    Deliberately **not** the rolled-back `db_session`: the worker commits, and a
    test that handed it a session inside an outer transaction would be asserting
    about a commit that never reached the database.
    """
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield factory


@pytest.fixture
def committed_owner(worker_sessions: sessionmaker[OrmSession]) -> Iterator[Owner]:
    """An owner that really exists, cleaned up afterwards.

    Everything this test module writes cascades from this row, so one `DELETE`
    at the end is the whole teardown.
    """
    from trip_planner.security.passwords import hash_password

    with worker_sessions() as db:
        owner = Owner(
            email=f"worker-{uuid.uuid4().hex}@example.com",
            password_hash=hash_password("irrelevant"),
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)
        owner_id = owner.id

    with worker_sessions() as db:
        yield db.get(Owner, owner_id)  # type: ignore[misc]

    with worker_sessions() as db:
        db.execute(sa.delete(Owner).where(Owner.id == owner_id))
        db.commit()


def add_message(
    sessions: sessionmaker[OrmSession], owner: Owner, *, key: str = f"{PREFIX}ses-1", **overrides
) -> uuid.UUID:
    fields: dict[str, object] = {
        "owner_id": owner.id,
        "ses_message_id": f"ses-{uuid.uuid4().hex}",
        "s3_object_key": key,
        "ses_sender_verdict": "PASS",
        "ses_scan_verdict": "PASS",
        "received_at": datetime.now(UTC),
        "from_address": owner.email,
        "subject": "Potwierdzenie rezerwacji",
        "state": "pending_ingest",
    }
    fields.update(overrides)
    with sessions() as db:
        record = InboundMessage(**fields)
        db.add(record)
        db.commit()
        return record.id


def reload(sessions: sessionmaker[OrmSession], message_id: uuid.UUID) -> InboundMessage:
    with sessions() as db:
        return db.get(InboundMessage, message_id)  # type: ignore[return-value]


def make_worker(
    settings: Settings, sessions: sessionmaker[OrmSession], s3: StubS3
) -> InboxWorker:
    return InboxWorker(settings, sessions, fetcher=s3, interval=timedelta(seconds=0.01))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# A pass
# --------------------------------------------------------------------------- #


def test_a_pass_ingests_a_pending_message_and_commits_it(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    message_id = add_message(worker_sessions, committed_owner)
    s3 = StubS3({f"{PREFIX}ses-1": mime(sender=committed_owner.email, text="PNR: SX-9912L")})

    assert make_worker(inbox_settings, worker_sessions, s3).run_once() == 1

    stored = reload(worker_sessions, message_id)
    assert stored.state == "received"
    assert stored.text_body == "PNR: SX-9912L"


def test_an_ingested_object_is_deleted_only_after_the_commit(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """And the locator is cleared only after the delete actually succeeded.

    The sequence is the crash-safety story: message committed, object deleted,
    locator cleared. A process dying at any point leaves either an orphaned
    object the lifecycle expires, or a locator pointing at an object already
    gone — never a deleted object and no message.
    """
    message_id = add_message(worker_sessions, committed_owner)
    s3 = StubS3({f"{PREFIX}ses-1": mime(sender=committed_owner.email)})

    make_worker(inbox_settings, worker_sessions, s3).run_once()

    assert s3.deleted == [f"{PREFIX}ses-1"]
    assert reload(worker_sessions, message_id).s3_object_key is None


def test_a_failed_delete_leaves_the_message_stored_and_the_locator_intact(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """The orphan case, which is the acceptable half of the trade."""

    class Unreliable(StubS3):
        def delete(self, key: str) -> None:
            raise TimeoutError("s3 delete timed out")

    message_id = add_message(worker_sessions, committed_owner)
    s3 = Unreliable({f"{PREFIX}ses-1": mime(sender=committed_owner.email)})

    make_worker(inbox_settings, worker_sessions, s3).run_once()

    stored = reload(worker_sessions, message_id)
    assert stored.state == "received"
    assert stored.s3_object_key == f"{PREFIX}ses-1"


def test_a_transient_s3_failure_is_recorded_and_the_message_stays_retryable(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    message_id = add_message(worker_sessions, committed_owner)
    s3 = StubS3()
    s3.fail_with = TimeoutError("s3 timed out")

    make_worker(inbox_settings, worker_sessions, s3).run_once()

    stored = reload(worker_sessions, message_id)
    assert stored.state == "pending_ingest"
    assert stored.attempts == 1
    assert stored.last_error == "ingest_failed"


def test_a_pass_with_nothing_to_do_processes_nothing(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    assert make_worker(inbox_settings, worker_sessions, StubS3()).run_once() == 0


# --------------------------------------------------------------------------- #
# Two workers
# --------------------------------------------------------------------------- #


def test_a_second_worker_finds_the_lock_taken_and_does_nothing(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """The rolling-deploy case: two loops for a few seconds, one message.

    Both fetching it would store its documents twice. `pg_try_advisory_lock` —
    *try*, not the blocking form — means the second finds the lock taken and
    returns, rather than holding a connection to then do redundant work.
    """
    add_message(worker_sessions, committed_owner)
    s3 = StubS3({f"{PREFIX}ses-1": mime(sender=committed_owner.email)})
    first = make_worker(inbox_settings, worker_sessions, s3)
    second = make_worker(inbox_settings, worker_sessions, s3)

    holder = worker_sessions()
    try:
        assert first._take_lock(holder) is True
        # The lock is genuinely exclusive across connections, which is the
        # property the whole arrangement rests on.
        assert second.run_once() == 0
    finally:
        first._release_lock(holder)
        holder.close()

    # Released, so the next pass does the work.
    assert second.run_once() == 1


def test_concurrent_passes_process_a_message_exactly_once(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """Two real threads over one real message — the property, not a proxy for it."""
    message_id = add_message(worker_sessions, committed_owner)
    s3 = StubS3({f"{PREFIX}ses-1": mime(sender=committed_owner.email)})
    ready = threading.Barrier(2)
    processed: list[int] = []

    def pass_once() -> None:
        worker = make_worker(inbox_settings, worker_sessions, s3)
        ready.wait(timeout=5)
        processed.append(worker.run_once())

    threads = [threading.Thread(target=pass_once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sum(processed) == 1
    assert s3.fetched == [f"{PREFIX}ses-1"]
    assert reload(worker_sessions, message_id).state == "received"


# --------------------------------------------------------------------------- #
# Off when unconfigured, and stopping cleanly
# --------------------------------------------------------------------------- #


def test_an_unconfigured_deployment_starts_no_worker(plain_settings: Settings) -> None:
    """No thread, no connection, no AWS client — "off" is genuinely inert."""
    assert start_inbox_worker(plain_settings) is None


def test_a_worker_cannot_be_constructed_without_inbox_settings(
    plain_settings: Settings, worker_sessions: sessionmaker[OrmSession]
) -> None:
    """Refused at construction rather than checked on every pass."""
    with pytest.raises(ValueError, match="inbox settings"):
        InboxWorker(plain_settings, worker_sessions)  # type: ignore[arg-type]


def test_the_loop_starts_and_stops_cleanly(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    worker = make_worker(inbox_settings, worker_sessions, StubS3())
    worker.start()
    try:
        assert any(thread.name == "inbox-worker" for thread in threading.enumerate())
    finally:
        worker.stop(timeout=10)

    assert not any(thread.name == "inbox-worker" for thread in threading.enumerate())


def test_a_hung_s3_call_does_not_hold_up_the_rest_of_the_application(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
    client,
) -> None:
    """The loop is on its own thread, so the event loop and the threadpool are free.

    Asserted by hanging an S3 read for as long as the test allows and serving
    `GET /health` while it hangs. Without the thread this is the request that
    would queue behind a mail fetch.
    """
    released = threading.Event()

    class Hanging(StubS3):
        def fetch(self, key: str) -> bytes:
            self.fetched.append(key)
            released.wait(timeout=30)
            return mime(sender=committed_owner.email)

    add_message(worker_sessions, committed_owner)
    worker = make_worker(inbox_settings, worker_sessions, Hanging())
    worker.start()
    try:
        # Give the loop a moment to reach the hanging fetch.
        for _ in range(200):
            if worker._fetcher.fetched:  # type: ignore[attr-defined]
                break
            threading.Event().wait(0.02)

        response = client.get("/api/v1/health")
        assert response.status_code == 200
    finally:
        released.set()
        worker.stop(timeout=15)


def test_a_pass_that_commits_still_releases_its_lock(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
    engine: sa.Engine,
) -> None:
    """The regression test for a silent, permanent outage.

    A session-level advisory lock belongs to the connection that took it, and
    SQLAlchemy returns a `Session`'s connection to the pool on every `commit()`.
    A pass commits several times — once per message, once for the cleanup — so a
    lock taken and released through the working session could be released on a
    *different* connection, leave the real one held, and make every later pass
    find the lock taken. The inbox would stop ingesting with no error anywhere.

    Asserted against `pg_locks` rather than by running a second pass, so the test
    names the actual condition instead of a symptom.
    """
    add_message(worker_sessions, committed_owner)
    s3 = StubS3({f"{PREFIX}ses-1": mime(sender=committed_owner.email)})

    assert make_worker(inbox_settings, worker_sessions, s3).run_once() == 1

    with engine.connect() as connection:
        held = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND objid = :key"
            ),
            {"key": INBOX_WORKER_LOCK_KEY & 0xFFFFFFFF},
        ).scalar_one()

    assert held == 0, "the ingestion loop leaked its advisory lock"


def test_repeated_passes_keep_working(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """The symptom the leak would have produced, covered from the other side."""
    s3 = StubS3()
    worker = make_worker(inbox_settings, worker_sessions, s3)

    for _ in range(3):
        add_message(worker_sessions, committed_owner)
        s3.objects[f"{PREFIX}ses-1"] = mime(sender=committed_owner.email)
        assert worker.run_once() == 1


def test_a_pass_runs_the_cleanup(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """Ingestion and tidying share a pass, in that order and in separate transactions.

    Separate so a cleanup failure cannot roll back messages that were
    successfully ingested a moment earlier.
    """
    from datetime import timedelta

    from trip_planner.inbound.cleanup import QUARANTINE_RETENTION

    expired = add_message(
        worker_sessions,
        committed_owner,
        state="quarantined",
        received_at=datetime.now(UTC) - QUARANTINE_RETENTION - timedelta(days=1),
    )
    s3 = StubS3({f"{PREFIX}ses-1": mime(sender=committed_owner.email)})

    make_worker(inbox_settings, worker_sessions, s3).run_once()

    with worker_sessions() as db:
        assert db.get(InboundMessage, expired) is None
    assert s3.deleted == [f"{PREFIX}ses-1"]
