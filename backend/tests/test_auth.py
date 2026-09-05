"""The authentication endpoints.

The assertions here are mostly about what the API refuses to reveal. R08 and D14
put this on the public internet, and the properties that matter — no user
enumeration, real revocation, CSRF on every unsafe method — are all properties of
responses that look *the same* as each other.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from trip_planner.config import Settings
from trip_planner.db.models import Owner, Session
from trip_planner.security.sessions import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
)

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


def sign_in(client: TestClient, email: str, password: str) -> None:
    response = client.post(LOGIN, json={"email": email, "password": password})
    assert response.status_code == 204, response.text


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER_NAME: client.cookies.get(CSRF_COOKIE_NAME, "")}


class TestLogin:
    def test_a_correct_password_signs_in_and_sets_both_cookies(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        response = client.post(LOGIN, json={"email": owner.email, "password": owner_password})

        assert response.status_code == 204
        assert client.cookies.get(SESSION_COOKIE_NAME)
        assert client.cookies.get(CSRF_COOKIE_NAME)

    def test_the_session_cookie_is_httponly_and_lax(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        response = client.post(LOGIN, json={"email": owner.email, "password": owner_password})

        cookies = [h for h in response.headers.get_list("set-cookie") if h.startswith("session=")]
        assert len(cookies) == 1
        header = cookies[0].lower()
        assert "httponly" in header, "an XSS bug must not be able to read the session token"
        assert "samesite=lax" in header

    def test_the_csrf_cookie_is_readable_by_javascript(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        """Double-submit only works if the SPA can copy it into a header."""
        response = client.post(LOGIN, json={"email": owner.email, "password": owner_password})

        header = next(
            h for h in response.headers.get_list("set-cookie") if h.startswith("csrf_token=")
        )
        assert "httponly" not in header.lower()

    def test_the_session_token_is_not_stored_in_the_clear(
        self, client: TestClient, db_session: OrmSession, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)
        token = client.cookies[SESSION_COOKIE_NAME]

        stored = db_session.execute(sa.select(Session.token_hash)).scalars().all()
        assert stored
        assert token not in stored

    def test_email_is_matched_case_insensitively(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        response = client.post(
            LOGIN, json={"email": "OWNER@Example.COM", "password": owner_password}
        )
        assert response.status_code == 204

    def test_surrounding_whitespace_in_the_email_is_tolerated(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        response = client.post(
            LOGIN, json={"email": "  owner@example.com  ", "password": owner_password}
        )
        assert response.status_code == 204

    def test_a_wrong_password_is_401_with_the_error_code(
        self, client: TestClient, owner: Owner
    ) -> None:
        response = client.post(LOGIN, json={"email": owner.email, "password": "wrong"})

        assert response.status_code == 401
        assert response.json() == {"error": {"code": "invalid_credentials", "field": None}}

    def test_no_session_cookie_is_issued_on_failure(self, client: TestClient, owner: Owner) -> None:
        client.post(LOGIN, json={"email": owner.email, "password": "wrong"})
        assert not client.cookies.get(SESSION_COOKIE_NAME)

    def test_an_unknown_email_and_a_wrong_password_are_indistinguishable(
        self, client: TestClient, owner: Owner
    ) -> None:
        """The whole point: no user enumeration.

        Status, body and headers must all match — a difference in any of the three
        is an oracle telling an attacker which addresses have accounts.
        """
        wrong_password = client.post(LOGIN, json={"email": owner.email, "password": "wrong"})
        unknown_email = client.post(
            LOGIN, json={"email": "nobody@example.com", "password": "wrong"}
        )

        assert wrong_password.status_code == unknown_email.status_code
        assert wrong_password.content == unknown_email.content

        ignored = {"date", "server", "content-length"}

        def comparable(response: object) -> dict[str, str]:
            headers = response.headers  # type: ignore[attr-defined]
            return {k.lower(): v for k, v in headers.items() if k.lower() not in ignored}

        assert comparable(wrong_password) == comparable(unknown_email)

    @pytest.mark.parametrize(
        "payload",
        [
            {"email": "not-an-email", "password": "x"},
            {"email": "owner@example.com"},
            {"password": "x"},
            {"email": "owner@example.com", "password": "x", "extra": "field"},
            {},
        ],
    )
    def test_malformed_bodies_answer_the_projects_error_shape(
        self, client: TestClient, payload: dict[str, str]
    ) -> None:
        """Not FastAPI's default list-of-dicts, which leaks internal field paths."""
        response = client.post(LOGIN, json=payload)

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "validation_error"

    def test_an_unknown_field_is_rejected(self, client: TestClient, owner: Owner) -> None:
        """`extra="forbid"`: a typo'd field silently ignored is a bug that ships."""
        response = client.post(
            LOGIN, json={"email": owner.email, "password": "x", "remember_me": True}
        )
        assert response.status_code == 422


