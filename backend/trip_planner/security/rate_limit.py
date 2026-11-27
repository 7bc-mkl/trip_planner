"""Login rate limiting and the fixed response floor.

Both defend the login handler, and both are written so their effect is *not*
observable: a limited attempt answers exactly like an ordinary failure, and the
floor makes every answer take the same wall-clock time whatever work happened
behind it.

The counters live in PostgreSQL rather than in a process-local dictionary because
a public deployment runs more than one worker, and an in-process counter would be
decorative — an attacker would simply be load-balanced onto a fresh one.
"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import sqlalchemy as sa
from fastapi import Request
from sqlalchemy.orm import Session as OrmSession

from trip_planner.db.models import LoginAttempt

#: How long a failed attempt counts against the limit.
DEFAULT_WINDOW = timedelta(minutes=15)

#: Attempts allowed per identity within the window before it engages.
DEFAULT_MAX_ATTEMPTS = 10

#: Every login answer takes at least this long.
#:
#: The point is not to equalise the real work — Argon2 timing varies with load and
#: cannot be equalised reliably — but to put a floor under it so the difference
#: between "hashed a real password" and "hashed the dummy" is below the noise.
RESPONSE_FLOOR_SECONDS = 0.4


class Clock(Protocol):
    """The seam that makes the floor testable without measuring wall-clock time."""

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


_clock: Clock = SystemClock()


def set_clock(clock: Clock) -> None:
    """Inject a clock. Tests use this; nothing in production calls it."""
    global _clock
    _clock = clock


def get_clock() -> Clock:
    return _clock


@contextmanager
def response_floor(seconds: float = RESPONSE_FLOOR_SECONDS) -> Iterator[None]:
    """Ensure the wrapped block takes at least `seconds`, sleeping out the remainder.

    Wrapping rather than sleeping a fixed amount at the end matters: a fixed
    trailing sleep would still let the *total* vary with the work done inside.
    """
    clock = get_clock()
    started = clock.monotonic()
    try:
        yield
    finally:
        remaining = seconds - (clock.monotonic() - started)
        if remaining > 0:
            clock.sleep(remaining)


#: Stand-in for a caller whose address cannot be determined or parsed. Attempts
#: from all such callers share one bucket, which is the safe direction: they are
#: rate limited together rather than not at all.
UNKNOWN_SOURCE_IP = "::"


def _parse_ip(value: str) -> str | None:
    """Return `value` when it is a real IP address, else None.

    `source_ip` is an INET column, so an unparseable value is a database error
    rather than a bad row. Without this, `X-Forwarded-For: garbage` would turn
    every login into a 500 — which both breaks sign-in and hands an attacker a
    trivially distinguishable response.
    """
    candidate = value.strip()
    if not candidate:
        return None

    # A forwarded entry may carry a port ("203.0.113.7:41234") or brackets
    # ("[2001:db8::1]:443"); neither is part of the address.
    if candidate.startswith("["):
        candidate = candidate[1:].split("]", 1)[0]
    elif candidate.count(":") == 1:
        candidate = candidate.split(":", 1)[0]

    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


#: Today's rule: the first X-Forwarded-For element, behind Caddy.
CLIENT_IP_SOURCE_FORWARDED = "x-forwarded-for"

#: The Lambda target: X-Forwarded-For is never read.
CLIENT_IP_SOURCE_CLOUDFRONT = "cloudfront"


def _cloudfront_viewer_ip(request: Request) -> str | None:
    """The viewer address CloudFront vouches for, or None.

    SEAM (spec Phase 1, step 12): this is where the `CloudFront-Viewer-Address`
    header is read — and only on a request that passed the `X-Origin-Verify`
    check, since without that check anyone calling the raw Function URL could
    set it. Until that middleware exists nothing here is trustworthy, so it
    returns None and `client_ip` falls back to the socket peer.
    """
    del request
    return None


def client_ip(request: Request, source: str = CLIENT_IP_SOURCE_FORWARDED) -> str:
    """The caller's address, always a value the INET column accepts.

    `source` is `Settings.client_ip_source` (`CLIENT_IP_SOURCE`):

    - `x-forwarded-for` (default, compose behind Caddy): the socket peer is the
      proxy, so the leftmost X-Forwarded-For entry is used when present. That is
      safe only because Caddy *replaces* the header; the app must never be
      reachable except through it.
    - `cloudfront` (Lambda behind CloudFront and a Function URL): X-Forwarded-For
      is **never** read. There a client-supplied header is preserved with AWS's
      address appended, so its first element is chosen by the viewer — who could
      rotate it on every attempt and never trip the per-address limit. The
      address comes from `_cloudfront_viewer_ip`, else the socket peer; uvicorn
      must then run without `--proxy-headers` (`deploy/entrypoint.sh`), or it
      rewrites `request.client` from that same header.

    A spoofable source is not harmless: rotating fake addresses bypasses the
    per-address limit entirely (the per-e-mail limit still holds), which is why
    the rule is selected per deployment rather than assumed.
    """
    if source == CLIENT_IP_SOURCE_CLOUDFRONT:
        viewer = _cloudfront_viewer_ip(request)
        if viewer is not None:
            return viewer
    else:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            parsed = _parse_ip(forwarded.split(",")[0])
            if parsed is not None:
                return parsed

    if request.client is not None:
        parsed = _parse_ip(request.client.host or "")
        if parsed is not None:
            return parsed

    return UNKNOWN_SOURCE_IP


@dataclass(frozen=True, slots=True)
class RateLimiter:
    window: timedelta = DEFAULT_WINDOW
    max_attempts: int = DEFAULT_MAX_ATTEMPTS

    def _since(self, now: datetime | None) -> datetime:
        return (now or datetime.now(UTC)) - self.window

    def is_limited(
        self, db: OrmSession, *, email: str, source_ip: str, now: datetime | None = None
    ) -> bool:
        """True when either the e-mail or the source address is over the limit.

        Both keys are counted because they defend different attacks: many
        passwords against one account, and many accounts from one address.
        """
        since = self._since(now)

        count = db.execute(
            sa.select(sa.func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.attempted_at >= since,
                sa.or_(
                    LoginAttempt.email_normalised == email,
                    LoginAttempt.source_ip == source_ip,
                ),
            )
        ).scalar_one()

        return int(count) >= self.max_attempts

    def record_attempt(
        self, db: OrmSession, *, email: str, source_ip: str, now: datetime | None = None
    ) -> None:
        """Log the attempt and drop rows that have aged out of every window."""
        db.add(
            LoginAttempt(
                email_normalised=email,
                source_ip=source_ip,
                attempted_at=now or datetime.now(UTC),
            )
        )
        db.execute(sa.delete(LoginAttempt).where(LoginAttempt.attempted_at < self._since(now)))
        db.flush()

    def clear(self, db: OrmSession, *, email: str, source_ip: str) -> None:
        """Forget a caller's attempts after they succeed."""
        db.execute(
            sa.delete(LoginAttempt).where(
                sa.or_(
                    LoginAttempt.email_normalised == email,
                    LoginAttempt.source_ip == source_ip,
                )
            )
        )
        db.flush()


_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Override the limiter. Tests use this to shrink the window."""
    global _rate_limiter
    _rate_limiter = limiter
