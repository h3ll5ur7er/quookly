"""What this instance is pointed at, for the person running it (UC-8.2).

An operator's first question about an inference provider is "is it on", and their second
is "is it the one I meant". Until now the only way to find out was to try an import and
read the failure.

Nothing here is settable. Configuration arrives as environment variables (FR-8), which is
what a self-hoster's container already speaks; this reports what that produced.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import model as inference
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

INSTANCE = "/api/v1/instance/inference"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-test-signing-key-of-sufficient-length-01")
    monkeypatch.delenv("QUOOKLY_INFERENCE_BASE_URL", raising=False)
    monkeypatch.delenv("QUOOKLY_INFERENCE_MODEL", raising=False)
    monkeypatch.delenv("QUOOKLY_INFERENCE_API_KEY", raising=False)
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


@pytest.fixture
async def admin(client: AsyncClient) -> dict[str, str]:
    """The first account on an instance is its administrator (FR-16)."""
    response = await client.post(
        "/api/v1/accounts/bootstrap",
        json={
            "email": "admin@example.com",
            "display_name": "Emanuel",
            "password": "a-sufficiently-long-password",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
async def ordinary(client: AsyncClient, admin: dict[str, str]) -> dict[str, str]:
    return await sign_up(client, "cook@example.com")


@pytest.fixture
def configured(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("QUOOKLY_INFERENCE_BASE_URL", "http://jarvis:9293/v1")
    monkeypatch.setenv("QUOOKLY_INFERENCE_MODEL", "a-model")
    get_settings.cache_clear()


def answering(status: int, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        inference,
        "_transport",
        lambda: httpx.MockTransport(lambda _: httpx.Response(status, json={"data": []})),
    )


def unreachable(monkeypatch: MonkeyPatch) -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(inference, "_transport", lambda: httpx.MockTransport(refuse))


async def status_of(client: AsyncClient, headers: dict[str, str]) -> Any:
    response = await client.get(INSTANCE, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


class TestWithoutAProvider:
    async def test_it_says_there_is_none(self, client: AsyncClient, admin: dict[str, str]) -> None:
        """An instance with no model is not broken. It cannot read a blog, and it can
        still import from every site that publishes its recipes properly."""
        assert (await status_of(client, admin))["configured"] is False

    async def test_it_says_how_to_configure_one(
        self, client: AsyncClient, admin: dict[str, str]
    ) -> None:
        """Naming the setting is the difference between a status page and a support
        question."""
        detail = (await status_of(client, admin))["detail"]
        assert "QUOOKLY_INFERENCE_BASE_URL" in detail

    async def test_reachability_is_not_claimed_either_way(
        self, client: AsyncClient, admin: dict[str, str]
    ) -> None:
        """Not false — nothing was tried. There is nowhere to try."""
        assert (await status_of(client, admin))["reachable"] is None


class TestWithAProvider:
    async def test_it_says_what_it_will_ask(
        self, client: AsyncClient, admin: dict[str, str], configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        answering(200, monkeypatch)
        found = await status_of(client, admin)
        assert found["configured"] is True
        assert found["base_url"] == "http://jarvis:9293/v1"
        assert found["model"] == "a-model"

    async def test_a_reachable_provider_reports_reachable(
        self, client: AsyncClient, admin: dict[str, str], configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        answering(200, monkeypatch)
        assert (await status_of(client, admin))["reachable"] is True

    async def test_an_unreachable_provider_reports_a_reason(
        self, client: AsyncClient, admin: dict[str, str], configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """The page must answer even when the thing it reports on does not. A diagnostic
        that fails when its subject is broken is no diagnostic."""
        unreachable(monkeypatch)
        found = await status_of(client, admin)
        assert found["reachable"] is False
        assert found["detail"]

    async def test_a_provider_that_refuses_is_reachable_but_reported(
        self, client: AsyncClient, admin: dict[str, str], configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """A 401 means the address is right and the key is wrong, which is a different
        thing to go and fix."""
        answering(401, monkeypatch)
        found = await status_of(client, admin)
        assert found["reachable"] is False
        assert "key" in found["detail"].lower()


class TestCredentials:
    async def test_it_says_whether_a_key_is_set(
        self, client: AsyncClient, admin: dict[str, str], configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QUOOKLY_INFERENCE_API_KEY", "sk-secret")
        get_settings.cache_clear()
        answering(200, monkeypatch)
        assert (await status_of(client, admin))["authenticated"] is True

    async def test_it_never_says_what_the_key_is(
        self, client: AsyncClient, admin: dict[str, str], configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """A status page that prints a credential has published it — into a screenshot, a
        support thread, a browser cache."""
        monkeypatch.setenv("QUOOKLY_INFERENCE_API_KEY", "sk-secret")
        get_settings.cache_clear()
        answering(200, monkeypatch)
        response = await client.get(INSTANCE, headers=admin)
        assert "sk-secret" not in response.text

    async def test_a_local_provider_needs_no_key(
        self, client: AsyncClient, admin: dict[str, str], configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        answering(200, monkeypatch)
        assert (await status_of(client, admin))["authenticated"] is False


class TestWhoMayLook:
    async def test_an_administrator_may(self, client: AsyncClient, admin: dict[str, str]) -> None:
        assert (await client.get(INSTANCE, headers=admin)).status_code == 200

    async def test_an_ordinary_cook_may_not(
        self, client: AsyncClient, ordinary: dict[str, str]
    ) -> None:
        """It names an address on the operator's network, and whether a credential is set.
        Neither is a cook's business, and the first is a map of where the server can see."""
        assert (await client.get(INSTANCE, headers=ordinary)).status_code == 403

    async def test_nobody_signed_out_may(self, client: AsyncClient) -> None:
        assert (await client.get(INSTANCE)).status_code == 401
