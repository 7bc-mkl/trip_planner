"""Empty baseline.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-05

Creates nothing. It exists so that every later phase is one revision on top of a
known starting point, and so `alembic upgrade head` is a valid release step from
the very first deployment.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
