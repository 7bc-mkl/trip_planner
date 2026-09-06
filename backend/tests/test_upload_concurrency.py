"""An upload that waits for a lock must not take the whole server with it.

This is the only test in the suite that runs the ASGI application on a **real
event loop with more than one request in flight**, and it exists because nothing
else could have caught the defect it pins: the upload handlers are `async def` —
they have to be, to drive `request.stream()` themselves — and they used to do
their synchronous psycopg work directly on that loop. `store_attachment` takes
`pg_advisory_xact_lock` on the trip, so a second upload to the same trip blocked
the loop waiting for a lock whose holder needed that same loop in order to reach
its commit and release it. The process hung permanently and `/api/v1/health`
timed out for every client.

The first class reproduces that deterministically, and the shape of it is the
point. Racing two uploads and hoping they interleave is **not** a reliable
reproduction — under `ASGITransport` the first upload runs to its commit before
the second is ever scheduled, so it passes either way; that race is kept below as
a companion assertion, honestly labelled. Instead the trip's advisory lock is
held by a *third*, plainly separate connection, which puts an upload into the
blocked state on demand. Then the question the defect is actually about can be
asked directly: while that upload waits, does the application still answer
anything at all?

Three things about the harness are deliberate:

- **The real `get_db`, not the shared session.** `conftest`'s `app` fixture hands
  every request one never-committed session on one connection, which is exactly
  what concurrent transactions cannot share. Here
  `trip_planner.api.deps.get_sessionmaker` is pointed at the test engine instead,
  so production's `get_db` runs verbatim — a session per request, committed after
  the handler returns, which is the moment the advisory lock is released. Rows
  are therefore really committed, and the owner is deleted afterwards; every
  table involved cascades from it.
- **A thread with a `join(timeout=...)`, not `asyncio.wait_for`.** The regression
  is a *frozen loop*: a timeout scheduled on that loop would never fire, so an
  in-loop deadline would hang the suite instead of failing it. The loop runs in
  its own daemon thread and the assertion lives in the main one, where the freeze
  cannot reach it, so a regression fails in bounded time.
- **The lock is held longer than that deadline.** A frozen loop must not be able
  to quietly recover after the lock times out and pass late.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Iterator
from datetime import date
from typing import TYPE_CHECKING, Any

import httpx2 as httpx
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from tests.test_attachments_api import MULTIPART_CONTENT_TYPE, multipart_body
from tests.test_domain_uploads import make_pdf
from tests.test_models_trip import make_trip
from trip_planner.db.models import Owner, TripDay
from trip_planner.security.passwords import hash_password
from trip_planner.security.sessions import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

if TYPE_CHECKING:
    from fastapi import FastAPI

    from trip_planner.config import Settings

PASSWORD = "a-correct-horse-battery-staple"
DAY = date(2026, 10, 10)

#: How long the main thread waits for the loop thread. Generous: the fixed code
#: answers in well under a second, and a genuine deadlock never ends.
DEADLINE_SECONDS = 30

#: Longer than the deadline, on purpose — see the module docstring.
LOCK_HOLD_SECONDS = 90


@pytest.fixture
def committed_trip(engine: sa.Engine) -> Iterator[tuple[str, uuid.UUID, uuid.UUID]]:
    """An owner, a trip and a day **committed**, so other connections can see them.

    The shared `db_session` fixture never commits, and its rows are invisible to
    the per-request sessions these requests really open.
    """
    email = f"concurrent-upload-{uuid.uuid4().hex[:8]}@example.com"
    with Session(engine) as setup:
        owner = Owner(email=email, password_hash=hash_password(PASSWORD))
        setup.add(owner)
        setup.flush()
        trip = make_trip(owner)
        setup.add(trip)
        setup.flush()
        setup.add(TripDay(trip_id=trip.id, date=DAY))
        setup.commit()
        owner_id, trip_id = owner.id, trip.id

    try:
        yield email, trip_id, owner_id
    finally:
        with Session(engine) as teardown:
            # Bounded so that a failing run — which leaves a wedged request
            # holding row locks — reports the failure instead of hanging here.
            teardown.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
            teardown.execute(sa.delete(Owner).where(Owner.id == owner_id))
            teardown.commit()


@pytest.fixture
def live_app(
    engine: sa.Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FastAPI]:
    """The application with its real, committing `get_db`, bound to the test engine."""
    from trip_planner.api import deps
    from trip_planner.app import create_app
    from trip_planner.config import get_settings

    monkeypatch.setattr(
        deps,
        "get_sessionmaker",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    application = create_app(check_configuration=False)
    application.dependency_overrides[get_settings] = lambda: settings

    yield application

    application.dependency_overrides.clear()


def voucher(marker: bytes) -> bytes:
    """A valid PDF whose bytes differ per upload, so neither can stand in for the other."""
    return make_pdf().replace(b"trailer", b"%" + marker + b"\ntrailer")


def attachments_url(trip_id: uuid.UUID) -> str:
    return f"/api/v1/trips/{trip_id}/days/{DAY.isoformat()}/attachments"


async def signed_in(client: httpx.AsyncClient, email: str) -> None:
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 204, login.text
    client.headers[CSRF_HEADER_NAME] = client.cookies.get(CSRF_COOKIE_NAME, "")


async def upload(client: httpx.AsyncClient, url: str, marker: bytes) -> httpx.Response:
    body = multipart_body([("file", voucher(marker), f"{marker.decode()}.pdf")])
    return await client.post(url, content=body, headers={"content-type": MULTIPART_CONTENT_TYPE})


def run_on_its_own_loop(scenario: Any, outcome: dict[str, Any]) -> threading.Thread:
    """Drive `scenario` on a fresh loop in a daemon thread, recording what happened."""

    def run() -> None:
        try:
            outcome["result"] = asyncio.run(scenario())
        except BaseException as error:  # noqa: BLE001 - re-raised from the main thread
            outcome["error"] = error

    # Daemon: a genuinely frozen loop can never be joined, and the suite must
    # still be able to exit after reporting the failure.
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def finish(thread: threading.Thread, outcome: dict[str, Any], what: str) -> Any:
    thread.join(timeout=DEADLINE_SECONDS)
    assert not thread.is_alive(), (
        f"{what} did not finish within {DEADLINE_SECONDS}s — blocking database work is "
        "back on the event loop, and a request waiting on pg_advisory_xact_lock is "
        "freezing every other request in the process"
    )
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


class TestAnUploadBlockedOnTheTripLock:
    """The regression test for the deadlock, made deterministic by a third connection."""

    @pytest.fixture
    def trip_lock_held(self, engine: sa.Engine, committed_trip: tuple) -> Iterator[threading.Event]:
        """Hold the trip's advisory lock on a connection of its own, until released.

        The same key `check_byte_quotas` takes: `hashtext` of the trip's id as
        text. Holding it puts the next upload of this trip into exactly the state
        the second of two concurrent uploads is in.
        """
        _, trip_id, _ = committed_trip
        holding = threading.Event()
        release = threading.Event()

        def hold() -> None:
            with Session(engine) as session:
                session.execute(
                    sa.select(sa.func.pg_advisory_xact_lock(sa.func.hashtext(str(trip_id))))
                ).scalar_one()
                holding.set()
                release.wait(timeout=LOCK_HOLD_SECONDS)
                session.rollback()

        holder = threading.Thread(target=hold, daemon=True)
        holder.start()
        assert holding.wait(timeout=10), "the lock holder never acquired the lock"

        try:
            yield release
        finally:
            release.set()
            holder.join(timeout=10)

    def test_the_rest_of_the_application_still_answers(
        self,
        live_app: FastAPI,
        committed_trip: tuple[str, uuid.UUID, uuid.UUID],
        trip_lock_held: threading.Event,
    ) -> None:
        """`/health` answers while an upload waits, and the upload then completes."""
        email, trip_id, _ = committed_trip

        async def scenario() -> dict[str, Any]:
            transport = httpx.ASGITransport(app=live_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                await signed_in(client, email)

                blocked = asyncio.create_task(upload(client, attachments_url(trip_id), b"blocked"))
                # Long enough for it to reach the lock. If the database work is on
                # the loop, this sleep is where the process stops for good.
                await asyncio.sleep(0.5)
                assert not blocked.done(), "the held lock did not block the upload"

                health = await client.get("/api/v1/health")

                trip_lock_held.set()
                stored = await blocked
                return {"health": health.status_code, "upload": stored.status_code}

        outcome: dict[str, Any] = {}
        result = finish(
            run_on_its_own_loop(scenario, outcome),
            outcome,
            "a request served while an upload waited on the trip lock",
        )

        assert result["health"] == 200, "the event loop was not free to answer anything else"
        assert result["upload"] == 201, "the upload did not complete once the lock was released"


class TestTwoUploadsToOneTrip:
    """Two uploads gathered on one loop both succeed.

    A companion, not the regression test: under `ASGITransport` the first upload
    reliably runs through to its commit before the second is scheduled, so this
    passes with the blocking calls on the loop too. It is here because it is the
    user-visible shape of the bug — a multi-file drop — and because it proves the
    threadpool hop keeps both uploads' quotas, sessions and transactions correct.
    """

    def test_both_are_stored(
        self, live_app: FastAPI, committed_trip: tuple[str, uuid.UUID, uuid.UUID]
    ) -> None:
        email, trip_id, _ = committed_trip

        async def scenario() -> list[int]:
            transport = httpx.ASGITransport(app=live_app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                await signed_in(client, email)
                url = attachments_url(trip_id)
                responses = await asyncio.gather(
                    upload(client, url, b"first"), upload(client, url, b"second")
                )
                return [response.status_code for response in responses]

        outcome: dict[str, Any] = {}
        statuses = finish(
            run_on_its_own_loop(scenario, outcome), outcome, "two concurrent uploads"
        )

        assert statuses == [201, 201]
