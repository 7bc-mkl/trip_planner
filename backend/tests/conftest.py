"""Test fixtures.

The suite runs against a real PostgreSQL server, not SQLite: the schema this
project builds uses a functional unique index, a DEFERRABLE unique constraint and
an INET column, none of which SQLite can express. A green suite on SQLite would
therefore be evidence about a database we do not deploy.

Point `TEST_DATABASE_URL` at any reachable server. The default matches the
throwaway container in `deploy/compose.dev.yml`:

    docker compose -f deploy/compose.dev.yml up -d db
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from trip_planner.config import Settings
    from trip_planner.db.models import Owner

BACKEND_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://trip_planner:trip_planner@127.0.0.1:55432/trip_planner_test"
)

#: Test-only value. Production reads SESSION_SECRET from the environment and the
#: app refuses to start without it.
TEST_SESSION_SECRET = "test-session-secret-not-used-outside-the-suite"

#: The non-database settings the app requires. Set once, here, so a new required
#: variable is added in one place rather than in every test that builds an app.
TEST_ENVIRONMENT = {
    "SESSION_SECRET": TEST_SESSION_SECRET,
    "APP_BASE_URL": "http://testserver",
    "ENVIRONMENT": "development",
}


def _admin_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    # env.py reads DATABASE_URL through trip_planner.config, so the throwaway
    # database is selected the same way production selects the real one.
    os.environ["DATABASE_URL"] = database_url
    for key, value in TEST_ENVIRONMENT.items():
        os.environ.setdefault(key, value)
    return config


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Create a throwaway database for the session, migrate it, and drop it after."""
    admin = sa.engine.make_url(_admin_url())
    name = f"trip_planner_test_{uuid.uuid4().hex[:12]}"

    maintenance = sa.create_engine(admin.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with maintenance.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{name}"'))
    except sa.exc.OperationalError as error:  # pragma: no cover - environment problem
        maintenance.dispose()
        message = (
            f"No PostgreSQL server at {admin.set(password=None).render_as_string()}: {error}. "
            "Start one with: docker compose -f deploy/compose.dev.yml up -d db"
        )
        # Locally an unreachable database is a setup problem and skipping keeps the
        # rest of the suite useful. In CI it is a false green — the database layer
        # would go unverified while the gate reports success — so it fails instead.
        if os.environ.get("CI", "").lower() in {"1", "true"}:
            pytest.fail(message, pytrace=False)
        pytest.skip(message)

    url = admin.set(database=name).render_as_string(hide_password=False)

    previous = os.environ.get("DATABASE_URL")
    command.upgrade(_alembic_config(url), "head")

    try:
        yield url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

        with maintenance.connect() as connection:
            connection.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{name}"'))
        maintenance.dispose()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[sa.Engine]:
    engine = sa.create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: sa.Engine) -> Iterator[Session]:
    """A session rolled back after each test, so tests never see each other's rows."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False, future=True)()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def alembic_config(database_url: str) -> Config:
    return _alembic_config(database_url)


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Settings built from the test environment, bypassing the process-wide cache."""
    from trip_planner.config import require_settings

    return require_settings({"DATABASE_URL": database_url, **TEST_ENVIRONMENT})


@pytest.fixture
def app(db_session: Session, settings: Settings) -> Iterator[FastAPI]:
    """The real application, wired to the test transaction.

    `get_db` is overridden to hand out the rolled-back session so an endpoint test
    leaves no rows behind; everything else — routing, dependencies, exception
    handlers, cookie policy — is the production wiring.
    """
    from trip_planner.api.deps import get_db
    from trip_planner.app import create_app
    from trip_planner.config import get_settings

    def request_scoped_db() -> Iterator[Session]:
        """Hand out the rolled-back session, but expired first.

        In production `get_db` opens a **new** session per request, so an eager
        `selectinload` always reflects what the previous request wrote. Here one
        session is shared so the whole test can roll back as a unit — which means
        its identity map, and every relationship collection already loaded into
        it, would otherwise survive into the next request and serve stale data
        that production never would.

        Expiring on entry makes the shared session behave like the fresh one it
        stands in for. Without it, a test asserting that an item it just created
        shows up in the next response fails against code that is correct.
        """
        db_session.expire_all()
        yield db_session

    application = create_app(check_configuration=False)
    application.dependency_overrides[get_db] = request_scoped_db
    application.dependency_overrides[get_settings] = lambda: settings

    yield application

    application.dependency_overrides.clear()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    from fastapi.testclient import TestClient

    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client


@pytest.fixture
def owner_password() -> str:
    return "a-correct-horse-battery-staple"


@pytest.fixture
def owner(db_session: Session, owner_password: str) -> Owner:
    from trip_planner.db.models import Owner
    from trip_planner.security.passwords import hash_password

    record = Owner(email="owner@example.com", password_hash=hash_password(owner_password))
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture
def signed_in_client(client: TestClient, owner: Owner, owner_password: str) -> TestClient:
    """A client holding a real session and sending the CSRF header on every request.

    Every trip endpoint is authenticated and every unsafe method is CSRF-checked,
    so without this fixture each test would open with the same four lines of
    ceremony — and a test that got them wrong would fail for a reason unrelated to
    what it is checking.

    The header is set on the client rather than passed per call because the SPA's
    fetch client does exactly the same thing: a test that had to remember it would
    be testing a client nobody ships.
    """
    from trip_planner.security.sessions import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

    response = client.post(
        "/api/v1/auth/login", json={"email": owner.email, "password": owner_password}
    )
    assert response.status_code == 204, response.text

    client.headers[CSRF_HEADER_NAME] = client.cookies.get(CSRF_COOKIE_NAME, "")
    return client


@pytest.fixture
def other_owner(db_session: Session) -> Owner:
    """A second owner, for the tests that prove one owner cannot see another's trips.

    D15 says there is one owner today, but the ownership check is the reason
    `get_owned_trip` exists, and a check nothing exercises is a check nobody knows
    is broken.
    """
    from trip_planner.db.models import Owner
    from trip_planner.security.passwords import hash_password

    record = Owner(email="someone-else@example.com", password_hash=hash_password("irrelevant"))
    db_session.add(record)
    db_session.flush()
    return record


@pytest.fixture(autouse=True)
def instant_clock() -> Iterator[None]:
    """Remove the response floor's real sleeping from the suite.

    The floor is asserted directly in tests/test_rate_limit.py through this same
    seam; making every other login test wait 400 ms would only buy slowness.
    """
    from trip_planner.security import rate_limit

    class NoSleepClock:
        def __init__(self) -> None:
            self.slept: list[float] = []

        def monotonic(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            self.slept.append(seconds)

    previous = rate_limit.get_clock()
    rate_limit.set_clock(NoSleepClock())
    yield
    rate_limit.set_clock(previous)
