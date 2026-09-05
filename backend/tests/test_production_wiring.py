"""Behaviour only the real request transaction can show.

Every other endpoint test in this suite runs with `get_db` overridden by a
session that is rolled back once, at the end of the test — so a handler that
raises still sees its own writes. Production does not work that way:
`api/deps.py`'s `get_db` rolls the whole request back whenever the handler
raises, and the two writes below happen on paths that raise by definition.

Under the overridden wiring both looked correct while neither survived a real
request. So these tests build the application on a genuine request-scoped
session, which is the only arrangement in which the difference is observable.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from trip_planner.config import Settings
from trip_planner.db.models import LoginAttempt, Owner, Session
from trip_planner.security import rate_limit
from trip_planner.security.rate_limit import RateLimiter, set_rate_limiter

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"

#: These rows are committed for real, so they use an address of their own rather
#: than the `owner` fixture's, which lives in a transaction that is rolled back.
EMAIL = "durable-owner@example.com"
PASSWORD = "a-correct-horse-battery-staple"


@pytest.fixture
def factory(engine: sa.Engine) -> sessionmaker[sa.orm.Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture
def production_client(
    factory: sessionmaker[sa.orm.Session],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """The application on the real `get_db`, against the test database."""
    from trip_planner.api import deps
    from trip_planner.app import create_app
    from trip_planner.config import get_settings
    from trip_planner.security.passwords import hash_password

    # `deps` imported the name, so it is patched where it is looked up.
    monkeypatch.setattr(deps, "get_sessionmaker", lambda: factory)

    _clean(factory)
    with factory() as setup:
        setup.add(Owner(email=EMAIL, password_hash=hash_password(PASSWORD)))
        setup.commit()

    application = create_app(check_configuration=False)
    application.dependency_overrides[get_settings] = lambda: settings

    with TestClient(application, base_url="http://testserver") as client:
        yield client

    _clean(factory)


def _clean(factory: sessionmaker[sa.orm.Session]) -> None:
    """Remove the committed rows: no fixture transaction sweeps them away."""
    owned = sa.select(Owner.id).where(Owner.email == EMAIL)
    with factory() as cleanup:
        cleanup.execute(sa.delete(LoginAttempt).where(LoginAttempt.email_normalised == EMAIL))
        cleanup.execute(sa.delete(Session).where(Session.owner_id.in_(owned)))
        cleanup.execute(sa.delete(Owner).where(Owner.email == EMAIL))
        cleanup.commit()


def _attempts(factory: sessionmaker[sa.orm.Session]) -> int:
    with factory() as counting:
        return int(
            counting.execute(
                sa.select(sa.func.count())
                .select_from(LoginAttempt)
                .where(LoginAttempt.email_normalised == EMAIL)
            ).scalar_one()
        )


class TestTheRateLimiterSurvivesTheRequestTransaction:
    @pytest.fixture(autouse=True)
    def tight_limiter(self) -> Iterator[None]:
        previous = rate_limit.get_rate_limiter()
        set_rate_limiter(RateLimiter(window=timedelta(minutes=15), max_attempts=3))
        yield
        set_rate_limiter(previous)

    def test_a_failed_attempt_is_recorded_even_though_the_request_failed(
        self, production_client: TestClient, factory: sessionmaker[sa.orm.Session]
    ) -> None:
        response = production_client.post(LOGIN, json={"email": EMAIL, "password": "wrong"})

        assert response.status_code == 401
        assert _attempts(factory) == 1, (
            "the failed attempt was rolled back together with the 401, so the limiter counts "
            "nothing and brute-force protection does not exist outside this suite"
        )

    def test_the_limiter_engages_under_the_production_wiring(
        self, production_client: TestClient
    ) -> None:
        """Once the limit is reached even the correct password is refused."""
        for _ in range(3):
            failure = production_client.post(LOGIN, json={"email": EMAIL, "password": "wrong"})
            assert failure.status_code == 401

        limited = production_client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})

        assert limited.status_code == 401, (
            "the correct password was accepted after the limit was reached — the limiter never "
            "saw the failures"
        )

    def test_a_success_still_clears_the_counter(
        self, production_client: TestClient, factory: sessionmaker[sa.orm.Session]
    ) -> None:
        """A durable record must not turn one typo into a creeping lockout."""
        production_client.post(LOGIN, json={"email": EMAIL, "password": "wrong"})
        success = production_client.post(LOGIN, json={"email": EMAIL, "password": PASSWORD})

        assert success.status_code == 204
        assert _attempts(factory) == 0, (
            "a successful sign-in must forget the caller's failed attempts"
        )


class TestExpiredSessionsAreActuallyDeleted:
    def test_reading_an_expired_session_removes_its_row(
        self,
        production_client: TestClient,
        factory: sessionmaker[sa.orm.Session],
        settings: Settings,
    ) -> None:
        """There is no scheduler: the read that finds a dead session drops it.

        The drop happens on a request that answers 401, so it only survives if it
        is committed rather than flushed — otherwise every expired session stays
        in the table forever and the cleanup story is fiction.
        """
        from trip_planner.security.sessions import create_session

        with factory() as setup:
            owner = setup.execute(
                sa.select(Owner).where(Owner.email == EMAIL)
            ).scalar_one()
            issued = create_session(
                setup,
                owner,
                secret=settings.session_secret,
                now=datetime.now(UTC) - timedelta(days=365),
            )
            token = issued.token
            setup.commit()

        production_client.cookies.set("session", token)
        response = production_client.get(ME)

        assert response.status_code == 401
        with factory() as counting:
            remaining = counting.execute(
                sa.select(sa.func.count())
                .select_from(Session)
                .where(Session.owner_id.in_(sa.select(Owner.id).where(Owner.email == EMAIL)))
            ).scalar_one()

        assert remaining == 0, "the expired session row was rolled back into existence again"
