"""Migration round-trip.

Each phase ships one revision with a working `downgrade` (spec, Migrations). The
rollback story in the spec's Risks section is only true if every revision can
actually be reversed, so this walks the whole chain down to base and back up.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _current_revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        if not sa.inspect(engine).has_table("alembic_version"):
            return None
        return connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


def test_upgrade_head_leaves_the_database_at_a_known_revision(
    alembic_config: Config, engine: sa.Engine
) -> None:
    assert _current_revision(engine) is not None


def test_downgrade_to_base_and_back_up_succeeds(alembic_config: Config, engine: sa.Engine) -> None:
    head = _current_revision(engine)

    command.downgrade(alembic_config, "base")
    assert _current_revision(engine) is None

    command.upgrade(alembic_config, "head")
    assert _current_revision(engine) == head


def test_the_attachment_revision_round_trips_on_its_own(
    alembic_config: Config, engine: sa.Engine
) -> None:
    """`0005_attachment` must be reversible without taking the walking skeleton with it.

    The whole-chain test above would still pass if this revision's downgrade
    dropped its tables in an order PostgreSQL refuses, because a chain walked to
    base drops everything anyway. Stepping down exactly one revision and back is
    what proves the phase rolls back alone — which is the reason the reservation
    columns are a separate revision in the first place.
    """
    head = _current_revision(engine)
    inspector = sa.inspect(engine)
    attachment_tables = {"attachment", "attachment_blob", "upload_event"}
    assert attachment_tables <= set(inspector.get_table_names())

    command.downgrade(alembic_config, "0004_item")
    assert _current_revision(engine) == "0004_item"
    remaining = set(sa.inspect(engine).get_table_names())
    assert attachment_tables & remaining == set()
    # The tables the earlier phases created are untouched.
    assert {"owner", "trip", "trip_day", "item"} <= remaining

    command.upgrade(alembic_config, "head")
    assert _current_revision(engine) == head
    assert attachment_tables <= set(sa.inspect(engine).get_table_names())


def test_every_revision_defines_a_downgrade(alembic_config: Config) -> None:
    """A revision whose downgrade is missing breaks the phase-by-phase rollback story."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config)
    revisions = list(script.walk_revisions())
    assert revisions, "expected at least the baseline revision"

    for revision in revisions:
        module = revision.module
        assert hasattr(module, "downgrade"), f"{revision.revision} has no downgrade()"


def test_models_and_migrations_do_not_drift(alembic_config: Config, engine: sa.Engine) -> None:
    """`alembic upgrade head` must produce exactly the schema the models declare.

    Without this, a model edit that nobody wrote a migration for passes every
    other test — the models are used to build the test schema in some projects,
    and the divergence only shows up in production where the migration is the
    only thing that ran.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from trip_planner.db import models  # noqa: F401  (registers the models)
    from trip_planner.db.base import Base

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)

    assert diff == [], (
        "The models and the migrations disagree. Generate a revision for this diff:\n"
        + "\n".join(repr(entry) for entry in diff)
    )


def test_the_reservation_revision_round_trips_over_existing_rows(
    alembic_config: Config, engine: sa.Engine
) -> None:
    """`0006_item_reservation` must unwind without taking attachments with it.

    This is the reason the reservation columns are a second revision rather than
    part of `0005_attachment` (A1), and the only way to prove it is to step down
    exactly one revision on a database that is **not** empty: an owner, a trip, a
    day, an item and an attachment, all committed, exactly as a real installation
    would have them when an operator rolls Phase 3 back at 02:00.

    What must survive the round trip: every one of those rows, and the attachment
    tables themselves. What must not: the three `item` columns, which are dropped
    with the data in them — which is what downgrading a feature migration means.
    """
    head = _current_revision(engine)
    owner_id, item_id = uuid.uuid4(), uuid.uuid4()

    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO owner (id, email, password_hash) "
                    "VALUES (:id, :email, 'x')"
                ),
                {"id": owner_id, "email": f"rollback-{owner_id.hex}@example.com"},
            )
            trip_id, day_id, attachment_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO trip (id, owner_id, title, start_date, end_date, "
                    "departure_place, return_place) VALUES (:id, :owner_id, 'Malezja', "
                    "'2026-10-10', '2026-10-24', 'Warszawa', 'Katowice')"
                ),
                {"id": trip_id, "owner_id": owner_id},
            )
            connection.execute(
                sa.text("INSERT INTO trip_day (id, trip_id, date) VALUES (:id, :trip_id, :date)"),
                {"id": day_id, "trip_id": trip_id, "date": date(2026, 10, 10)},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO item (id, trip_day_id, position, kind, status, title, "
                    "confirmation_number, cost_amount, cost_currency) "
                    "VALUES (:id, :day_id, 0, 'accommodation', 'to_book', 'Memmo Alfama', "
                    "'SX-9912L', 249.00, 'PLN')"
                ),
                {"id": item_id, "day_id": day_id},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO attachment (id, item_id, filename, content_type, byte_size, "
                    "sha256) VALUES (:id, :item_id, 'voucher.pdf', 'application/pdf', 2048, :sha)"
                ),
                {"id": attachment_id, "item_id": item_id, "sha": "a" * 64},
            )

        command.downgrade(alembic_config, "0005_attachment")
        assert _current_revision(engine) == "0005_attachment"

        columns = {column["name"] for column in sa.inspect(engine).get_columns("item")}
        assert columns & {"confirmation_number", "cost_amount", "cost_currency"} == set()
        # The attachment phase is untouched by the reservation phase's rollback.
        assert {"attachment", "attachment_blob", "upload_event"} <= set(
            sa.inspect(engine).get_table_names()
        )

        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT count(*) FROM attachment WHERE id = :id"),
                {"id": attachment_id},
            ).scalar() == 1
            assert connection.execute(
                sa.text("SELECT title FROM item WHERE id = :id"), {"id": item_id}
            ).scalar() == "Memmo Alfama"

        command.upgrade(alembic_config, "head")
        assert _current_revision(engine) == head

        with engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    "SELECT confirmation_number, cost_amount, cost_currency "
                    "FROM item WHERE id = :id"
                ),
                {"id": item_id},
            ).one()
        # The item survived; its reservation data did not, and the columns come
        # back nullable so the row is valid without a backfill.
        assert row == (None, None, None)
    finally:
        with engine.begin() as connection:
            connection.execute(
                sa.text("DELETE FROM owner WHERE id = :id"), {"id": owner_id}
            )
