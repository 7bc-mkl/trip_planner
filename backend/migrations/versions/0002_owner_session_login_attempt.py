"""owner, session and login_attempt

Revision ID: 0002_owner_session_login_attempt
Revises: 0001_baseline
Create Date: 2026-09-05

Phase 1 of the walking skeleton. Creates three tables that did not exist, so the
"safe against rows that already exist" rule in BACKWARD_COMPATIBILITY.md is
vacuous here, and the downgrade is a clean drop.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_owner_session_login_attempt"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(length=2), server_default="pl", nullable=False),
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
        sa.CheckConstraint("locale IN ('pl', 'en')", name="ck_owner_locale"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_owner_email"),
    )
    # The functional index is the belt-and-braces guard beside the plain UNIQUE:
    # the application normalises on write, and this makes a mixed-case duplicate
    # impossible even if some future write path forgets to.
    op.create_index(
        "uq_owner_email_lower", "owner", [sa.literal_column("lower(email)")], unique=True
    )

    op.create_table(
        "session",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["owner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_session_token_hash"),
    )
    op.create_index("ix_session_owner_id", "session", ["owner_id"], unique=False)

    op.create_table(
        "login_attempt",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("email_normalised", sa.Text(), nullable=False),
        sa.Column("source_ip", postgresql.INET(), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_login_attempt_attempted_at", "login_attempt", ["attempted_at"], unique=False
    )
    op.create_index(
        "ix_login_attempt_email_normalised", "login_attempt", ["email_normalised"], unique=False
    )
    op.create_index("ix_login_attempt_source_ip", "login_attempt", ["source_ip"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_login_attempt_source_ip", table_name="login_attempt")
    op.drop_index("ix_login_attempt_email_normalised", table_name="login_attempt")
    op.drop_index("ix_login_attempt_attempted_at", table_name="login_attempt")
    op.drop_table("login_attempt")

    op.drop_index("ix_session_owner_id", table_name="session")
    op.drop_table("session")

    op.drop_index("uq_owner_email_lower", table_name="owner")
    op.drop_table("owner")
