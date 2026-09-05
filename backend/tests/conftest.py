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

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://trip_planner:trip_planner@127.0.0.1:55432/trip_planner_test"
)

#: Test-only value. Production reads SESSION_SECRET from the environment and the
#: app refuses to start without it.
TEST_SESSION_SECRET = "test-session-secret-not-used-outside-the-suite"


def _admin_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    # env.py reads DATABASE_URL through trip_planner.config, so the throwaway
    # database is selected the same way production selects the real one.
    os.environ["DATABASE_URL"] = database_url
    os.environ.setdefault("SESSION_SECRET", TEST_SESSION_SECRET)
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
