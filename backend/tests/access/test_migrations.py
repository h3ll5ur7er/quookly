"""Migrations are the schema of record.

The instance a self-hoster runs is built by migrations, not by `create_all`. If the
models and the migrations disagree, the tests pass against a schema nobody will ever
have — so the drift check below is the point of this file.

These tests are deliberately synchronous: Alembic's async env runs its own event loop.
"""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from alembic import command
from quookly.access.database import get_engine
from quookly.access.models import hand_managed
from quookly.utilities.configuration import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def migrated_database(tmp_path: Path, monkeypatch: MonkeyPatch) -> Path:
    """A fresh database built the way a real instance is built: by upgrading."""
    database = tmp_path / "quookly.db"
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    get_settings.cache_clear()
    get_engine.cache_clear()
    return database


def _about_the_search_index(difference: object) -> bool:
    return isinstance(difference, tuple) and hand_managed(getattr(difference[1], "name", None))


class TestMigrations:
    def test_upgrading_a_fresh_database_creates_the_schema(self, migrated_database: Path) -> None:
        engine = create_engine(f"sqlite:///{migrated_database}")
        try:
            assert "cook" in inspect(engine).get_table_names()
        finally:
            engine.dispose()

    def test_the_models_and_the_migrations_agree(self, migrated_database: Path) -> None:
        """A model changed without a migration is a schema that only exists in tests."""
        engine = create_engine(f"sqlite:///{migrated_database}")
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(connection)
                differences = [
                    difference
                    for difference in compare_metadata(context, SQLModel.metadata)
                    # The search index and FTS5's shadow tables are hand-managed, and
                    # autogenerate would offer to drop them on every future migration.
                    if not _about_the_search_index(difference)
                ]
        finally:
            engine.dispose()
        assert differences == [], (
            f"the models and the migrations have drifted; generate a migration:\n{differences}"
        )
