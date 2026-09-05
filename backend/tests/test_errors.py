"""The error-code contract.

This file is the half of R01 that `scripts/check_locales.py` structurally cannot
cover. That gate compares the two locale files *against each other*, so a code
whose key is missing from both is invisible to it: the message would render blank
in Polish and in English, and the gate would still be green.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trip_planner.errors import (
    GENERATED_TS_PATH,
    STATUS_FOR_CODE,
    ApiError,
    ErrorCode,
    error_body,
    typescript_union,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCALES = REPO_ROOT / "frontend" / "src" / "locales"
REQUIRED_LOCALES = ["en", "pl"]


def load_locale(locale: str) -> dict[str, object]:
    return json.loads((LOCALES / f"{locale}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("locale", REQUIRED_LOCALES)
@pytest.mark.parametrize("code", list(ErrorCode), ids=lambda c: c.value)
def test_every_error_code_resolves_to_a_non_empty_message(code: ErrorCode, locale: str) -> None:
    messages = load_locale(locale).get("error", {})
    assert isinstance(messages, dict)

    assert code.value in messages, (
        f"'{locale}.json' has no error.{code.value}. Add it to both locale files — "
        "check_locales.py cannot catch this, because a key missing from both is "
        "consistent."
    )
    value = messages[code.value]
    assert isinstance(value, str) and value.strip(), f"error.{code.value} is empty in '{locale}'"


@pytest.mark.parametrize("locale", REQUIRED_LOCALES)
def test_no_locale_carries_an_error_key_no_code_produces(locale: str) -> None:
    """The other direction: copy for an error that cannot happen is dead weight."""
    messages = load_locale(locale)["error"]
    assert isinstance(messages, dict)

    known = {code.value for code in ErrorCode} | {"unknown"}
    stray = sorted(set(messages) - known)
    assert stray == [], (
        f"'{locale}.json' defines error keys no ErrorCode produces: {stray}. "
        "Remove them, or add the matching enum member."
    )


def test_every_code_has_a_status() -> None:
    """A code without a status would 500 at the moment it is first raised."""
    assert set(STATUS_FOR_CODE) == set(ErrorCode)


def test_the_generated_typescript_union_is_current() -> None:
    checked_in = (REPO_ROOT / GENERATED_TS_PATH).read_text(encoding="utf-8")
    assert checked_in == typescript_union(), (
        f"{GENERATED_TS_PATH} is stale. Regenerate it with: "
        "(cd backend && uv run python -m trip_planner.errors)"
    )


def test_error_body_shape() -> None:
    assert error_body(ErrorCode.NOT_FOUND) == {"error": {"code": "not_found", "field": None}}
    assert error_body(ErrorCode.VALIDATION_ERROR, "email") == {
        "error": {"code": "validation_error", "field": "email"}
    }


def test_api_error_carries_the_mapped_status() -> None:
    error = ApiError(ErrorCode.INVALID_CREDENTIALS)
    assert error.status_code == 401
    assert error.detail == {"error": {"code": "invalid_credentials", "field": None}}


def test_error_codes_are_lower_snake_case() -> None:
    """The wire format is a stable identifier, not prose."""
    for code in ErrorCode:
        assert code.value.islower()
        assert " " not in code.value
