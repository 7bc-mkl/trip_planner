"""inbound_action_item

Revision ID: 0009_inbound_action_item
Revises: 0008_inbound_model_egress
Create Date: 2026-11-07

Phase 3 of the reservation inbox: the action item, which is D21 as a table. A
forwarded confirmation changes a plan only through one of these rows, and only
once the owner has approved it field by field.

One new table, so "safe against rows that already exist" is satisfied
trivially — nothing existing changes shape, and every Phase 2 message is valid
with no action items, which is exactly what it means: routed, not yet proposed.

**Rolling back returns the deployment to a routing inbox.** Messages, their
documents and their routes are Phase 1 and Phase 2 and survive untouched. What
the downgrade destroys is every pending proposal and the record of what each
approval wrote — so after a rollback an approval can no longer be undone. The
writes themselves stay on the items, where the owner can edit them like any
other value.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_inbound_action_item"
down_revision: str | None = "0008_inbound_model_egress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Literals rather than imports from `db.models`, for the reason revision 0007
#: gives: a migration describes the schema *at this revision*.
_KINDS = ("update_item", "create_item")
_STATES = ("pending", "approved", "rejected", "superseded")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "inbound_action_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_trip_day_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal", postgresql.JSONB(), nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("state", sa.Text(), server_default="pending", nullable=False),
        sa.Column("applied", postgresql.JSONB(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(_in_list("kind", _KINDS), name="ck_inbound_action_item_kind"),
        sa.CheckConstraint(_in_list("state", _STATES), name="ck_inbound_action_item_state"),
        sa.CheckConstraint("revision >= 1", name="ck_inbound_action_item_revision"),
        # An `update_item` never names a day and a `create_item` never names an
        # item. Either may name neither while it waits for the owner's target.
        sa.CheckConstraint(
            "(kind = 'update_item' AND target_trip_day_id IS NULL)"
            " OR (kind = 'create_item' AND target_item_id IS NULL)",
            name="ck_inbound_action_item_target_matches_kind",
        ),
        sa.ForeignKeyConstraint(
            ["inbound_message_id"], ["inbound_message.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_item_id"], ["item.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_trip_day_id"], ["trip_day.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inbound_action_item_inbound_message_id",
        "inbound_action_item",
        ["inbound_message_id"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_action_item_owner_id", "inbound_action_item", ["owner_id"], unique=False
    )
    op.create_index(
        "ix_inbound_action_item_target_item_id",
        "inbound_action_item",
        ["target_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_action_item_target_trip_day_id",
        "inbound_action_item",
        ["target_trip_day_id"],
        unique=False,
    )
    # The badge's query, read on every page load.
    op.create_index(
        "ix_inbound_action_item_pending",
        "inbound_action_item",
        ["owner_id"],
        unique=False,
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_inbound_action_item_pending", table_name="inbound_action_item")
    op.drop_index("ix_inbound_action_item_target_trip_day_id", table_name="inbound_action_item")
    op.drop_index("ix_inbound_action_item_target_item_id", table_name="inbound_action_item")
    op.drop_index("ix_inbound_action_item_owner_id", table_name="inbound_action_item")
    op.drop_index("ix_inbound_action_item_inbound_message_id", table_name="inbound_action_item")
    op.drop_table("inbound_action_item")
