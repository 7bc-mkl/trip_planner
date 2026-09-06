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

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from trip_planner.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
