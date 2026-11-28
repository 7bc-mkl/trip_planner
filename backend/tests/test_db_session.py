"""Engine construction is driven by settings; none of this connects."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool, QueuePool

from tests.test_config import COMPLETE_ENV
from trip_planner.config import require_settings
from trip_planner.db.session import engine_options

URL = "postgresql+psycopg://u:p@localhost:5432/db"


def _engine(extra: dict[str, str]):
    settings = require_settings(COMPLETE_ENV | {"DATABASE_URL": URL} | extra)
    options = engine_options(settings)
    return options, create_engine(settings.sqlalchemy_url, **options)


def _assert_keepalives(options: dict) -> None:
    args = options["connect_args"]
    assert args["keepalives"] == 1
    assert args["keepalives_idle"] == 30
    assert args["keepalives_interval"] == 10
    assert args["keepalives_count"] == 3


def test_default_uses_a_queue_pool_and_keeps_prepared_statements_default() -> None:
    options, engine = _engine({})

    assert isinstance(engine.pool, QueuePool)
    assert "prepare_threshold" not in options["connect_args"]
    _assert_keepalives(options)


def test_null_pool_mode_uses_null_pool_and_disables_prepared_statements() -> None:
    options, engine = _engine({"DB_POOL": "null"})

    assert isinstance(engine.pool, NullPool)
    assert options["connect_args"]["prepare_threshold"] is None
    _assert_keepalives(options)
