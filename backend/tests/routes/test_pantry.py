"""The pantry through the API (UC-5.1 to UC-5.4).

The tests here are about the boundary rather than the arithmetic: that a shelf belongs to
exactly one cook, that adjusting and wasting stay two different acts all the way out to
the wire, and that a mistaken entry can be taken back without being counted as waste.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.ingredient import IngredientKind
from quookly.utilities.configuration import get_settings

PANTRY = "/api/v1/pantry"


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
        json={"email": email, "display_name": "Emanuel", "password": "a-long-enough-password"},
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
async def cook(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "chef@example.com")


@pytest.fixture
async def neighbour(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "neighbour@example.com")


@pytest.fixture
async def flour() -> int:
    entry = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=None,
        names={"en-GB": ["plain flour"]},
    )
    return entry.id


def arriving(ingredient_id: int, **overrides: Any) -> dict[str, Any]:
    return {"ingredient_id": ingredient_id, "magnitude": "500", "unit": "g", **overrides}


async def test_signing_in_is_required(client: AsyncClient) -> None:
    assert (await client.get(PANTRY)).status_code == 401


async def test_stock_arrives_and_reads_back(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    created = await client.post(PANTRY, json=arriving(flour, expires_on="2026-12-01"), headers=cook)

    assert created.status_code == 201
    assert created.json()["total"] == "500 g"

    shelf = await client.get(PANTRY, headers=cook)
    assert [entry["name"] for entry in shelf.json()] == ["plain flour"]
    assert shelf.json()[0]["lots"][0]["expires_on"] == "2026-12-01"


async def test_an_unknown_ingredient_is_refused_in_words(
    client: AsyncClient, cook: dict[str, str]
) -> None:
    response = await client.post(PANTRY, json=arriving(9999), headers=cook)

    assert response.status_code == 404
    assert "no ingredient" in response.json()["detail"]


async def test_a_unit_nobody_has_heard_of_is_named_back(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    """Not "invalid input". A cook who typed "handfuls" needs to be told which word was
    the problem."""
    response = await client.post(PANTRY, json=arriving(flour, unit="handfuls"), headers=cook)

    assert response.status_code == 422
    assert "handfuls" in response.json()["detail"]


async def test_one_cooks_shelf_is_not_anothers(
    client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str], flour: int
) -> None:
    created = await client.post(PANTRY, json=arriving(flour), headers=cook)
    lot = created.json()["lots"][0]["id"]

    assert (await client.get(PANTRY, headers=neighbour)).json() == []
    assert (
        await client.patch(f"{PANTRY}/lots/{lot}", json={"magnitude": "1"}, headers=neighbour)
    ).status_code == 404
    assert (await client.delete(f"{PANTRY}/lots/{lot}", headers=neighbour)).status_code == 404


async def test_adjusting_restates_what_is_there(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    created = await client.post(PANTRY, json=arriving(flour), headers=cook)
    lot = created.json()["lots"][0]["id"]

    adjusted = await client.patch(f"{PANTRY}/lots/{lot}", json={"magnitude": "300"}, headers=cook)

    assert adjusted.status_code == 200
    assert adjusted.json()["total"] == "300 g"


async def test_wasting_is_its_own_act(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    created = await client.post(PANTRY, json=arriving(flour), headers=cook)
    lot = created.json()["lots"][0]["id"]

    wasted = await client.post(
        f"{PANTRY}/lots/{lot}/waste",
        json={"magnitude": "200", "reason": "spoiled", "note": "weevils"},
        headers=cook,
    )

    assert wasted.status_code == 200
    assert wasted.json()["total"] == "300 g"


async def test_throwing_away_more_than_is_there_is_refused(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    created = await client.post(PANTRY, json=arriving(flour), headers=cook)
    lot = created.json()["lots"][0]["id"]

    response = await client.post(
        f"{PANTRY}/lots/{lot}/waste", json={"magnitude": "900", "reason": "spoiled"}, headers=cook
    )

    assert response.status_code == 422
    assert "more than" in response.json()["detail"]


async def test_a_mistaken_entry_can_be_taken_back(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    created = await client.post(PANTRY, json=arriving(flour), headers=cook)
    lot = created.json()["lots"][0]["id"]

    assert (await client.delete(f"{PANTRY}/lots/{lot}", headers=cook)).status_code == 204
    assert (await client.get(PANTRY, headers=cook)).json() == []


async def test_a_lot_already_wasted_from_cannot_be_taken_back(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    """Deleting it would leave the waste record pointing at nothing — and quietly shrink
    the history the cook is trying to learn from."""
    created = await client.post(PANTRY, json=arriving(flour), headers=cook)
    lot = created.json()["lots"][0]["id"]
    await client.post(
        f"{PANTRY}/lots/{lot}/waste", json={"magnitude": "100", "reason": "spoiled"}, headers=cook
    )

    response = await client.delete(f"{PANTRY}/lots/{lot}", headers=cook)

    assert response.status_code == 409
    assert "adjust it to zero" in response.json()["detail"]


async def test_using_soon_is_its_own_view(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    await client.post(PANTRY, json=arriving(flour, expires_on="2099-01-01"), headers=cook)

    pressing = await client.get(f"{PANTRY}/using-soon", headers=cook)

    assert pressing.status_code == 200
    assert pressing.json() == []
