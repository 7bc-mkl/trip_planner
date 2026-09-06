"""CSRF double-submit verification.

The check is on the *method*, not on the route: every unsafe method requires the
header to match the cookie, so a new endpoint is protected the day it is written
rather than the day someone remembers to decorate it.
"""

from __future__ import annotations

from fastapi import Request

from trip_planner.errors import ApiError, ErrorCode
from trip_planner.security.sessions import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from trip_planner.security.tokens import tokens_equal

#: Methods that do not change state and therefore need no token.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def requires_csrf(method: str) -> bool:
    return method.upper() not in SAFE_METHODS


def verify_csrf(request: Request) -> None:
    """Raise `csrf_token_invalid` unless the header matches the cookie."""
    if not requires_csrf(request.method):
        return

    cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    header = request.headers.get(CSRF_HEADER_NAME, "")

    # An absent pair is a failure, not a pass: treating "no token at all" as
    # acceptable would make the whole check opt-in from the attacker's side.
    if not cookie or not header or not tokens_equal(cookie, header):
        raise ApiError(ErrorCode.CSRF_TOKEN_INVALID)
