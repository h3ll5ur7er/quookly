"""A cook's preferred unit per kind of ingredient, through the API (UC-6.2).

Per kind rather than per system: "metric" is not a fine enough answer to be useful in a
kitchen, where the same cook wants powders in grams and liquids in decilitres.
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

UNITS = "/api/v1/preferences/units"


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


async def sign_up(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/accounts",
        json={
            "email": email,
            "display_name": "Emanuel",
            "password": "a-sufficiently-long-password",
        },
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
async def cook(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "chef@example.com")


def by_kind(body: Any) -> dict[str, Any]:
    return {entry["kind"]: entry for entry in body}


class TestReading:
    async def test_every_kind_is_offered(self, client: AsyncClient, cook: dict[str, str]) -> None:
        """A kind missing from the list is one a cook can never set."""
        response = await client.get(UNITS, headers=cook)
        assert response.status_code == 200
        assert set(by_kind(response.json())) == {"powder", "liquid", "solid", "countable"}

    async def test_a_new_cook_sees_workable_defaults(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        entries = by_kind((await client.get(UNITS, headers=cook)).json())
        assert entries["powder"]["unit"] == "g"
        assert entries["liquid"]["unit"] == "ml"

    async def test_a_default_is_marked_as_unchosen(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """Setup has to tell a preference from a default: everybody has defaults, and
        having them is not an answer."""
        entries = by_kind((await client.get(UNITS, headers=cook)).json())
        assert all(entry["chosen"] is False for entry in entries.values())

    async def test_it_needs_an_account(self, client: AsyncClient) -> None:
        assert (await client.get(UNITS)).status_code == 401


class TestChoosing:
    async def test_a_choice_is_remembered(self, client: AsyncClient, cook: dict[str, str]) -> None:
        response = await client.put(f"{UNITS}/liquid", json={"unit": "dl"}, headers=cook)
        assert response.status_code == 200
        assert by_kind(response.json())["liquid"]["unit"] == "dl"
        assert by_kind((await client.get(UNITS, headers=cook)).json())["liquid"]["chosen"] is True

    async def test_choosing_one_kind_leaves_the_others_alone(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.put(f"{UNITS}/liquid", json={"unit": "dl"}, headers=cook)
        entries = by_kind((await client.get(UNITS, headers=cook)).json())
        assert entries["powder"]["chosen"] is False

    async def test_a_unit_that_measures_the_wrong_thing_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """Grams for a countable is not a preference, it is a recipe that cannot render."""
        response = await client.put(f"{UNITS}/countable", json={"unit": "g"}, headers=cook)
        assert response.status_code == 422

    async def test_an_unknown_unit_is_refused_rather_than_guessed(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        response = await client.put(f"{UNITS}/liquid", json={"unit": "buckets"}, headers=cook)
        assert response.status_code == 422

    async def test_an_unknown_kind_is_refused(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        response = await client.put(f"{UNITS}/pudding", json={"unit": "g"}, headers=cook)
        assert response.status_code == 422

    async def test_cooks_do_not_share_preferences(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.put(f"{UNITS}/liquid", json={"unit": "dl"}, headers=cook)
        neighbour = await sign_up(client, "neighbour@example.com")
        assert (
            by_kind((await client.get(UNITS, headers=neighbour)).json())["liquid"]["unit"] == "ml"
        )


class TestItSettlesSetup:
    async def test_choosing_a_unit_settles_the_units_step(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        await client.put(f"{UNITS}/liquid", json={"unit": "dl"}, headers=cook)
        setup = (await client.get("/api/v1/setup", headers=cook)).json()
        assert "units" in {status["step"] for status in setup["steps"] if status["done"]}
