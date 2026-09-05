"""SQLAlchemy models.

Phase 1 of the walking skeleton: the owner, their sessions, and the login-attempt
log the rate limiter counts. The trip tables arrive in Phase 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trip_planner.db.base import Base

__all__ = ["LoginAttempt", "Owner", "Session", "normalise_email"]


def normalise_email(email: str) -> str:
    """The one normalisation, applied on write and on lookup alike.

    Both paths must agree or a lower-case login would miss a mixed-case row.
    """
    return email.strip().lower()


class Owner(Base):
    """The single owner account (D15).

    A real table with a real primary key even though there is exactly one user:
    the password hash needs somewhere to live, and a singleton row in a
    properly-shaped table does not have to be migrated if D15 is ever revisited.
    There is deliberately no registration, no roles and no password reset.
    """

    __tablename__ = "owner"
    __table_args__ = (
        CheckConstraint("locale IN ('pl', 'en')", name="ck_owner_locale"),
        UniqueConstraint("email", name="uq_owner_email"),
        # Belt-and-braces beside the plain UNIQUE on the stored value: the column
        # is normalised on write, and this makes a mixed-case duplicate
        # impossible even if some future write path forgets to normalise.
        Index("uq_owner_email_lower", text("lower(email)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(2), nullable=False, server_default="pl")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list[Session]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Deliberately excludes password_hash so it cannot reach a log line."""
        return f"<Owner id={self.id!r} email={self.email!r}>"


class Session(Base):
    """An opaque server-side session.

    The table exists rather than a JWT because logout must genuinely revoke
    (spec A8). Only the SHA-256 of the token is stored: the token itself lives in
    the cookie, so a database dump does not yield a usable session.
    """

    __tablename__ = "session"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_session_token_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("owner.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    owner: Mapped[Owner] = relationship(back_populates="sessions")

    def __repr__(self) -> str:
        """Excludes token_hash: it is the secret's only stored form."""
        return f"<Session id={self.id!r} owner_id={self.owner_id!r} expires_at={self.expires_at!r}>"


class LoginAttempt(Base):
    """The rate limiter's storage.

    In Postgres rather than a process-local dictionary because a public
    deployment runs more than one worker and an in-process counter would be
    decorative. Rows older than the window are deleted on each check; there is no
    scheduler in this milestone.
    """

    __tablename__ = "login_attempt"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email_normalised: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    source_ip: Mapped[str] = mapped_column(INET, nullable=False, index=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<LoginAttempt id={self.id!r} at={self.attempted_at!r}>"
