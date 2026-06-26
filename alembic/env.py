"""
alembic/env.py — Alembic environment configuration.

Reads the database URL from the DATABASE_URL environment variable.
Uses create_engine() for Alembic's internal migration runner — this is
unavoidable and is the standard Alembic pattern.

No SQLAlchemy ORM models are used. target_metadata is None.

No locking is performed here, and Alembic has no built-in guard against
concurrent migrations — this file does not add one either. This is only
safe as long as a single web service instance runs migrations at a time;
if the web service is ever scaled to multiple replicas, or two deploys
briefly overlap, two instances could run `alembic upgrade head` against
the same database concurrently with no protection. Flagged here as an
open risk, not a verified-safe pattern.
"""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Set up Python logging from the .ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# No SQLAlchemy ORM models — metadata is None.
target_metadata = None

# ---------------------------------------------------------------------------
# Override the sqlalchemy.url from the environment.
# ---------------------------------------------------------------------------

database_url = os.environ.get("DATABASE_URL")
if not database_url or not database_url.strip():
    raise RuntimeError("DATABASE_URL environment variable is not set")

config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — connects to the database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
