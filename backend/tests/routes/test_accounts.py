"""The account endpoints, exercised through the API as a client would.

Routes are Client services: they resolve input, call one manager, and translate domain
errors into status codes. These tests pin the translation, since a domain error escaping
as a 500 is how an ordinary refusal becomes an incident.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.utilities.configuration import get_settings

PASSWORD = "a-sufficiently-long-password"
REGISTRATION: dict[str, Any] = {
    "email": "cook@example.com",
    "display_name": "Emanuel",
    "password": PASSWORD,
}


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


class TestBootstrap:
    async def test_a_fresh_instance_reports_that_it_needs_bootstrapping(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/accounts/bootstrap")
        assert response.status_code == 200
        assert response.json() == {"required": True}

    async def test_bootstrapping_creates_an_admin(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        assert response.status_code == 201
        body = response.json()
        assert body["cook"]["is_admin"] is True
        assert body["token"]

    async def test_the_bootstrap_closes_after_use(self, client: AsyncClient) -> None:
        await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        state = await client.get("/api/v1/accounts/bootstrap")
        assert state.json() == {"required": False}

    async def test_bootstrapping_twice_is_a_conflict_not_a_crash(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/v1/accounts/bootstrap", json=REGISTRATION)
        second = await client.post(
            "/api/v1/accounts/bootstrap", json={**REGISTRATION, "email": "other@example.com"}
        )
        assert second.status_code == 409


class TestRegistration:
    async def test_an_account_can_be_registered(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/accounts", json=REGISTRATION)
        assert response.status_code == 201
        assert response.json()["cook"]["is_admin"] is False

    async def test_a_duplicate_email_is_a_conflict(self, client: AsyncClient) -> None:
        await client.post("/api/v1/accounts", json=REGISTRATION)
        second = await client.post("/api/v1/accounts", json=REGISTRATION)
        assert second.status_code == 409

    async def test_a_short_password_is_rejected_before_any_work(
        self, client: AsyncClient
    ) -> None:
        response = await client.post("/api/v1/accounts", json={**REGISTRATION, "password": "short"})
        assert response.status_code == 422

    async def test_a_malformed_email_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/accounts", json={**REGISTRATION, "email": "nope"})
        assert response.status_code == 422

    async def test_the_password_never_comes_back(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/accounts", json=REGISTRATION)
        assert PASSWORD not in response.text


class TestSignIn:
    async def test_correct_credentials_return_a_token(self, client: AsyncClient) -> None:
        await client.post("/api/v1/accounts", json=REGISTRATION)
        response = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["token"]

    async def test_a_wrong_password_is_unauthorised(self, client: AsyncClient) -> None:
        await client.post("/api/v1/accounts", json=REGISTRATION)
        response = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": "wrong-password-entirely"},
        )
        assert response.status_code == 401

    async def test_an_unknown_account_is_indistinguishable_from_a_wrong_password(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/v1/accounts", json=REGISTRATION)
        unknown = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "nobody@example.com", "password": PASSWORD},
        )
        wrong = await client.post(
            "/api/v1/accounts/sign-in",
            json={"email": "cook@example.com", "password": "wrong-password-entirely"},
        )
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json() == wrong.json()
