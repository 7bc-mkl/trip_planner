"""Login rate limiting and the fixed response floor.

Both are tested through the injected clock rather than by measuring elapsed time.
A wall-clock assertion on a 400 ms floor is a flaky test on a loaded CI box, and
a flaky security test gets deleted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession
from starlette.datastructures import Headers
from starlette.requests import Request

from trip_planner.db.models import LoginAttempt, Owner
from trip_planner.security import rate_limit
from trip_planner.security.rate_limit import (
    RESPONSE_FLOOR_SECONDS,
    UNKNOWN_SOURCE_IP,
    RateLimiter,
    client_ip,
    response_floor,
    set_rate_limiter,
)

LOGIN = "/api/v1/auth/login"


class RecordingClock:
    """A clock that advances only when told, and records what it was asked to sleep."""

    def __init__(self, elapsed: float = 0.0) -> None:
        self._now = 0.0
        self._elapsed = elapsed
        self.slept: list[float] = []

    def monotonic(self) -> float:
        now = self._now
        # The second reading (taken after the block) is `elapsed` later.
        self._now = self._elapsed
        return now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


class TestResponseFloor:
    def test_it_sleeps_out_the_remainder_of_the_floor(self) -> None:
        clock = RecordingClock(elapsed=0.1)
        rate_limit.set_clock(clock)

        with response_floor():
            pass

        assert clock.slept == [pytest.approx(RESPONSE_FLOOR_SECONDS - 0.1)]

    def test_work_that_already_exceeds_the_floor_does_not_sleep(self) -> None:
        """A slow request must not be padded to a multiple of the floor."""
        clock = RecordingClock(elapsed=RESPONSE_FLOOR_SECONDS + 1.0)
        rate_limit.set_clock(clock)

        with response_floor():
            pass

        assert clock.slept == []

    def test_the_floor_applies_even_when_the_block_raises(self) -> None:
        """The failure path is the one an attacker times; it must be floored too."""
        clock = RecordingClock(elapsed=0.05)
        rate_limit.set_clock(clock)

        with pytest.raises(ValueError, match="boom"), response_floor():
            raise ValueError("boom")

        assert clock.slept == [pytest.approx(RESPONSE_FLOOR_SECONDS - 0.05)]

    def test_the_login_handler_applies_the_floor(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        clock = RecordingClock(elapsed=0.0)
        rate_limit.set_clock(clock)

        client.post(LOGIN, json={"email": owner.email, "password": owner_password})

        assert clock.slept, "login answered without waiting for the response floor"


class TestClientIp:
    def _request(self, headers: dict[str, str], client_host: str | None) -> Request:
        scope = {
            "type": "http",
            "method": "POST",
            "path": LOGIN,
            "headers": Headers(headers).raw,
            "client": (client_host, 12345) if client_host else None,
        }
        return Request(scope)

    def test_the_forwarded_header_wins_behind_a_proxy(self) -> None:
        request = self._request({"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, "10.0.0.1")
        assert client_ip(request) == "203.0.113.7"

    def test_a_port_suffix_is_stripped(self) -> None:
        request = self._request({"x-forwarded-for": "203.0.113.7:41234"}, None)
        assert client_ip(request) == "203.0.113.7"

    def test_a_bracketed_ipv6_address_is_parsed(self) -> None:
        request = self._request({"x-forwarded-for": "[2001:db8::1]:443"}, None)
        assert client_ip(request) == "2001:db8::1"

    @pytest.mark.parametrize("garbage", ["not-an-ip", "", "   ", "'; DROP TABLE owner; --"])
    def test_an_unparseable_address_falls_back_instead_of_reaching_the_database(
        self, garbage: str
    ) -> None:
        """`source_ip` is INET: an unparseable value would be a 500, not a bad row.

        Without this, `X-Forwarded-For: garbage` turns every login into a server
        error — which both breaks sign-in and gives an attacker a response that is
        trivially distinguishable from a real failure.
        """
        request = self._request({"x-forwarded-for": garbage}, None)
        assert client_ip(request) == UNKNOWN_SOURCE_IP

    def test_a_non_ip_socket_peer_falls_back(self) -> None:
        request = self._request({}, "testclient")
        assert client_ip(request) == UNKNOWN_SOURCE_IP

    def test_a_garbage_forwarded_header_does_not_break_login(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        response = client.post(
            LOGIN,
            json={"email": owner.email, "password": owner_password},
            headers={"X-Forwarded-For": "definitely-not-an-ip"},
        )
        assert response.status_code == 204


class TestRateLimiter:
    def test_it_engages_after_the_configured_number_of_attempts(
        self, db_session: OrmSession
    ) -> None:
        limiter = RateLimiter(window=timedelta(minutes=15), max_attempts=3)
        key = {"email": "owner@example.com", "source_ip": "203.0.113.7"}

        for _ in range(3):
            assert not limiter.is_limited(db_session, **key)
            limiter.record_attempt(db_session, **key)

        assert limiter.is_limited(db_session, **key)

    def test_attempts_outside_the_window_do_not_count(self, db_session: OrmSession) -> None:
        limiter = RateLimiter(window=timedelta(minutes=15), max_attempts=2)
        key = {"email": "owner@example.com", "source_ip": "203.0.113.7"}
        long_ago = datetime.now(UTC) - timedelta(hours=1)

        for _ in range(5):
            db_session.add(
                LoginAttempt(
                    email_normalised=key["email"], source_ip=key["source_ip"], attempted_at=long_ago
                )
            )
        db_session.flush()

        assert not limiter.is_limited(db_session, **key)

    def test_the_email_is_limited_independently_of_the_address(
        self, db_session: OrmSession
    ) -> None:
        """Many passwords against one account, from a rotating set of addresses."""
        limiter = RateLimiter(window=timedelta(minutes=15), max_attempts=3)

        for index in range(3):
            limiter.record_attempt(
                db_session, email="owner@example.com", source_ip=f"203.0.113.{index}"
            )

        assert limiter.is_limited(db_session, email="owner@example.com", source_ip="198.51.100.9")

    def test_the_address_is_limited_independently_of_the_email(
        self, db_session: OrmSession
    ) -> None:
        """Many accounts from one address."""
        limiter = RateLimiter(window=timedelta(minutes=15), max_attempts=3)

        for index in range(3):
            limiter.record_attempt(
                db_session, email=f"victim{index}@example.com", source_ip="203.0.113.7"
            )

        assert limiter.is_limited(
            db_session, email="someone-else@example.com", source_ip="203.0.113.7"
        )

    def test_a_success_clears_the_callers_attempts(self, db_session: OrmSession) -> None:
        limiter = RateLimiter(window=timedelta(minutes=15), max_attempts=3)
        key = {"email": "owner@example.com", "source_ip": "203.0.113.7"}

        for _ in range(3):
            limiter.record_attempt(db_session, **key)
        assert limiter.is_limited(db_session, **key)

        limiter.clear(db_session, **key)
        assert not limiter.is_limited(db_session, **key)

    def test_recording_prunes_rows_that_aged_out(self, db_session: OrmSession) -> None:
        """Lazy pruning on write — there is no scheduler in this milestone."""
        limiter = RateLimiter(window=timedelta(minutes=15), max_attempts=100)
        db_session.add(
            LoginAttempt(
                email_normalised="old@example.com",
                source_ip="203.0.113.1",
                attempted_at=datetime.now(UTC) - timedelta(days=2),
            )
        )
        db_session.flush()

        limiter.record_attempt(db_session, email="owner@example.com", source_ip="203.0.113.7")

        remaining = db_session.execute(sa.select(LoginAttempt.email_normalised)).scalars().all()
        assert "old@example.com" not in remaining


class TestLimitedResponseIsIndistinguishable:
    @pytest.fixture(autouse=True)
    def tight_limiter(self) -> object:
        previous = rate_limit.get_rate_limiter()
        set_rate_limiter(RateLimiter(window=timedelta(minutes=15), max_attempts=3))
        yield
        set_rate_limiter(previous)

    def test_the_limiter_engages_through_the_endpoint(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        for _ in range(3):
            failure = client.post(LOGIN, json={"email": owner.email, "password": "wrong"})
            assert failure.status_code == 401

        # Even the *correct* password is refused once the limiter engages —
        # otherwise the limit would be a free oracle for "was that the password?".
        limited = client.post(LOGIN, json={"email": owner.email, "password": owner_password})
        assert limited.status_code == 401

    def test_a_limited_response_is_byte_identical_to_an_ordinary_failure(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        ordinary = client.post(LOGIN, json={"email": owner.email, "password": "wrong"})

        for _ in range(5):
            client.post(LOGIN, json={"email": owner.email, "password": "wrong"})

        limited = client.post(LOGIN, json={"email": owner.email, "password": owner_password})

        assert limited.status_code == ordinary.status_code
        assert limited.content == ordinary.content

        ignored = {"date", "server", "content-length"}

        def comparable(response: object) -> dict[str, str]:
            headers = response.headers  # type: ignore[attr-defined]
            return {k.lower(): v for k, v in headers.items() if k.lower() not in ignored}

        assert comparable(limited) == comparable(ordinary)

    def test_no_retry_after_header_advertises_the_limit(
        self, client: TestClient, owner: Owner
    ) -> None:
        """A Retry-After would announce that the limiter exists and when it lifts."""
        for _ in range(6):
            response = client.post(LOGIN, json={"email": owner.email, "password": "wrong"})

        assert "retry-after" not in {k.lower() for k in response.headers}
