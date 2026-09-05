"""Cookie policy, in one place.

`SameSite=Lax` is the first line against CSRF and the double-submit token is the
second (D14). Both are applied here so no handler can set a session cookie with a
weaker policy by forgetting a keyword argument.
"""

from __future__ import annotations

from fastapi import Response

from trip_planner.config import Settings
from trip_planner.security.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_LIFETIME,
)


def set_session_cookies(
    response: Response, *, session_token: str, csrf_token: str, settings: Settings
) -> None:
    max_age = int(SESSION_LIFETIME.total_seconds())

    # HttpOnly: JavaScript must never be able to read the session token, so an
    # XSS bug cannot become a stolen session.
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookies_are_secure,
        samesite="lax",
        path="/",
    )

    # Deliberately readable by JavaScript: the SPA copies this into the
    # X-CSRF-Token header, and the server checks the two match. A same-site
    # attacker cannot read it cross-origin, which is what makes double-submit work.
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookies_are_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookies(response: Response, *, settings: Settings) -> None:
    for name in (SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(
            name,
            path="/",
            httponly=name == SESSION_COOKIE_NAME,
            secure=settings.cookies_are_secure,
            samesite="lax",
        )
