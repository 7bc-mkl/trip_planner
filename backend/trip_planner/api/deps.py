"""Shared FastAPI dependencies.

`get_current_session` is applied to the whole API router by default rather than
opted into per route (step 1.6): the failure mode of opt-in authentication is a
new endpoint that silently ships unauthenticated, and R08 says nothing showing a
plan is reachable without a session.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session as OrmSession

from trip_planner.config import Settings, get_settings
from trip_planner.db.models import Owner, Session
from trip_planner.db.session import get_sessionmaker
from trip_planner.errors import ApiError, ErrorCode
from trip_planner.security.csrf import verify_csrf
from trip_planner.security.sessions import SESSION_COOKIE_NAME, resolve_session


def get_db() -> Iterator[OrmSession]:
    """A session per request, committed on success and rolled back on failure."""
    with get_sessionmaker()() as db:
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


DbSession = Annotated[OrmSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def get_current_session(
    request: Request, db: DbSession, settings: AppSettings
) -> Session:
    """Resolve the caller's session, or refuse the request.

    Also runs the CSRF check, so an unsafe method reaching any authenticated
    route is verified without the route having to remember.
    """
    verify_csrf(request)

    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    session = resolve_session(db, token, secret=settings.session_secret)
    if session is None:
        raise ApiError(ErrorCode.NOT_AUTHENTICATED)

    return session


CurrentSession = Annotated[Session, Depends(get_current_session)]


def get_current_owner(session: CurrentSession, db: DbSession) -> Owner:
    owner = db.get(Owner, session.owner_id)
    if owner is None:  # pragma: no cover - the FK cascade makes this unreachable
        raise ApiError(ErrorCode.NOT_AUTHENTICATED)
    return owner


CurrentOwner = Annotated[Owner, Depends(get_current_owner)]
