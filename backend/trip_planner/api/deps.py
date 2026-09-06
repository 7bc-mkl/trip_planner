"""Shared FastAPI dependencies.

`get_current_session` is applied to the whole API router by default rather than
opted into per route (step 1.6): the failure mode of opt-in authentication is a
new endpoint that silently ships unauthenticated, and R08 says nothing showing a
plan is reachable without a session.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, Request
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import selectinload

from trip_planner.config import Settings, get_settings
from trip_planner.db.models import Owner, Session, Trip, TripDay
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


def get_owned_trip(trip_id: uuid.UUID, db: DbSession, owner: CurrentOwner) -> Trip:
    """Resolve `{trip_id}` to a trip this owner actually owns, or answer 404.

    Every trip-scoped route takes this rather than joining to the trip by hand.
    A handler that writes its own query can forget the `owner_id` clause, and the
    resulting endpoint serves another owner's plan while looking correct in review;
    `tests/test_route_protection.py` enumerates the routes and fails if one skips
    this dependency, so the guarantee survives routes nobody has written yet.

    **A trip belonging to someone else answers 404, not 403.** A 403 would confirm
    the id exists, which is a membership oracle over the whole table.

    Stages, days and the days' items are eager-loaded because every consumer
    needs them: the timeline payload derives each day's stages from the first,
    renders the third, and computes the readiness counter over all of them. Lazily
    loaded, one timeline would cost a query per day.
    """
    trip = db.execute(
        sa.select(Trip)
        .where(Trip.id == trip_id, Trip.owner_id == owner.id)
        .options(
            selectinload(Trip.stages),
            selectinload(Trip.days).selectinload(TripDay.items),
        )
    ).scalar_one_or_none()

    if trip is None:
        raise ApiError(ErrorCode.NOT_FOUND, field="trip_id")

    return trip


OwnedTrip = Annotated[Trip, Depends(get_owned_trip)]
