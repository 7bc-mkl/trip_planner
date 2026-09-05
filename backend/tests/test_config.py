"""Settings resolution."""

from __future__ import annotations

import pytest

from trip_planner.config import MissingConfiguration, Settings, require_settings


def test_missing_required_variable_is_fatal_and_names_the_variable() -> None:
    with pytest.raises(MissingConfiguration) as caught:
        require_settings({})

    assert "DATABASE_URL" in caught.value.missing
    assert "DATABASE_URL" in str(caught.value)


def test_blank_is_treated_as_unset() -> None:
    """An empty string in a platform's env editor is a mistake, not a value."""
    with pytest.raises(MissingConfiguration):
        require_settings({"DATABASE_URL": "   "})


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
    assert Settings(database_url=given).sqlalchemy_url == expected
