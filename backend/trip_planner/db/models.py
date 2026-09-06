"""SQLAlchemy models.

Phase 1 of the walking skeleton: the owner, their sessions, and the login-attempt
log the rate limiter counts. Phase 2 adds the trip, its ordered stages and the
generated days; Phase 3 adds the items that hang off a day.

The attachments slice adds three more: `attachment` (metadata), `attachment_blob`
(the bytes, split off so a listing cannot read them by accident) and
`upload_event` (the upload limiter's storage, shaped after `login_attempt`).
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime, time

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trip_planner.db.base import Base
from trip_planner.domain.uploads import ATTACHMENT_CONTENT_TYPES, MAX_ATTACHMENT_BYTES

__all__ = [
    "ATTACHMENT_CONTENT_TYPES",
    "ITEM_KINDS",
    "ITEM_STATUSES",
    "MAX_ATTACHMENT_BYTES",
    "Attachment",
    "AttachmentBlob",
    "Item",
    "LoginAttempt",
    "Owner",
    "Session",
    "Trip",
    "TripDay",
    "TripStage",
    "UploadEvent",
    "normalise_email",
    "normalise_place",
]

#: The five item types the filter bar's chips are built from.
ITEM_KINDS = ("accommodation", "transport", "activity", "meal", "other")

# `ATTACHMENT_CONTENT_TYPES` and `MAX_ATTACHMENT_BYTES` are defined in
# `domain/uploads.py` — the module that derives a type from an upload's bytes and
# counts them — and re-exported here for the `attachment` `CHECK` constraints
# below. One definition is what keeps "what the sniffer accepts" and "what the
# database can store" a single fact rather than two that drift, and the
# dependency runs `db` → `domain` so the pure module stays free of SQLAlchemy.
# The 10 MiB cap is enforced before the body is read *and* by the constraint, so
# a write path that skips the endpoint still cannot store a larger file.

#: The three statuses R02 and D05 fix, in the order they progress.
#:
#: English identifiers in the database and on the wire; the Polish and English
#: labels are translation keys (R09). Storing a Polish string as the enum value
#: would make the English UI a translation of the database rather than of the
#: product.
ITEM_STATUSES = ("to_plan", "to_book", "done")


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
    items: Mapped[list[Item]] = relationship(
        back_populates="trip_day",
        cascade="all, delete-orphan",
        order_by="Item.position",
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="trip_day",
        cascade="all, delete-orphan",
        order_by="Attachment.created_at",
    )

    def __repr__(self) -> str:
        return f"<TripDay id={self.id!r} date={self.date!r}>"


def _in_list(column: str, values: tuple[str, ...]) -> str:
    """A `CHECK (col IN (...))` clause built from the tuple that defines the values.

    Written from the constant rather than typed out twice so the constraint and
    the application's idea of the allowed values cannot drift apart — which, for
    `status`, would quietly break the readiness arithmetic R02 depends on.
    """
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({rendered})"


class Item(Base):
    """One entry on a day: a hotel, a flight, a museum, a dinner.

    An item belongs to a **day**, never directly to a stage, and the day it
    belongs to is its *start* day. `end_date` and `end_time` give it a span, which
    is in this first migration on purpose: without one, the overnight flight that
    leaves Warsaw at 23:50 and lands in Kuala Lumpur at 14:00 the next day has to
    be split in two, and the two halves then count as **two** entries in the
    readiness arithmetic — the shape of the item would silently change the number
    the whole product exists to show. Adding a second day pointer later to a table
    full of split-in-two flights is a backfill nobody can perform correctly.

    `status` is a CHECK-constrained TEXT column rather than a PostgreSQL ENUM:
    R02 is active until 2026-12-31 and a superseding decision is the documented
    way to change it, so the column that is an ordinary migration to alter is the
    right one. The constraint itself is what makes R02 structural rather than
    conventional — a fourth status cannot be written even by a path that forgets.
    """

    __tablename__ = "item"
    __table_args__ = (
        CheckConstraint(_in_list("kind", ITEM_KINDS), name="ck_item_kind"),
        CheckConstraint(_in_list("status", ITEM_STATUSES), name="ck_item_status"),
        CheckConstraint("position >= 0", name="ck_item_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trip_day_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trip_day.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Assigned server-side as max(position)+1 within the day; the tie-break for
    #: items with no time. Manual reordering is out of scope for this milestone,
    #: so there is no deferrable unique constraint here — unlike `trip_stage`,
    #: nothing renumbers these in bulk.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="to_plan")
    #: Local wall-clock, no timezone (spec, Edge Cases). NULL means "sometime that day".
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    #: NULL means the item ends on its start day.
    end_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    trip_day: Mapped[TripDay] = relationship(back_populates="items")
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="Attachment.created_at",
    )

    def __repr__(self) -> str:
        return f"<Item id={self.id!r} kind={self.kind!r} status={self.status!r}>"


class Attachment(Base):
    """A file pinned to exactly one parent — a day, or an item on that day.

    **One table with two nullable foreign keys**, not two tables and not a
    polymorphic `(parent_type, parent_id)` pair. Two tables would duplicate every
    column, constraint, index and endpoint, and would owe a `UNION` the first time
    anything asks for "this trip's documents". A polymorphic key would buy the
    same single table by giving up referential integrity — no cascade, and a
    dangling parent becomes representable. Two real foreign keys keep the database
    doing the deleting, and the `CHECK` below makes both "no parent" and "two
    parents" states the database will not hold.

    **There is deliberately no `trip_id`.** It would be a convenience for scoping
    and a denormalisation that can drift; the parent chain (`item → trip_day →
    trip`, or `trip_day → trip`) already answers it exactly, and ownership is
    enforced one hop up by `get_owned_trip`. A trip-level attachment, if it is
    ever wanted, arrives as a nullable `trip_id` plus a widened `CHECK` — an
    ordinary additive migration rather than something to guess at now.

    `content_type` is **derived from the bytes**, never copied from the request,
    and the CHECK is what makes that structural: a write path that trusted the
    client's header could still only store one of three types.

    `sha256` is indexed but **not unique** — the same voucher attached to two days
    is two attachments, and refusing the second would be a rule nobody asked for
    (A14 asks only for a hint).
    """

    __tablename__ = "attachment"
    __table_args__ = (
        # Exactly one parent, always. `<>` on two booleans is XOR in PostgreSQL.
        CheckConstraint(
            "(item_id IS NULL) <> (trip_day_id IS NULL)",
            name="ck_attachment_exactly_one_parent",
        ),
        CheckConstraint(
            _in_list("content_type", ATTACHMENT_CONTENT_TYPES),
            name="ck_attachment_content_type",
        ),
        CheckConstraint(
            f"byte_size > 0 AND byte_size <= {MAX_ATTACHMENT_BYTES}",
            name="ck_attachment_byte_size",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("item.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    trip_day_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("trip_day.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    #: The display name only, normalised on write. It never reaches a filesystem,
    #: a path, a shell or a storage key — the primary key is the storage identity.
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    #: The true length of what was stored, counted while reading the body.
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    item: Mapped[Item | None] = relationship(back_populates="attachments")
    trip_day: Mapped[TripDay | None] = relationship(back_populates="attachments")
    blob: Mapped[AttachmentBlob] = relationship(
        back_populates="attachment",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Attachment id={self.id!r} filename={self.filename!r} "
            f"content_type={self.content_type!r}>"
        )


class AttachmentBlob(Base):
    """The file's bytes, in a table of their own.

    Split from the metadata for one reason, and it is not tidiness: with the bytes
    in the same row, rendering a day of six photos would read sixty megabytes to
    display six filenames, and nothing in SQLAlchemy stops an ordinary
    `SELECT`-the-whole-row from doing it. A `deferred()` loader option would be a
    rule that can be forgotten at one call site; a separate table makes the
    mistake unrepresentable. Postgres TOASTs a large `BYTEA` out of line anyway,
    so the split costs no storage.

    The primary key **is** the foreign key: one blob per attachment, enforced by
    the schema rather than by convention. `ON DELETE CASCADE` from `attachment`,
    which cascades from `item` / `trip_day`, which cascade from `trip` — so
    deleting a trip deletes its files transactionally, with no sweeper and no
    eventual consistency to get wrong.
    """

    __tablename__ = "attachment_blob"

    attachment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("attachment.id", ondelete="CASCADE"),
        primary_key=True,
    )
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    attachment: Mapped[Attachment] = relationship(back_populates="blob")

    def __repr__(self) -> str:
        """Excludes `data`: a repr of ten megabytes helps nobody and logs badly."""
        return f"<AttachmentBlob attachment_id={self.attachment_id!r}>"


class UploadEvent(Base):
    """The upload limiter's storage — `LoginAttempt`'s pattern, for an authenticated caller.

    A separate table rather than a widened `login_attempt` because the two are
    keyed on different things: `login_attempt` counts a normalised e-mail and a
    source address for an endpoint with no user yet, this counts an owner who is
    already signed in. Merging them would mean nullable columns on both halves and
    a discriminator to tell them apart, and would change a shipped table's meaning
    to save one `CREATE TABLE`.

    In Postgres rather than process memory for the same reason as there: a
    deployment runs more than one worker, so an in-process counter would be
    decorative. Rows outside the window are deleted on each check; there is still
    no scheduler.

    `byte_size` is carried so the volume window (megabytes per hour) is a `SUM`
    over the same rows the rate window (uploads per ten minutes) counts.
    """

    __tablename__ = "upload_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("owner.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<UploadEvent id={self.id!r} owner_id={self.owner_id!r} at={self.occurred_at!r}>"
