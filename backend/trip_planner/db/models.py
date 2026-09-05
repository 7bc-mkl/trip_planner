"""SQLAlchemy models.

Phase 1 of the walking skeleton: the owner, their sessions, and the login-attempt
log the rate limiter counts. Phase 2 adds the trip, its ordered stages and the
generated days; Phase 3 adds the items that hang off a day.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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

__all__ = [
    "LoginAttempt",
    "Owner",
    "Session",
    "Trip",
    "TripDay",
    "TripStage",
    "normalise_email",
    "normalise_place",
]


def normalise_place(place: str) -> str:
    """The comparison form for a free-text place.

    The route mode is *derived* by comparing `departure_place` with `return_place`
    (spec, Data Model), so the comparison has to be stable against the differences
    a human types: leading and trailing space, and case. `"Warszawa"` and
    `"Warszawa "` are the same city and must not read as an open-jaw trip.

    Only the comparison is normalised — what is stored is what the owner typed,
    because the trip header shows it back to them.
    """
    return " ".join(place.split()).casefold()


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
    trips: Mapped[list[Trip]] = relationship(
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


class Trip(Base):
    """A trip: a title, an inclusive date range, and where it leaves from and returns to.

    The open-jaw question (R03, D06) is answered by two nullable-aware text columns
    rather than by structure — there is no discriminator column, because the three
    route modes fall out of `return_place` alone:

    - `NULL`                              → one-way, the trip does not return
    - equal to `departure_place`          → round trip
    - different from `departure_place`    → open-jaw

    Comparison is on the normalised form (`normalise_place`), and `PATCH` rewrites
    `return_place` when a round trip's `departure_place` is edited, so correcting a
    typo cannot silently convert the trip into an open-jaw one.

    Places are free text rather than references to a places table: D04 rules out
    live lookups, so a structured place entity would be a guess about a schema we
    cannot populate. Adding a nullable `departure_place_id` beside the text later
    is an addition; inventing the wrong entity now would be a migration.
    """

    __tablename__ = "trip"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_trip_date_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("owner.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    departure_place: Mapped[str] = mapped_column(Text, nullable=False)
    return_place: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    owner: Mapped[Owner] = relationship(back_populates="trips")
    stages: Mapped[list[TripStage]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripStage.position",
    )
    days: Mapped[list[TripDay]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="TripDay.date",
    )

    @property
    def is_round_trip(self) -> bool:
        """True when the trip returns to where it departed from.

        Used by the mode-stability rule on `PATCH`; the frontend derives the same
        three modes from the same two fields, so neither side stores the answer.
        """
        return self.return_place is not None and normalise_place(
            self.return_place
        ) == normalise_place(self.departure_place)

    def __repr__(self) -> str:
        return f"<Trip id={self.id!r} title={self.title!r} {self.start_date}..{self.end_date}>"


class TripStage(Base):
    """A base (etap) of a multi-stop trip: a place, in order, optionally with dates.

    A trip has one or more stages (R03). Dates are **nullable** because R03 asks the
    creation form for the trip's dates, not a range per stage: a traveller who knows
    "Kuala Lumpur, Penang, Langkawi" but has not decided how to split fourteen days
    must still be able to create the trip. A stage with no dates labels no day.

    There is deliberately **no non-overlap constraint**. Stages may share boundary
    dates — the day two stages both contain is the travel day between them — so a
    day resolves to any number of stages, ordered by `position`.

    `UNIQUE (trip_id, position)` is `DEFERRABLE INITIALLY DEFERRED` so that the
    dense-reassignment statement after a delete from the middle can renumber every
    later stage in one `UPDATE` without transiently colliding.
    """

    __tablename__ = "trip_stage"
    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_trip_stage_date_range",
        ),
        CheckConstraint("position >= 0", name="ck_trip_stage_position"),
        UniqueConstraint(
            "trip_id",
            "position",
            name="uq_trip_stage_position",
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trip.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    place: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    trip: Mapped[Trip] = relationship(back_populates="stages")

    def __repr__(self) -> str:
        return f"<TripStage id={self.id!r} position={self.position!r} place={self.place!r}>"


class TripDay(Base):
    """One calendar date of a trip, generated when the trip is created.

    Generating these rows *is* the "create an empty timeline" action the creator's
    primary button performs.

    **`trip_day` deliberately carries no `stage_id`.** The stage or stages covering a
    day are derived by date containment in `domain/stages.py`, because a stored
    foreign key would have to be re-maintained on every stage date edit and could
    silently contradict the stage's own dates — the "changing what it means while
    keeping its name" failure BACKWARD_COMPATIBILITY.md calls the worst kind.
    Derivation is a pure function that cannot drift; denormalising later, if query
    cost ever justifies it, is an addition.
    """

    __tablename__ = "trip_day"
    __table_args__ = (UniqueConstraint("trip_id", "date", name="uq_trip_day_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trip.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    trip: Mapped[Trip] = relationship(back_populates="days")

    def __repr__(self) -> str:
        return f"<TripDay id={self.id!r} date={self.date!r}>"
