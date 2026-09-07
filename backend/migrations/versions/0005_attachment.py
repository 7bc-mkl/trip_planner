"""attachment

Revision ID: 0005_attachment
Revises: 0004_item
Create Date: 2026-09-06

Phase 1 of the attachments slice: three tables that did not exist, so the
downgrade is a clean drop and "safe against rows that already exist" is vacuous
for all three (BACKWARD_COMPATIBILITY.md §2).

`attachment` and `attachment_blob` are two tables on purpose. Keeping the bytes
out of the metadata row is what makes "list a day's six photos" read six
filenames rather than sixty megabytes — a property of the schema, not of every
query remembering a loader option.

The three CHECK constraints are the point. `ck_attachment_exactly_one_parent`
makes an orphaned attachment and a two-parent attachment both unrepresentable,
which is what buys the two-nullable-FK shape its referential integrity over a
polymorphic parent key. `ck_attachment_content_type` means even a write path that
trusted the client's `Content-Type` header could still only store one of the
three types the sniffer derives. `ck_attachment_byte_size` restates the per-file
cap where no code path can skip it.

**The `item` reservation columns are deliberately not here.** They ship in
`0006_item_reservation`, so reservation data can be rolled back without taking
attachments with it, and so the columns never exist during a phase that cannot
populate them.

A downgrade drops the tables and therefore destroys the files in them. That is
what downgrading a feature migration means, and it is written down here so nobody
discovers it at 02:00.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_attachment"
down_revision: str | None = "0004_item"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attachment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trip_day_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "byte_size > 0 AND byte_size <= 10485760",
            name="ck_attachment_byte_size",
        ),
        sa.CheckConstraint(
            "content_type IN ('application/pdf', 'image/jpeg', 'image/png')",
            name="ck_attachment_content_type",
        ),
        sa.CheckConstraint(
            "(item_id IS NULL) <> (trip_day_id IS NULL)",
            name="ck_attachment_exactly_one_parent",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["item.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_day_id"], ["trip_day.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attachment_item_id", "attachment", ["item_id"], unique=False)
    op.create_index("ix_attachment_trip_day_id", "attachment", ["trip_day_id"], unique=False)
    # Non-unique on purpose: the same voucher on two days is two attachments.
    op.create_index("ix_attachment_sha256", "attachment", ["sha256"], unique=False)

    op.create_table(
        "attachment_blob",
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachment.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("attachment_id"),
    )

    op.create_table(
        "upload_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_upload_event_owner_id", "upload_event", ["owner_id"], unique=False)
    op.create_index("ix_upload_event_occurred_at", "upload_event", ["occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_upload_event_occurred_at", table_name="upload_event")
    op.drop_index("ix_upload_event_owner_id", table_name="upload_event")
    op.drop_table("upload_event")

    # Before `attachment`: the blob's foreign key points at it.
    op.drop_table("attachment_blob")

    op.drop_index("ix_attachment_sha256", table_name="attachment")
    op.drop_index("ix_attachment_trip_day_id", table_name="attachment")
    op.drop_index("ix_attachment_item_id", table_name="attachment")
    op.drop_table("attachment")
