"""Alembic environment.

The database URL comes from the Configuration utility rather than alembic.ini, so an
instance is configured in exactly one place. Metadata comes from SQLModel, so
autogenerate sees the same tables the application does.
"""

import asyncio

from alembic.runtime.environment import NameFilterParentNames, NameFilterType
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context
from quookly.access.models import hand_managed
from quookly.utilities.configuration import get_settings
from quookly.utilities.diagnostics import configure_logging

config = context.config

# Logging is configured by the application's own utility rather than from alembic.ini.
# `fileConfig` disables every existing logger by default, which silences the application
# whenever migrations run in the same process.
configure_logging()

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = SQLModel.metadata


def _worth_autogenerating(
    name: str | None, kind: NameFilterType, parent_names: NameFilterParentNames
) -> bool:
    """Whether autogenerate should have an opinion about this object.

    The search index is a virtual table and its shadow tables are FTS5's own bookkeeping.
    None of them are in the metadata, so without this every migration would offer to drop
    the lot — a trap that goes off later, quietly, in production.
    """
    return not (kind == "table" and hand_managed(name))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_name=_worth_autogenerating,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # SQLite cannot ALTER most things in place; batch mode rewrites the table instead.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=_worth_autogenerating,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
