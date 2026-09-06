"""trip, trip_stage and trip_day

Revision ID: 0003_trip_stage_day
Revises: 0002_owner_session_login_attempt
Create Date: 2026-09-05

Phase 2 of the walking skeleton. Three tables that did not exist, so the "safe
against rows that already exist" rule in BACKWARD_COMPATIBILITY.md is vacuous
here and the downgrade is a clean drop.

The one constraint worth reading twice is `uq_trip_stage_position`: it is
DEFERRABLE INITIALLY DEFERRED so the dense-renumbering UPDATE after a stage is
deleted from the middle can shift every later position in one statement without
transiently colliding with itself.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_trip_stage_day"
down_revision: str | None = "0002_owner_session_login_attempt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trip",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("departure_place", sa.Text(), nullable=False),
        # NULL is meaningful: it is the one-way route mode, not missing data.
        sa.Column("return_place", sa.Text(), nullable=True),
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
        sa.CheckConstraint("end_date >= start_date", name="ck_trip_date_range"),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_owner_id", "trip", ["owner_id"], unique=False)

    op.create_table(
        "trip_stage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("place", sa.Text(), nullable=False),
        # Nullable by design: a stage whose dates are undecided labels no day.
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
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
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_trip_stage_date_range",
        ),
        sa.CheckConstraint("position >= 0", name="ck_trip_stage_position"),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trip_id",
            "position",
            name="uq_trip_stage_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index("ix_trip_stage_trip_id", "trip_stage", ["trip_id"], unique=False)

    op.create_table(
        "trip_day",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "date", name="uq_trip_day_date"),
    )
    op.create_index("ix_trip_day_trip_id", "trip_day", ["trip_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trip_day_trip_id", table_name="trip_day")
    op.drop_table("trip_day")

    op.drop_index("ix_trip_stage_trip_id", table_name="trip_stage")
    op.drop_table("trip_stage")

    op.drop_index("ix_trip_owner_id", table_name="trip")
    op.drop_table("trip")
