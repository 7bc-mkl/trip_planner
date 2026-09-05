"""Authentication endpoints.

The login handler's shape is dictated by two requirements that pull the same way:
a wrong password and an unknown e-mail must be indistinguishable (no user
enumeration), and repeated attempts must be rate limited without that limiting
being observable either. So every path through `login` does the same work, in the
same order, and answers with the same bytes.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from trip_planner.api.deps import AppSettings, CurrentOwner, CurrentSession, DbSession
from trip_planner.db.models import Owner, normalise_email
from trip_planner.errors import ApiError, ErrorCode
from trip_planner.security.cookies import clear_session_cookies, set_session_cookies
from trip_planner.security.csrf import verify_csrf
from trip_planner.security.passwords import DUMMY_HASH, verify_password
from trip_planner.security.rate_limit import (
    RateLimiter,
    client_ip,
    get_rate_limiter,
    response_floor,
)
from trip_planner.security.sessions import SESSION_COOKIE_NAME, create_session, revoke_session
from trip_planner.security.tokens import generate_csrf_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class LocaleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locale: str = Field(pattern="^(pl|en)$")


class OwnerRead(BaseModel):
    """The owner as the API exposes them. `password_hash` is structurally absent."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    locale: str


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    """Sign in. Answers 204 with the session and CSRF cookies, or 401.

    A wrong password and an unknown e-mail produce byte-identical responses, and
    so does a rate-limited attempt: identical status, identical body, identical
    headers. Anything else is a user-enumeration oracle.
    """
    limiter: RateLimiter = get_rate_limiter()
    email = normalise_email(payload.email)
    source_ip = client_ip(request)

    with response_floor():
        limited = limiter.is_limited(db, email=email, source_ip=source_ip)
        limiter.record_attempt(db, email=email, source_ip=source_ip)

        owner = db.execute(sa.select(Owner).where(Owner.email == email)).scalar_one_or_none()

        # Verify unconditionally, against a real hash when the owner is unknown,
        # so an unknown e-mail costs the same Argon2 work as a known one.
        password_matches = verify_password(
            owner.password_hash if owner is not None else DUMMY_HASH,
            payload.password,
        )

        if limited or owner is None or not password_matches:
            raise ApiError(ErrorCode.INVALID_CREDENTIALS)

        limiter.clear(db, email=email, source_ip=source_ip)

        issued = create_session(db, owner, secret=settings.session_secret)
        csrf_token = generate_csrf_token()

    response.status_code = status.HTTP_204_NO_CONTENT
    set_session_cookies(
        response,
        session_token=issued.token,
        csrf_token=csrf_token,
        settings=settings,
    )
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    """Sign out. Idempotent, and it genuinely revokes: the row is deleted.

    CSRF is verified only when a session cookie is actually present. Logout is a
    state-changing request, so a cross-site page must not be able to drop the
    owner's session; but a logout with no session to end is a no-op, and demanding
    a token there would turn "sign me out" into an error for someone already
    signed out.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if token:
        verify_csrf(request)

    revoke_session(db, token, secret=settings.session_secret)

    response.status_code = status.HTTP_204_NO_CONTENT
    clear_session_cookies(response, settings=settings)
    return response


@router.get("/me")
def read_me(owner: CurrentOwner) -> OwnerRead:
    return OwnerRead.model_validate(owner)


@router.patch("/me")
def update_me(
    payload: LocaleUpdate,
    owner: CurrentOwner,
    session: CurrentSession,  # noqa: ARG001  (forces the CSRF + session check)
    db: DbSession,
) -> OwnerRead:
    """Update the owner's locale — the only mutable field.

    It is a server-side field rather than localStorage so the language survives a
    new browser (R01): a locale that resets every time is the kind of paper cut
    that makes an owner stop using his own tool.
    """
    owner.locale = payload.locale
    db.flush()
    return OwnerRead.model_validate(owner)
