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


def test_missing_required_variable_is_fatal_and_names_the_variable() -> None:
    with pytest.raises(MissingConfiguration) as caught:
        require_settings({})

    assert "DATABASE_URL" in caught.value.missing
    assert "DATABASE_URL" in str(caught.value)


def test_every_missing_variable_is_named_at_once() -> None:
    """An operator should not have to restart once per unset variable."""
    with pytest.raises(MissingConfiguration) as caught:
        require_settings({})

    assert caught.value.missing == ["DATABASE_URL", "SESSION_SECRET"]


def test_blank_is_treated_as_unset() -> None:
    """An empty string in a platform's env editor is a mistake, not a value."""
    with pytest.raises(MissingConfiguration):
        require_settings({"DATABASE_URL": "   ", "SESSION_SECRET": VALID_SECRET})


def test_a_short_session_secret_is_refused() -> None:
    """A short secret is worse than a missing one: it looks configured."""
    with pytest.raises(WeakConfiguration) as caught:
        require_settings({"DATABASE_URL": "postgresql://u:p@h/d", "SESSION_SECRET": "short"})

    assert "SESSION_SECRET" in str(caught.value)


def test_a_complete_environment_resolves() -> None:
    settings = require_settings(
        {"DATABASE_URL": "postgresql://u:p@h/d", "SESSION_SECRET": VALID_SECRET}
    )
    assert settings.session_secret == VALID_SECRET


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
    assert Settings(database_url=given, session_secret=VALID_SECRET).sqlalchemy_url == expected
