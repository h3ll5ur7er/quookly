"""The async engine and session over the configured datastore.

SQLite only at v1 ([ADR-009]). SQLModel and SQLAlchemy types stay inside this layer;
what crosses upward belongs to `quookly.contracts` ([ADR-018]). That boundary is what
keeps the datastore swappable, and it is enforced by import-linter rather than by
discipline.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.utilities.configuration import get_settings


def _is_in_memory(url: str) -> bool:
    return url.startswith("sqlite") and (url.endswith("://") or ":memory:" in url)


def _engine_options(url: str) -> dict[str, Any]:
    """Options the URL implies.

    Each connection to an in-memory SQLite database gets a database of its own, so a
    pool that hands out fresh connections loses the schema between uses. A static pool
    keeps every caller on the one connection, which is what makes in-memory usable.
    """
    if _is_in_memory(url):
        return {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
    return {}


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """The process-wide engine. Connection pools are expensive; one is enough."""
    url = get_settings().database_url
    return create_async_engine(url, **_engine_options(url))


async def dispose_engine() -> None:
    """Close pooled connections. Called on shutdown, and between tests."""
    if get_engine.cache_info().currsize:
        await get_engine().dispose()


@asynccontextmanager
async def session() -> AsyncIterator[AsyncSession]:
    """A unit of work.

    Committing is the caller's decision — a resource access service knows whether its
    verb completed. What this guarantees is that an exception rolls back rather than
    leaving a half-written transaction behind.
    """
    factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    async with factory() as active:
        try:
            yield active
        except Exception:
            await active.rollback()
            raise
