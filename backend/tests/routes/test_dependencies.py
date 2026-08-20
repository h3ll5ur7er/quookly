"""Resolving who is asking.

A route that cannot identify the caller must refuse, not guess. These are the cases a
public endpoint actually receives: no header, a malformed one, a forged token, an expired
one.
"""

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.utilities.configuration import get_settings
from quookly.utilities.security import issue_token

SIGNING_KEY = "a-test-signing-key-of-sufficient-length-01"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", SIGNING_KEY)
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


PROTECTED = "/api/v1/recipes"


class TestRefusing:
    async def test_no_token_is_unauthorised(self, client: AsyncClient) -> None:
        assert (await client.get(PROTECTED)).status_code == 401

    async def test_a_malformed_header_is_unauthorised(self, client: AsyncClient) -> None:
        response = await client.get(PROTECTED, headers={"Authorization": "Basic hunter2"})
        assert response.status_code == 401

    async def test_rubbish_instead_of_a_token_is_unauthorised(self, client: AsyncClient) -> None:
        response = await client.get(PROTECTED, headers={"Authorization": "Bearer nonsense"})
        assert response.status_code == 401

    async def test_an_expired_token_is_unauthorised(self, client: AsyncClient) -> None:
        stale = issue_token(cook_id=1, is_admin=False, lifetime=timedelta(seconds=-1))
        response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {stale}"})
        assert response.status_code == 401

    async def test_a_token_signed_by_someone_else_is_unauthorised(
        self, client: AsyncClient, monkeypatch: MonkeyPatch
    ) -> None:
        foreign = issue_token(cook_id=1, is_admin=False)
        monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-completely-different-key-long-enough-01")
        get_settings.cache_clear()
        response = await client.get(PROTECTED, headers={"Authorization": f"Bearer {foreign}"})
        assert response.status_code == 401

    async def test_the_refusal_says_how_to_authenticate(self, client: AsyncClient) -> None:
        """A 401 without a challenge leaves a client guessing."""
        response = await client.get(PROTECTED)
        assert response.headers.get("www-authenticate") == "Bearer"


class TestAccepting:
    async def test_a_valid_token_gets_through(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/accounts",
            json={
                "email": "chef@example.com",
                "display_name": "Emanuel",
                "password": "a-sufficiently-long-password",
            },
        )
        token = response.json()["token"]
        assert (
            await client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
        ).status_code == 200
