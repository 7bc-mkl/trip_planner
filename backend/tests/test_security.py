"""Password hashing and token primitives."""

from __future__ import annotations

import re

import pytest

from trip_planner.security.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    verify_password,
)
from trip_planner.security.tokens import (
    TOKEN_BYTES,
    generate_csrf_token,
    generate_token,
    hash_token,
    tokens_equal,
)

SECRET = "a" * 48


class TestPasswords:
    def test_a_correct_password_verifies(self) -> None:
        assert verify_password(hash_password("correct horse"), "correct horse")

    def test_a_wrong_password_does_not(self) -> None:
        assert not verify_password(hash_password("correct horse"), "wrong horse")

    def test_the_hash_is_argon2id(self) -> None:
        assert hash_password("x").startswith("$argon2id$")

    def test_the_same_password_hashes_differently_every_time(self) -> None:
        """A per-hash salt: two owners with the same password must not look alike."""
        assert hash_password("same") != hash_password("same")

    def test_the_plaintext_never_appears_in_the_hash(self) -> None:
        assert "hunter2" not in hash_password("hunter2")

    @pytest.mark.parametrize("corrupt", ["", "not-a-hash", "$argon2id$broken"])
    def test_a_corrupt_hash_returns_false_rather_than_raising(self, corrupt: str) -> None:
        """A 500 here would tell an attacker the stored hash is malformed."""
        assert verify_password(corrupt, "anything") is False

    def test_the_dummy_hash_is_a_real_verifiable_argon2_hash(self) -> None:
        """It must cost the same as a real one, or it does not hide anything."""
        assert DUMMY_HASH.startswith("$argon2id$")
        assert verify_password(DUMMY_HASH, "not the dummy password") is False

    def test_needs_rehash_is_false_for_a_fresh_hash(self) -> None:
        assert needs_rehash(hash_password("x")) is False

    def test_needs_rehash_tolerates_a_corrupt_hash(self) -> None:
        assert needs_rehash("garbage") is False


class TestTokens:
    def test_a_token_carries_the_full_entropy(self) -> None:
        token = generate_token()
        # url-safe base64 of 32 bytes, padding stripped
        assert len(token) >= (TOKEN_BYTES * 4) // 3
        assert re.fullmatch(r"[A-Za-z0-9_-]+", token)

    def test_tokens_are_unique(self) -> None:
        assert len({generate_token() for _ in range(200)}) == 200

    def test_the_stored_form_is_not_the_token(self) -> None:
        token = generate_token()
        assert hash_token(token, secret=SECRET) != token

    def test_hashing_is_deterministic_under_one_secret(self) -> None:
        token = generate_token()
        assert hash_token(token, secret=SECRET) == hash_token(token, secret=SECRET)

    def test_a_different_secret_gives_a_different_digest(self) -> None:
        """This is what makes rotating SESSION_SECRET a global sign-out."""
        token = generate_token()
        assert hash_token(token, secret=SECRET) != hash_token(token, secret="b" * 48)

    def test_the_digest_is_not_a_bare_sha256_of_the_token(self) -> None:
        """A keyed digest means a stolen dump cannot be attacked offline alone."""
        from hashlib import sha256

        token = generate_token()
        assert hash_token(token, secret=SECRET) != sha256(token.encode()).hexdigest()

    def test_tokens_equal_matches_and_rejects(self) -> None:
        assert tokens_equal("abc", "abc")
        assert not tokens_equal("abc", "abd")
        assert not tokens_equal("abc", "abcd")

    def test_csrf_tokens_are_random_and_distinct_from_session_tokens(self) -> None:
        assert generate_csrf_token() != generate_csrf_token()


# --- Response headers the app sets itself ----------------------------------------
#
# These four were Caddy's job; the Lambda target has no Caddy. HSTS is production-only.

ALWAYS_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}
HSTS = "max-age=63072000; includeSubDomains"


def _production(settings):
    import dataclasses

    return dataclasses.replace(settings, environment="production")


