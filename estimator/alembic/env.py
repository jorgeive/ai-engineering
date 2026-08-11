"""Alembic migration environment for the Session 6 persistence layer.

The DB URL is read from ``app.config.Settings`` (not from alembic.ini) so the
container, the dev host and CI all use the same source of truth. Migrations are
discovered by importing ``app.foundation.persistence.models``: every SQLAlchemy model in
that module is registered against ``Base.metadata`` and becomes visible to
Alembic's autogenerate.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
import pgvector.sqlalchemy
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.foundation.persistence.models import Base  # noqa: F401 — ensure models are imported
import app.generation.rag.store.models  # noqa: F401 — register Session 8 tables

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL.replace("+psycopg", "+asyncpg"))

target_metadata = Base.metadata


def do_run_migrations(connection) -> None:
    """Run migrations synchronously within an async SQLAlchemy connection."""
    connection.dialect.ischema_names["vector"] = pgvector.sqlalchemy.Vector
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Generate SQL without a live connection — used by ``alembic upgrade --sql``."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Apply migrations against a live async database connection."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run the async migration environment from Alembic's sync entrypoint."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
