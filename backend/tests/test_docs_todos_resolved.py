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
    (
        "AGENTS.md",
        "TODO — integration module not yet created",
        "backend/trip_planner/inbound/ is the integration module, added by the "
        "reservation inbox's first phase. D04 and R07 exclude live price, inventory "
        "and vendor lookup — they have never excluded taking delivery of mail the "
        "owner forwarded himself, which is what D20 and D25 ask for",
    ),
]

#: Empty, and that is a real state rather than a placeholder: every TODO row the
#: earlier milestones left has now been answered by the code that established the
#: convention. A new row added to a doc belongs here until it is.
STILL_OPEN: list[tuple[str, str, str]] = []


@pytest.mark.parametrize(("filename", "marker", "because"), RESOLVED)
def test_resolved_todo_is_gone(filename: str, marker: str, because: str) -> None:
    text = (REPO_ROOT / filename).read_text(encoding="utf-8")
    assert marker not in text, f"{filename} still carries '{marker}', but {because}"


def test_open_todos_are_still_recorded() -> None:
    """Deleting a TODO row without building the thing it points at fails here.

    Written as one test over the list rather than a parametrized case per row,
    because `STILL_OPEN` is legitimately empty today and an empty parametrize
    argument is a pytest warning — which this suite turns into an error.
    """
    for filename, marker, because in STILL_OPEN:
        text = (REPO_ROOT / filename).read_text(encoding="utf-8")
        assert marker in text, f"{filename} dropped '{marker}', but {because}"


def test_every_inbox_variable_is_documented_where_an_operator_looks() -> None:
    """A setting that exists only in `config.py` is a setting nobody can find.

    Both places, because they answer different questions: the README explains
    what to set and what AWS has to look like, and the QA template is what a
    tester copies. A variable renamed in code and not in the docs fails here
    rather than in an environment that silently runs with the inbox off.
    """
    from trip_planner.config import (
        INBOX_ENVIRONMENT_VARIABLES,
        INBOX_OPTIONAL_ENVIRONMENT_VARIABLES,
    )

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    template = (REPO_ROOT / ".ai/qa/test-env.env.example").read_text(encoding="utf-8")

    for name in INBOX_ENVIRONMENT_VARIABLES | INBOX_OPTIONAL_ENVIRONMENT_VARIABLES:
        assert name in readme, f"README.md does not document {name}"
        assert name in template, f".ai/qa/test-env.env.example does not mention {name}"


def test_the_qa_template_carries_no_filled_in_secret() -> None:
    """The template is committed; the copy made from it is not, and must stay that way."""
    template = (REPO_ROOT / ".ai/qa/test-env.env.example").read_text(encoding="utf-8")

    assert "SESSION_SECRET=''" in template
    # No AWS key material belongs in a committed file even as an example.
    assert "AKIA" not in template
    assert "aws_secret_access_key" not in template.lower()
