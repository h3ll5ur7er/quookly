"""Database plumbing: an async engine and session over SQLite (ADR-009, ADR-018).

These tests exercise the connection machinery through the ORM path that resource access
services will actually use. Domain tables arrive with the services that own them; the
table here is a throwaway standing in for one.
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import Field, SQLModel, select

from quookly.access.database import dispose_engine, get_engine, session
from quookly.utilities.configuration import get_settings

IN_MEMORY = "sqlite+aiosqlite://"


class StockProbe(SQLModel, table=True):
    """Stand-in for a real table, so the plumbing is tested the way it will be used."""

    __tablename__ = "stock_probe"

    id: int | None = Field(default=None, primary_key=True)
    label: str


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    """Never let a test touch the developer's database file."""
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", IN_MEMORY)
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


class TestEngine:
    def test_the_engine_uses_the_configured_url(self) -> None:
        assert get_engine().url.render_as_string() == IN_MEMORY

    def test_the_engine_is_created_once(self) -> None:
        """Connection pools are expensive; one engine per process."""
        assert get_engine() is get_engine()

    def test_the_engine_is_async(self) -> None:
        """Blocking the event loop on database I/O would defeat the point of async routes."""
        from sqlalchemy.ext.asyncio import AsyncEngine

        assert isinstance(get_engine(), AsyncEngine)


class TestSession:
    async def test_a_session_reads_what_it_wrote(self) -> None:
        async with session() as active:
            active.add(StockProbe(label="butter"))
            await active.commit()

        async with session() as active:
            found = (await active.exec(select(StockProbe))).all()
        assert [probe.label for probe in found] == ["butter"]

    async def test_the_unit_of_work_ends_with_the_block(self) -> None:
        """A session left holding a transaction pins a connection and blocks writers."""
        async with session() as active:
            await active.exec(select(StockProbe))
            assert active.in_transaction()
        assert not active.in_transaction()

    async def test_a_failing_block_does_not_commit(self) -> None:
        """An exception must roll back rather than leave a half-written transaction."""
        with pytest.raises(RuntimeError):
            async with session() as active:
                active.add(StockProbe(label="never-written"))
                await active.flush()
                raise RuntimeError("deliberate failure")

        async with session() as active:
            survivors = (await active.exec(select(StockProbe))).all()
        assert survivors == [], "the failed block left rows behind"
