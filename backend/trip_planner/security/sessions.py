"""Server-side session lifecycle.

Sessions are rows, not tokens-with-claims, so logout genuinely revokes (spec A8).
The cookie carries an opaque token; the row stores only its keyed digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import Owner, Session
from trip_planner.security.tokens import generate_token, hash_token

#: Absolute lifetime. A session older than this is dead however recently it was used.
SESSION_LIFETIME = timedelta(days=30)

#: How stale `last_seen_at` may get before a read refreshes it. A sliding window
#: that does not write on every single request.
LAST_SEEN_REFRESH_INTERVAL = timedelta(days=1)

SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A freshly created session and the token to hand the browser.

    The plaintext token exists only here and in the `Set-Cookie` header; it is
    never stored and never logged.
    """

    session: Session
    token: str


def create_session(
    db: OrmSession, owner: Owner, *, secret: str, now: datetime | None = None
) -> IssuedSession:
    moment = now or datetime.now(UTC)
    token = generate_token()

    session = Session(
        owner_id=owner.id,
        token_hash=hash_token(token, secret=secret),
        created_at=moment,
        expires_at=moment + SESSION_LIFETIME,
        last_seen_at=moment,
    )
    db.add(session)
    db.flush()

    return IssuedSession(session=session, token=token)


def resolve_session(
    db: OrmSession, token: str, *, secret: str, now: datetime | None = None
) -> Session | None:
    """Look a session up by its token, or return None when it is absent or expired.

    Expired rows are deleted here rather than by a scheduler: there is exactly one
    user, and a row nobody can use is cheaper to drop on the read that found it
    than to run a job for.
    """
    if not token:
        return None

    moment = now or datetime.now(UTC)
    digest = hash_token(token, secret=secret)

    session = db.execute(
        sa.select(Session).where(Session.token_hash == digest)
    ).scalar_one_or_none()
    if session is None:
        return None

    if session.expires_at <= moment:
        db.delete(session)
        db.flush()
        return None

    if moment - session.last_seen_at >= LAST_SEEN_REFRESH_INTERVAL:
        session.last_seen_at = moment
        db.flush()

    return session


def revoke_session(db: OrmSession, token: str, *, secret: str) -> bool:
    """Delete the session a token names. Idempotent: an unknown token is not an error."""
    if not token:
        return False

    digest = hash_token(token, secret=secret)
    result = db.execute(sa.delete(Session).where(Session.token_hash == digest))
    db.flush()
    return bool(result.rowcount)


def purge_expired_sessions(db: OrmSession, *, now: datetime | None = None) -> int:
    moment = now or datetime.now(UTC)
    result = db.execute(sa.delete(Session).where(Session.expires_at <= moment))
    db.flush()
    return int(result.rowcount or 0)