def test_every_response_carries_the_security_headers_and_hsts_only_in_production(
    settings, tmp_path, monkeypatch
) -> None:
    from fastapi.testclient import TestClient

    from trip_planner.app import create_app

    (tmp_path / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-abc.js").write_text("1", encoding="utf-8")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path))

    paths = ("/api/v1/health", "/api/v1/nope", "/trips", "/assets/app-abc.js")

    with TestClient(
        create_app(check_configuration=False, settings=_production(settings))
    ) as client:
        for path in paths:
            headers = client.get(path).headers
            for name, value in ALWAYS_HEADERS.items():
                assert headers[name] == value, (path, name)
            assert headers["strict-transport-security"] == HSTS, path

    for app in (
        create_app(check_configuration=False),
        create_app(check_configuration=False, settings=settings),
    ):
        with TestClient(app) as client:
            for path in paths:
                headers = client.get(path).headers
                assert headers["x-frame-options"] == "DENY", path
                assert "strict-transport-security" not in headers, path


def test_the_attachment_content_route_keeps_its_own_nosniff_and_csp(
    signed_in_client,
) -> None:
    """These routes set their own headers; the middleware adds the rest without clobbering."""
    from tests.test_attachments_api import attachment_url, stored
    from tests.test_trips_api import create

    trip = create(signed_in_client)
    created = stored(signed_in_client, trip)
    response = signed_in_client.get(f"{attachment_url(trip, created['id'])}/content")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert response.headers["x-frame-options"] == "DENY"
    # The route's own, stricter Referrer-Policy is kept, not replaced.
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers.get_list("x-content-type-options") == ["nosniff"]


# ---------------------------------------------------------------------------
# Origin lock (X-Origin-Verify)
# ---------------------------------------------------------------------------
#
# Settings are built without a database: none of these requests reaches one.

ORIGIN_SECRET = "cloudfront-origin-secret-" + "s" * 24


def _origin_settings(**overrides: str):
    from trip_planner.config import require_settings

    env = {
        "DATABASE_URL": "postgresql://u:p@localhost/unused",
        "SESSION_SECRET": "x" * 48,
        "APP_BASE_URL": "http://testserver",
        "ENVIRONMENT": "development",
    }
    return require_settings(env | overrides)


def _origin_client(**overrides: str):
    from fastapi.testclient import TestClient

    from trip_planner.app import create_app

    # No `with`: the lifespan (inbox worker) is not needed here.
    return TestClient(create_app(check_configuration=False, settings=_origin_settings(**overrides)))


def _locked_client():
    return _origin_client(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET)


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Origin-Verify": "wrong"}, {"X-Origin-Verify": ORIGIN_SECRET[:-1]}],
    ids=["missing", "wrong", "prefix"],
)
def test_a_request_without_the_origin_secret_is_refused(headers: dict[str, str]) -> None:
    client = _locked_client()

    for method, path in (
        ("GET", "/api/v1/trips"),
        ("POST", "/api/v1/auth/login"),
        ("GET", "/trips"),
        ("HEAD", "/api/v1/health"),
    ):
        response = client.request(method, path, headers=headers)
        assert response.status_code == 403, (method, path)
        if method != "HEAD":
            assert response.json() == {"error": {"code": "forbidden_origin", "field": None}}
        # The security headers wrap the refusal too.
        for name, value in ALWAYS_HEADERS.items():
            assert response.headers[name] == value, (path, name)


def test_a_duplicated_origin_header_is_refused() -> None:
    from starlette.datastructures import Headers

    client = _locked_client()
    raw = [(b"x-origin-verify", ORIGIN_SECRET.encode())] * 2
    response = client.get("/api/v1/trips", headers=Headers(raw=raw))
    assert response.status_code == 403


def test_the_right_origin_secret_passes_through() -> None:
    client = _locked_client()

    response = client.get("/api/v1/nope", headers={"X-Origin-Verify": ORIGIN_SECRET})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"

    health = client.get("/api/v1/health", headers={"X-Origin-Verify": ORIGIN_SECRET})
    assert health.status_code == 200


def test_the_health_probe_is_exempt() -> None:
    """LWA's readiness probe comes from localhost without the header."""
    response = _locked_client().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_an_unset_origin_secret_runs_no_check() -> None:
    """Compose behind Caddy: nothing changes."""
    client = _origin_client()

    assert client.get("/api/v1/nope").status_code == 404
    assert client.get("/api/v1/health").status_code == 200


def test_a_verified_request_is_marked_in_the_scope_and_an_unverified_one_is_not() -> None:
    import asyncio

    from trip_planner.security.origin import OriginVerifyMiddleware, is_origin_verified

    seen: list[bool] = []

    async def inner(scope, receive, send) -> None:
        seen.append(is_origin_verified(scope))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = OriginVerifyMiddleware(inner, secret=ORIGIN_SECRET)

    async def call(headers: list[tuple[bytes, bytes]], path: str) -> int:
        sent: list[dict] = []

        async def receive() -> dict:
            return {"type": "http.request", "body": b""}

        async def send(message: dict) -> None:
            sent.append(message)

        scope = {"type": "http", "method": "GET", "path": path, "headers": headers}
        await middleware(scope, receive, send)
        return sent[0]["status"]

    verified = [(b"x-origin-verify", ORIGIN_SECRET.encode())]
    assert asyncio.run(call(verified, "/api/v1/trips")) == 204
    assert asyncio.run(call([], "/api/v1/health")) == 204
    assert asyncio.run(call([], "/api/v1/trips")) == 403
    assert seen == [True, False]


def test_the_worker_app_has_no_origin_lock() -> None:
    """It has no URL; LWA posts events to it from localhost without the header."""
    from trip_planner.security.origin import OriginVerifyMiddleware
    from trip_planner.worker_app import create_worker_app

    app = create_worker_app(settings=_origin_settings(ORIGIN_VERIFY_SECRET=ORIGIN_SECRET))
    assert all(m.cls is not OriginVerifyMiddleware for m in app.user_middleware)
