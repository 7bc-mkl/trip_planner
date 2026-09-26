"""Alembic environment.

The connection string comes from `trip_planner.config`, never from alembic.ini,
so there is one resolution path and no credential in a committed file.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from trip_planner.config import require_settings
from trip_planner.db import models  # noqa: F401  (imported for its side effect: model registration)
from trip_planner.db.base import Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False` is not a preference. `fileConfig`'s
    # default is `True`, which switches off **every logger that already
    # exists** — so running a migration in the same process as the application
    # silently disables `trip_planner.*` logging for the rest of that process's
    # life. The test suite migrates at session start, which made every
    # application log line vanish for the whole run and any assertion about one
    # fail for a reason nothing in it mentions.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return require_settings().sqlalchemy_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
