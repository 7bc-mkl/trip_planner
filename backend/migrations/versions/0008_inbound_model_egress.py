"""inbound_model_egress and routing_reason_args

Revision ID: 0008_inbound_model_egress
Revises: 0007_inbound_message
Create Date: 2026-10-11

Phase 2 of the reservation inbox: the audit trail for every outbound model call,
and the column that lets a routing reason carry its arguments.

One new table plus one new nullable column, so "safe against rows that already
exist" is satisfied trivially — every existing `inbound_message` row is valid
with `routing_reason_args` null, which is exactly what a Phase 1 row means:
a reason with no arguments. No backfill, no default, no rewrite.

`routing_reason_args` is here rather than in its own revision because it belongs
to this phase: a Phase 1 reason (`placed_by_hand`) needs no arguments, and the
reasons that do — *"no trip covers 4–11 October"* — only exist once routing
does. The downgrade drops it, which loses the arguments while leaving every
reason key intact, so the screen degrades to the unparameterised sentence
rather than to nothing.

That clean reversibility is why the spec made Phase 2 its own revision:
**rolling back returns the deployment to a manual inbox** — the messages, their
documents and the `/inbox` screen are all Phase 1 and survive untouched.

What the downgrade *does* destroy is the record of which provider saw what.
Written down here rather than discovered later: if that history matters to the
owner, it wants exporting before the rollback, because nothing else in the
system holds it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_inbound_model_egress"
down_revision: str | None = "0007_inbound_message"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Literals rather than imports from `db.models`, for the reason revision 0007
#: gives: a migration describes the schema *at this revision*, and importing
#: today's constant would make an old revision change meaning when someone adds
#: a provider.
_KINDS = ("text", "document")
_PROVIDERS = ("anthropic", "gemini", "openai")


def upgrade() -> None:
    op.add_column(
        "inbound_message",
        sa.Column("routing_reason_args", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "inbound_model_egress",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_message_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("attachment_name", sa.Text(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{kind}'" for kind in _KINDS) + ")",
            name="ck_model_egress_kind",
        ),
        sa.CheckConstraint(
            "provider IN (" + ", ".join(f"'{one}'" for one in _PROVIDERS) + ")",
            name="ck_model_egress_provider",
        ),
        sa.CheckConstraint(
            "kind <> 'document' OR attachment_id IS NOT NULL OR attachment_name IS NOT NULL",
            name="ck_model_egress_document_names_its_file",
        ),
        # CASCADE from the message: deleting a message takes its audit rows,
        # which is A10 — his mail is his data, including the record of it.
        sa.ForeignKeyConstraint(
            ["inbound_message_id"], ["inbound_message.id"], ondelete="CASCADE"
        ),
        # SET NULL from the attachment, **not** CASCADE: deleting a document
        # must not erase the fact that it was sent somewhere.
        sa.ForeignKeyConstraint(["attachment_id"], ["attachment.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inbound_model_egress_inbound_message_id",
        "inbound_model_egress",
        ["inbound_message_id"],
        unique=False,
    )
    # The budget sums a billing month's rows before every call, so this index is
    # on the read path rather than a nicety.
    op.create_index(
        "ix_inbound_model_egress_attempted_at",
        "inbound_model_egress",
        ["attempted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_column("inbound_message", "routing_reason_args")

    op.drop_index("ix_inbound_model_egress_attempted_at", table_name="inbound_model_egress")
    op.drop_index(
        "ix_inbound_model_egress_inbound_message_id", table_name="inbound_model_egress"
    )
    op.drop_table("inbound_model_egress")
