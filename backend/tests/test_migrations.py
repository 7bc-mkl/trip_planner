"""Migration round-trip.

Each phase ships one revision with a working `downgrade` (spec, Migrations). The
rollback story in the spec's Risks section is only true if every revision can
actually be reversed, so this walks the whole chain down to base and back up.
"""

from __future__ import annotations

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


def test_every_revision_defines_a_downgrade(alembic_config: Config) -> None:
    """A revision whose downgrade is missing breaks the phase-by-phase rollback story."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config)
    revisions = list(script.walk_revisions())
    assert revisions, "expected at least the baseline revision"

    for revision in revisions:
        module = revision.module
        assert hasattr(module, "downgrade"), f"{revision.revision} has no downgrade()"
