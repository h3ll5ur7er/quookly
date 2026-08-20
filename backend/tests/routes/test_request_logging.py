"""Every request is correlated and logged, and never with a password in it."""

import logging
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import LogCaptureFixture, MonkeyPatch
from sqlmodel import SQLModel

from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.utilities.configuration import get_settings

PASSWORD = "a-sufficiently-long-password"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-test-signing-key-of-sufficient-length-01")
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


class TestCorrelation:
    async def test_every_response_carries_a_request_id(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/status")
        assert response.headers["x-request-id"]

    async def test_each_request_gets_its_own_id(self, client: AsyncClient) -> None:
        first = await client.get("/api/v1/status")
        second = await client.get("/api/v1/status")
        assert first.headers["x-request-id"] != second.headers["x-request-id"]

    async def test_an_incoming_id_is_honoured(self, client: AsyncClient) -> None:
        """Behind a proxy the id is assigned upstream; adopting it keeps a trace whole."""
        response = await client.get("/api/v1/status", headers={"X-Request-ID": "from-upstream"})
        assert response.headers["x-request-id"] == "from-upstream"


class TestRequestLogging:
    async def test_a_request_is_logged_with_its_outcome(
        self, client: AsyncClient, caplog: LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.INFO, logger="quookly.request"):
            await client.get("/api/v1/status")
        logged = [r for r in caplog.records if r.name == "quookly.request"]
        assert logged, "the request was not logged"
        attached = logged[0].__dict__
        assert attached["status_code"] == 200
        assert attached["method"] == "GET"
        assert attached["path"] == "/api/v1/status"
        assert attached["duration_ms"] >= 0

    async def test_a_password_is_never_logged(
        self, client: AsyncClient, caplog: LogCaptureFixture
    ) -> None:
        """Request bodies are not logged, precisely so this can never happen."""
        with caplog.at_level(logging.DEBUG):
            await client.post(
                "/api/v1/accounts",
                json={
                    "email": "cook@example.com",
                    "display_name": "Emanuel",
                    "password": PASSWORD,
                },
            )
        assert PASSWORD not in caplog.text
