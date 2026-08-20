"""Database plumbing: an async engine and session over SQLite (ADR-009, ADR-018).

These tests exercise the connection machinery through the ORM path that resource access
services will actually use, against a real table rather than a fixture one — a
test-only model would register in SQLModel's metadata and drift from the migrations.
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel, select

from quookly.access.database import dispose_engine, get_engine, session
from quookly.access.models import CookRow
from quookly.contracts.measure import Unit
from quookly.contracts.recipe import Provenance
from quookly.utilities.configuration import get_settings

IN_MEMORY = "sqlite+aiosqlite://"


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
            active.add(CookRow(email="a@example.com", display_name="A", password_hash="x"))
            await active.commit()

        async with session() as active:
            found = (await active.exec(select(CookRow))).all()
        assert [row.email for row in found] == ["a@example.com"]

    async def test_the_unit_of_work_ends_with_the_block(self) -> None:
        """A session left holding a transaction pins a connection and blocks writers."""
        async with session() as active:
            await active.exec(select(CookRow))
            assert active.in_transaction()
        assert not active.in_transaction()

    async def test_a_failing_block_does_not_commit(self) -> None:
        """An exception must roll back rather than leave a half-written transaction."""
        with pytest.raises(RuntimeError):
            async with session() as active:
                active.add(
                    CookRow(email="ghost@example.com", display_name="Ghost", password_hash="x")
                )
                await active.flush()
                raise RuntimeError("deliberate failure")

        async with session() as active:
            survivors = (await active.exec(select(CookRow))).all()
        assert survivors == [], "the failed block left rows behind"


class TestReferentialIntegrity:
    async def test_a_reference_to_something_absent_is_refused(self) -> None:
        """SQLite does not enforce foreign keys unless asked, and silence here is the
        worst outcome: a row that points nowhere is accepted, and the thing it belonged
        to quietly disappears on read."""
        from sqlalchemy.exc import IntegrityError

        from quookly.access.models import RecipeRow

        with pytest.raises(IntegrityError):
            async with session() as active:
                active.add(
                    RecipeRow(
                        cook_id=9999,
                        title="Orphan",
                        yield_magnitude=1,
                        yield_unit=Unit.PIECE,
                        provenance=Provenance.AUTHORED,
                    )
                )
                await active.commit()
