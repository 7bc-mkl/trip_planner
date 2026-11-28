"""The worker function's app: one event drains the inbox, under a time budget.

Driven through the HTTP surface the Lambda Web Adapter uses — a `POST /events`
with whatever event JSON arrived — against real sessions on the test database,
for the same reason `test_scheduler.py` gives: the advisory lock and
`SKIP LOCKED` are PostgreSQL behaviours.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from tests import test_scheduler as scheduler_tests
from tests.conftest import TEST_ENVIRONMENT
from tests.test_inbox_ingest import PREFIX, StubS3, mime
from tests.test_scheduler import add_message, reload
from trip_planner.config import Settings, require_settings
from trip_planner.db.models import Owner
from trip_planner.scheduler import BATCH_SIZE
from trip_planner.worker_app import WORKER_BUDGET, create_worker_app

KICK = {"source": "trip-planner.kick"}

# The scheduler tests' fixtures, shared rather than copied: a real session
# factory, a committed owner, and settings with the inbox configured.
inbox_settings = scheduler_tests.inbox_settings
worker_sessions = scheduler_tests.worker_sessions
committed_owner = scheduler_tests.committed_owner


class FakeClock:
    """A monotonic clock that only moves when told to."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.fetch_cost = 0.0

    def __call__(self) -> float:
        return self.now


def backlog(sessions: sessionmaker[OrmSession], owner: Owner, s3: StubS3, count: int) -> list:
    ids = []
    for index in range(count):
        key = f"{PREFIX}ses-{index}"
        s3.objects[key] = mime(sender=owner.email, text=f"PNR: SX-{index:04d}")
        ids.append(add_message(sessions, owner, key=key))
    return ids


def test_one_event_drains_a_backlog_larger_than_a_batch(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    s3 = StubS3()
    ids = backlog(worker_sessions, committed_owner, s3, 25)
    assert len(ids) > 2 * BATCH_SIZE

    app = create_worker_app(settings=inbox_settings, session_factory=worker_sessions, fetcher=s3)
    response = TestClient(app).post("/events", json=KICK)

    assert response.status_code == 200
    assert response.json() == {"processed": 25, "budget_exhausted": False}
    assert all(reload(worker_sessions, message_id).state == "received" for message_id in ids)


def test_any_event_body_means_drain(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """An EventBridge Scheduler event is as good as a kick; the body is not read."""
    s3 = StubS3()
    backlog(worker_sessions, committed_owner, s3, 1)
    app = create_worker_app(settings=inbox_settings, session_factory=worker_sessions, fetcher=s3)

    response = TestClient(app).post(
        "/events", json={"source": "aws.scheduler", "detail-type": "Scheduled Event"}
    )

    assert response.status_code == 200
    assert response.json()["processed"] == 1


def test_the_budget_stops_between_messages_not_between_batches(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """Each fetch takes a minute of fake time; a four-minute budget allows four.

    Checked only between batches, the pass would have run all ten and gone past
    the Lambda timeout.
    """
    clock = FakeClock()
    clock.fetch_cost = 60

    class Slow(StubS3):
        def fetch(self, key: str) -> bytes:
            clock.now += clock.fetch_cost
            return super().fetch(key)

    s3 = Slow()
    ids = backlog(worker_sessions, committed_owner, s3, BATCH_SIZE)
    assert timedelta(minutes=4) == WORKER_BUDGET

    app = create_worker_app(
        settings=inbox_settings, session_factory=worker_sessions, fetcher=s3, clock=clock
    )
    response = TestClient(app).post("/events", json=KICK)

    assert response.status_code == 200
    assert response.json() == {"processed": 4, "budget_exhausted": True}
    states = [reload(worker_sessions, message_id).state for message_id in ids]
    assert states.count("received") == 4
    assert states.count("pending_ingest") == BATCH_SIZE - 4

    # The rest are picked up by the next event, not lost.
    clock.fetch_cost = 0
    follow_up = TestClient(app).post("/events", json=KICK)
    assert follow_up.json()["processed"] == BATCH_SIZE - 4


def test_an_unconfigured_inbox_answers_with_nothing_processed() -> None:
    """No inbox settings: nothing to drain, no database touched, and no crash."""
    settings = require_settings(
        {"DATABASE_URL": "postgresql://unused@127.0.0.1:1/unused", **TEST_ENVIRONMENT}
    )
    assert settings.inbox is None

    response = TestClient(create_worker_app(settings=settings)).post("/events", json=KICK)

    assert response.status_code == 200
    assert response.json() == {"processed": 0, "budget_exhausted": False}


def test_the_worker_app_serves_health_for_the_adapter_readiness_check() -> None:
    settings = require_settings(
        {"DATABASE_URL": "postgresql://unused@127.0.0.1:1/unused", **TEST_ENVIRONMENT}
    )
    response = TestClient(create_worker_app(settings=settings)).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_a_transient_failure_costs_one_attempt_per_event_not_all_of_them(
    inbox_settings: Settings,
    worker_sessions: sessionmaker[OrmSession],
    committed_owner: Owner,
) -> None:
    """Regression: a failed message is claimable again at once, so a drain that
    counted claims as progress re-ran it back to back — one S3 hiccup burned every
    retry in milliseconds and sent real mail to `ingest_failed`, and a deferred
    message kept the worker (and Neon) busy for the whole budget.
    """
    s3 = StubS3()
    (message_id,) = backlog(worker_sessions, committed_owner, s3, 1)
    s3.fail_with = TimeoutError("S3 read timed out")
    app = create_worker_app(settings=inbox_settings, session_factory=worker_sessions, fetcher=s3)

    response = TestClient(app).post("/events", json=KICK)

    assert response.status_code == 200
    assert response.json() == {"processed": 1, "budget_exhausted": False}
    assert len(s3.fetched) == 1, "one attempt per event; the schedule is the retry"
    assert reload(worker_sessions, message_id).state in ("pending_ingest", "deferred")
