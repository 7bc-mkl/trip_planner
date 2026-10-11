"""inbound_message

Revision ID: 0007_inbound_message
Revises: 0006_item_reservation
Create Date: 2026-09-26

Phase 1 of the reservation inbox: three tables that did not exist, plus the one
change this revision makes to a **shipped** table.

Three of the four changes are ordinary. `inbound_message`,
`inbound_delivery_status` and `inbound_trusted_sender` are new, so "safe against
rows that already exist" is vacuous for them (BACKWARD_COMPATIBILITY.md §2) and
their downgrade is a clean drop.

**The fourth is the one to read carefully.** `attachment` gains a third nullable
parent, `inbound_message_id`, and its `CHECK` is replaced:

    -- was
    CHECK ((item_id IS NULL) <> (trip_day_id IS NULL))
    -- is
    CHECK (num_nonnulls(item_id, trip_day_id, inbound_message_id) = 1)

This is a **widening**, in the strongest sense §2 asks for: every row that
satisfied the old constraint satisfies the new one, because a row with exactly
one of two columns non-null still has exactly one of three non-null. There is no
backfill, no default, no table rewrite and no window in which existing data is
invalid. The old invariant does not regress either — `num_nonnulls(...) = 1` is
still *exactly one parent*, so zero parents and two parents remain states the
database will not hold, and the shipped tests asserting both keep passing.

**The downgrade refuses rather than deletes.** Narrowing back to two parents
would make every inbox document a row the constraint rejects, and the only way
to "fix" that automatically is to delete the documents — silently destroying a
voucher during a rollback, which is precisely the failure mode a downgrade must
not have. So it raises instead, naming what is in the way and what to do about
it, and the operator decides. `tests/test_migrations.py` asserts that refusal;
it is a behaviour of this revision, not a nicety.

`attachment.sent_externally_at` ships here as well, though **nothing in Phase 1
writes it**: it is a property of the document rather than of the model
integration, and adding it now costs one nullable column instead of a second
migration over a table full of inbox documents later.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_inbound_message"
down_revision: str | None = "0006_item_reservation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Kept as a literal rather than imported from `db.models`. A migration has to
#: describe the schema *at this revision*, and importing today's constant would
#: make an old revision silently change meaning the day someone adds a state.
_STATES = (
    "pending_ingest",
    "received",
    "deferred",
    "routed",
    "unrouted",
    "quarantined",
    "discarded",
)


class InboxAttachmentsRemain(RuntimeError):
    """Raised by `downgrade` rather than deleting documents. See the module docstring."""


def upgrade() -> None:
    op.create_table(
        "inbound_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ses_message_id", sa.Text(), nullable=False),
        sa.Column("s3_object_key", sa.Text(), nullable=True),
        sa.Column("ses_sender_verdict", sa.Text(), nullable=False),
        sa.Column("ses_scan_verdict", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_address", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("text_body", sa.Text(), server_default="", nullable=False),
        sa.Column("state", sa.Text(), server_default="pending_ingest", nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("routing_reason", sa.Text(), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("text_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_inbound_message_attempts"),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{state}'" for state in _STATES) + ")",
            name="ck_inbound_message_state",
        ),
        sa.CheckConstraint("length(subject) <= 1000", name="ck_inbound_message_subject"),
        sa.CheckConstraint("length(text_body) <= 200000", name="ck_inbound_message_text_body"),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        # SET NULL, not CASCADE: deleting a trip returns its mail to the
        # unrouted queue rather than destroying it. See the model docstring.
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "ses_message_id", name="uq_inbound_message_ses_id"),
    )
    op.create_index("ix_inbound_message_owner_id", "inbound_message", ["owner_id"], unique=False)
    op.create_index(
        "ix_inbound_message_received_at", "inbound_message", ["received_at"], unique=False
    )
    op.create_index("ix_inbound_message_trip_id", "inbound_message", ["trip_id"], unique=False)

    op.create_table(
        "inbound_delivery_status",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id"),
    )

    op.create_table(
        "inbound_trusted_sender",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id", "address"),
    )

    # --- the shipped table -------------------------------------------------
    op.add_column(
        "attachment",
        sa.Column("inbound_message_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "attachment", sa.Column("sent_externally_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_attachment_inbound_message_id", "attachment", ["inbound_message_id"], unique=False
    )
    op.create_foreign_key(
        "fk_attachment_inbound_message_id",
        "attachment",
        "inbound_message",
        ["inbound_message_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Drop then create, in that order and in one transaction: PostgreSQL runs
    # DDL transactionally, so no window exists in which the table has *no*
    # one-parent rule. A widening cannot fail its own validation pass either —
    # every existing row already satisfies the new constraint — so this does not
    # need NOT VALID plus a later VALIDATE.
    op.drop_constraint("ck_attachment_exactly_one_parent", "attachment", type_="check")
    op.create_check_constraint(
        "ck_attachment_exactly_one_parent",
        "attachment",
        "num_nonnulls(item_id, trip_day_id, inbound_message_id) = 1",
    )


def downgrade() -> None:
    """Narrow back to two parents, or **refuse**. Never delete a document.

    The refusal is the interesting half. An operator rolling this revision back
    on a database holding inbox documents is asking for those rows to become
    invalid under the narrower constraint, and the only automatic resolution is
    to delete them — a voucher destroyed by a rollback nobody thought was
    destructive. So the migration stops and says exactly what is in the way.
    """
    remaining = op.get_bind().execute(
        sa.text("SELECT count(*) FROM attachment WHERE inbound_message_id IS NOT NULL")
    ).scalar_one()

    if remaining:
        raise InboxAttachmentsRemain(
            f"Refusing to downgrade: {remaining} attachment(s) are still parented to an "
            "inbound message, and narrowing the parent CHECK would make them invalid. "
            "Approve or delete the affected inbox messages first — this migration will "
            "not delete a document to make room for itself."
        )

    op.drop_constraint("ck_attachment_exactly_one_parent", "attachment", type_="check")
    op.create_check_constraint(
        "ck_attachment_exactly_one_parent",
        "attachment",
        "(item_id IS NULL) <> (trip_day_id IS NULL)",
    )

    op.drop_constraint("fk_attachment_inbound_message_id", "attachment", type_="foreignkey")
    op.drop_index("ix_attachment_inbound_message_id", table_name="attachment")
    op.drop_column("attachment", "sent_externally_at")
    op.drop_column("attachment", "inbound_message_id")

    op.drop_table("inbound_trusted_sender")
    op.drop_table("inbound_delivery_status")

    op.drop_index("ix_inbound_message_trip_id", table_name="inbound_message")
    op.drop_index("ix_inbound_message_received_at", table_name="inbound_message")
    op.drop_index("ix_inbound_message_owner_id", table_name="inbound_message")
    op.drop_table("inbound_message")