class TestMe:
    def test_me_requires_a_session(self, client: TestClient) -> None:
        response = client.get(ME)

        assert response.status_code == 401
        assert response.json() == {"error": {"code": "not_authenticated", "field": None}}

    def test_me_returns_the_owner_without_the_hash(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)

        response = client.get(ME)

        assert response.status_code == 200
        body = response.json()
        assert body == {"id": str(owner.id), "email": owner.email, "locale": "pl"}
        assert "password_hash" not in response.text

    def test_a_garbage_session_cookie_is_401_not_500(self, client: TestClient) -> None:
        client.cookies.set(SESSION_COOKIE_NAME, "not-a-real-token")
        response = client.get(ME)
        assert response.status_code == 401

    def test_an_expired_session_is_refused_and_deleted(
        self,
        client: TestClient,
        db_session: OrmSession,
        owner: Owner,
        owner_password: str,
    ) -> None:
        sign_in(client, owner.email, owner_password)

        db_session.execute(
            sa.update(Session).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        db_session.flush()

        assert client.get(ME).status_code == 401
        assert db_session.execute(sa.select(sa.func.count()).select_from(Session)).scalar() == 0

    def test_the_locale_can_be_updated(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)

        response = client.patch(ME, json={"locale": "en"}, headers=csrf_headers(client))

        assert response.status_code == 200
        assert response.json()["locale"] == "en"
        assert client.get(ME).json()["locale"] == "en"

    def test_an_unsupported_locale_is_refused(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)

        response = client.patch(ME, json={"locale": "de"}, headers=csrf_headers(client))

        assert response.status_code == 422

    def test_the_email_cannot_be_changed_through_the_locale_endpoint(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)

        response = client.patch(
            ME,
            json={"locale": "en", "email": "attacker@example.com"},
            headers=csrf_headers(client),
        )

        assert response.status_code == 422


class TestCsrf:
    def test_an_unsafe_method_without_the_header_is_refused(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)

        response = client.patch(ME, json={"locale": "en"})

        assert response.status_code == 403
        assert response.json() == {"error": {"code": "csrf_token_invalid", "field": None}}

    def test_a_mismatched_header_is_refused(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)

        response = client.patch(
            ME, json={"locale": "en"}, headers={CSRF_HEADER_NAME: "a-different-token"}
        )

        assert response.status_code == 403

    def test_the_locale_is_unchanged_after_a_refused_request(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)
        client.patch(ME, json={"locale": "en"})

        assert client.get(ME).json()["locale"] == "pl"

    def test_safe_methods_need_no_token(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)
        assert client.get(ME).status_code == 200


class TestLogout:
    def test_logout_deletes_the_session_row(
        self,
        client: TestClient,
        db_session: OrmSession,
        owner: Owner,
        owner_password: str,
    ) -> None:
        """Real revocation is the reason this is a table and not a JWT."""
        sign_in(client, owner.email, owner_password)
        assert db_session.execute(sa.select(sa.func.count()).select_from(Session)).scalar() == 1

        response = client.post(LOGOUT, headers=csrf_headers(client))

        assert response.status_code == 204
        assert db_session.execute(sa.select(sa.func.count()).select_from(Session)).scalar() == 0

    def test_the_token_stops_working_even_if_the_cookie_is_kept(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)
        token = client.cookies[SESSION_COOKIE_NAME]

        client.post(LOGOUT, headers=csrf_headers(client))

        client.cookies.set(SESSION_COOKIE_NAME, token)
        assert client.get(ME).status_code == 401

    def test_logout_is_idempotent_without_a_session(self, client: TestClient) -> None:
        assert client.post(LOGOUT).status_code == 204

    def test_logout_clears_the_cookies(
        self, client: TestClient, owner: Owner, owner_password: str
    ) -> None:
        sign_in(client, owner.email, owner_password)

        response = client.post(LOGOUT, headers=csrf_headers(client))

        assert any(
            'session=""' in header or "session=;" in header or "Max-Age=0" in header
            for header in response.headers.get_list("set-cookie")
        )


class TestCookieSecurity:
    def test_cookies_are_marked_secure_in_production(
        self, db_session: OrmSession, database_url: str, owner: Owner, owner_password: str
    ) -> None:
        """A session cookie without Secure can travel in clear over a downgraded link."""
        from fastapi.testclient import TestClient as Client

        from trip_planner.api.deps import get_db
        from trip_planner.app import create_app
        from trip_planner.config import get_settings

        production = Settings(
            database_url=database_url,
            session_secret="x" * 48,
            app_base_url="https://planner.example.com",
            environment="production",
        )

        application = create_app(check_configuration=False)
        application.dependency_overrides[get_db] = lambda: db_session
        application.dependency_overrides[get_settings] = lambda: production

        with Client(application, base_url="https://testserver") as secure_client:
            response = secure_client.post(
                LOGIN, json={"email": owner.email, "password": owner_password}
            )

        assert response.status_code == 204
        for header in response.headers.get_list("set-cookie"):
            assert "Secure" in header, header
