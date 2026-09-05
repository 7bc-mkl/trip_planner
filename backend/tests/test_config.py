"""Settings resolution."""

from __future__ import annotations

import pytest

from trip_planner.config import (
    MissingConfiguration,
    Settings,
    WeakConfiguration,
    require_settings,
)

VALID_SECRET = "x" * 48

#: A complete, valid environment. Individual tests break one thing at a time.
COMPLETE_ENV = {
    "DATABASE_URL": "postgresql://u:p@h/d",
    "SESSION_SECRET": VALID_SECRET,
    "APP_BASE_URL": "https://planner.example.com",
    "ENVIRONMENT": "production",
}


def env_without(*names: str) -> dict[str, str]:
    return {k: v for k, v in COMPLETE_ENV.items() if k not in names}


def env_with(**overrides: str) -> dict[str, str]:
    return COMPLETE_ENV | overrides


def test_missing_required_variable_is_fatal_and_names_the_variable() -> None:
    with pytest.raises(MissingConfiguration) as caught:
        require_settings({})

    assert "DATABASE_URL" in caught.value.missing
    assert "DATABASE_URL" in str(caught.value)


def test_every_missing_variable_is_named_at_once() -> None:
    """An operator should not have to restart once per unset variable."""
    with pytest.raises(MissingConfiguration) as caught:
        require_settings({})

    assert caught.value.missing == [
        "APP_BASE_URL",
        "DATABASE_URL",
        "ENVIRONMENT",
        "SESSION_SECRET",
    ]


def test_blank_is_treated_as_unset() -> None:
    """An empty string in a platform's env editor is a mistake, not a value."""
    with pytest.raises(MissingConfiguration):
        require_settings(env_with(DATABASE_URL="   "))


def test_a_short_session_secret_is_refused() -> None:
    """A short secret is worse than a missing one: it looks configured."""
    with pytest.raises(WeakConfiguration) as caught:
        require_settings(env_with(SESSION_SECRET="short"))

    assert "SESSION_SECRET" in str(caught.value)


def test_a_complete_environment_resolves() -> None:
    settings = require_settings(COMPLETE_ENV)
    assert settings.session_secret == VALID_SECRET
    assert settings.is_production
    assert settings.cookies_are_secure


def test_production_refuses_a_non_https_base_url() -> None:
    """The session cookie is Secure; over http the browser silently drops it."""
    with pytest.raises(WeakConfiguration) as caught:
        require_settings(env_with(APP_BASE_URL="http://planner.example.com"))

    assert "APP_BASE_URL" in str(caught.value)


def test_development_allows_http_and_does_not_mark_cookies_secure() -> None:
    settings = require_settings(
        env_with(ENVIRONMENT="development", APP_BASE_URL="http://localhost:5173")
    )
    assert not settings.is_production
    assert not settings.cookies_are_secure


def test_an_unknown_environment_is_refused() -> None:
    with pytest.raises(WeakConfiguration):
        require_settings(env_with(ENVIRONMENT="staging"))


def test_a_trailing_slash_on_the_base_url_is_normalised_away() -> None:
    settings = require_settings(env_with(APP_BASE_URL="https://planner.example.com/"))
    assert settings.app_base_url == "https://planner.example.com"


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
        ("postgresql+psycopg://u:p@h/d", "postgresql+psycopg://u:p@h/d"),
    ],
)
def test_platform_connection_strings_are_normalised_to_the_pinned_driver(
    given: str, expected: str
) -> None:
    """Managed platforms hand out postgres:// or postgresql://; the app pins psycopg 3."""
    settings = Settings(
        database_url=given,
        session_secret=VALID_SECRET,
        app_base_url="https://x.example.com",
        environment="production",
    )
    assert settings.sqlalchemy_url == expected
