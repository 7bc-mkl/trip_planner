"""The repository's own TODO rows, where this milestone closed them.

`AGENTS.md` says a TODO row must be filled in by whoever establishes the
convention. Each row below was decided by the walking-skeleton spec or by the
code that implemented it, and a decision that is not written down where the next
agent reads it has not really been made — so the exact strings are asserted
absent rather than trusted to review vigilance.

Rows deliberately still open are asserted *present*, so that deleting one
without building the thing it points at fails here too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

RESOLVED = [
    ("AGENTS.md", "i18n | TODO", "the i18n library is react-i18next + i18next-icu (spec A6)"),
    (
        "AGENTS.md",
        "TODO: name the validation library",
        "request validation is Pydantic v2 (spec A7)",
    ),
    (
        "BACKWARD_COMPATIBILITY.md",
        "**Versioning:** TODO",
        "API versioning is a /api/v1 URL prefix (spec A13)",
    ),
    (
        "AGENTS.md",
        "TODO: point at the domain module",
        "backend/trip_planner/domain/ exists as of the Phase 2-4 implementation",
    ),
    (
        "CODE_REVIEW.md",
        "TODO: name the validation library",
        "request validation is Pydantic v2 with extra=\"forbid\" (spec A7)",
    ),
]

STILL_OPEN = [
    (
        "AGENTS.md",
        "TODO — integration module not yet created",
        "D04 and R07 exclude external calls from the first version",
    ),
]


@pytest.mark.parametrize(("filename", "marker", "because"), RESOLVED)
def test_resolved_todo_is_gone(filename: str, marker: str, because: str) -> None:
    text = (REPO_ROOT / filename).read_text(encoding="utf-8")
    assert marker not in text, f"{filename} still carries '{marker}', but {because}"


@pytest.mark.parametrize(("filename", "marker", "because"), STILL_OPEN)
def test_open_todo_is_still_recorded(filename: str, marker: str, because: str) -> None:
    text = (REPO_ROOT / filename).read_text(encoding="utf-8")
    assert marker in text, f"{filename} dropped '{marker}', but {because}"
