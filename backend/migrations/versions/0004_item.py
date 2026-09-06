"""item

Revision ID: 0004_item
Revises: 0003_trip_stage_day
Create Date: 2026-09-05

Phase 3 of the walking skeleton, and the last table this milestone adds. One
table that did not exist, so the downgrade is a clean drop.

The two CHECK constraints are the point of this revision. `ck_item_status` is
what makes R02 structural rather than conventional: with only three storable
statuses, the readiness arithmetic cannot be broken by a write path that invents
a fourth. `ck_item_kind` does the same for the filter bar's chips.

The nullable span columns (`end_time`, `end_date`) ship here rather than later
because an item without a span cannot express an overnight flight or three nights
in one hotel, and splitting such an item in two would make it count twice in the
readiness fraction.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_item"
down_revision: str | None = "0003_trip_stage_day"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_day_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="to_plan", nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('accommodation', 'transport', 'activity', 'meal', 'other')",
            name="ck_item_kind",
        ),
        sa.CheckConstraint("position >= 0", name="ck_item_position"),
        sa.CheckConstraint("status IN ('to_plan', 'to_book', 'done')", name="ck_item_status"),
        sa.ForeignKeyConstraint(["trip_day_id"], ["trip_day.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_item_trip_day_id", "item", ["trip_day_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_item_trip_day_id", table_name="item")
    op.drop_table("item")
