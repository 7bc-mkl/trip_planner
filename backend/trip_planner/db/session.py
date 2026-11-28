"""Engine and session management.

One engine per process, created lazily so importing the app does not require a
reachable database (tests import the app to enumerate its routes).

The request-scoped session lives in `trip_planner.api.deps.get_db`, which owns
the commit-on-success / rollback-on-failure contract. There is deliberately only
one of those: a second, non-committing `get_db` here was easy to import by
mistake and would have silently discarded every write.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from trip_planner.config import Settings, get_settings

# Client-side TCP keepalives: the app notices a server that vanished mid-query
# (a Neon compute suspended or restarted) within about a minute — 30 s idle plus
# 3 probes x 10 s — instead of hanging until the OS gives up. They do NOT free a
# killed worker's advisory lock: on Neon the client's TCP connection ends at
# Neon's proxy. The lock is freed by `idle_in_transaction_session_timeout`
# (scheduler.py, `_take_lock`). Harmless on compose.
_KEEPALIVES: dict[str, int] = {
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}


def engine_options(settings: Settings) -> dict[str, Any]:
    """Keyword arguments for `create_engine`, derived from settings. Never connects."""
    connect_args: dict[str, Any] = dict(_KEEPALIVES)
    options: dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if settings.db_pool == "null":
        # One connection per request to the pooler endpoint, closed afterwards.
        # pool_pre_ping stays: it is harmless with NullPool (a fresh connection).
        options["poolclass"] = NullPool
        # Phase 0 found Neon's PgBouncer supports protocol-level prepared
        # statements; disabling psycopg 3's automatic server-side preparation is
        # belt-and-braces through a transaction-mode pooler.
        connect_args["prepare_threshold"] = None
    options["connect_args"] = connect_args
    return options


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.sqlalchemy_url, **engine_options(settings))


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
