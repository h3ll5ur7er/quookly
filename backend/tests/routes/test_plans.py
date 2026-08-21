"""Plans through the API (UC-4.1 to UC-4.4).

The boundary rather than the arithmetic: that a week belongs to exactly one cook, that
stating a meal returns the whole plan because the shopping list moved with it, and that
deleting a plan gives its stock back rather than leaving it spoken for.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
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

PLANS = "/api/v1/plans"
MONDAY = "2026-08-24"
SUNDAY = "2026-08-30"


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
        density=Decimal("0.53"),
        names={"en-GB": ["plain flour"]},
    )
    return entry.id


async def a_recipe(client: AsyncClient, headers: dict[str, str], flour: int) -> int:
    """One that serves four, so every quantity follows from that."""
    created = await client.post(
        "/api/v1/recipes",
        json={
            "title": "Pancakes",
            "yield_magnitude": "4",
            "yield_unit": "serving",
            "lines": [{"ingredient_id": flour, "magnitude": "200", "unit": "g"}],
            "steps": [{"instruction": "Whisk."}],
        },
        headers=headers,
    )
    return int(created.json()["id"])


async def a_week(client: AsyncClient, headers: dict[str, str]) -> int:
    created = await client.post(
        PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=headers
    )
    return int(created.json()["id"])


def slot(**overrides: Any) -> dict[str, Any]:
    return {"on_date": MONDAY, "meal": "dinner", **overrides}


async def test_signing_in_is_required(client: AsyncClient) -> None:
    assert (await client.get(PLANS)).status_code == 401


async def test_a_week_opens_empty(client: AsyncClient, cook: dict[str, str]) -> None:
    created = await client.post(PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=cook)

    assert created.status_code == 201
    assert created.json()["slots"] == []
    assert created.json()["shopping"] == []


async def test_a_plan_that_ends_before_it_begins_is_refused(
    client: AsyncClient, cook: dict[str, str]
) -> None:
    response = await client.post(PLANS, json={"starts_on": SUNDAY, "ends_on": MONDAY}, headers=cook)

    assert response.status_code == 422


async def test_stating_a_meal_returns_the_whole_plan(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    """Because the shopping list moved with it, and a client that worked out how would be
    a second copy of the manager."""
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)

    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )

    assert placed.status_code == 200
    assert placed.json()["slots"][0]["recipe_title"] == "Pancakes"
    assert [line["quantity"] for line in placed.json()["shopping"]] == ["200 g"]


async def test_a_slot_is_stated_rather_than_repeated(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)

    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)
    again = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )

    assert len(again.json()["slots"]) == 1


async def test_reading_a_plan_does_not_change_it(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )

    read = await client.get(f"{PLANS}/{plan_id}", headers=cook)

    assert read.status_code == 200
    assert read.json() == placed.json()


async def test_clearing_a_meal_hands_back_the_plan_without_it(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )
    slot_id = placed.json()["slots"][0]["id"]

    cleared = await client.delete(f"{PLANS}/{plan_id}/slots/{slot_id}", headers=cook)

    assert cleared.status_code == 200
    assert cleared.json()["slots"] == []
    assert cleared.json()["shopping"] == []


async def test_a_plan_can_be_forgotten(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)

    assert (await client.delete(f"{PLANS}/{plan_id}", headers=cook)).status_code == 204
    assert (await client.get(f"{PLANS}/{plan_id}", headers=cook)).status_code == 404


async def test_a_plan_is_listed_with_how_much_of_it_is_planned(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)
    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(meal="lunch"), headers=cook)

    listed = await client.get(PLANS, headers=cook)

    assert listed.json() == [{"id": plan_id, "starts_on": MONDAY, "ends_on": SUNDAY, "planned": 1}]


async def test_one_cooks_week_is_not_anothers(
    client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
) -> None:
    plan_id = await a_week(client, cook)

    assert (await client.get(PLANS, headers=neighbour)).json() == []
    assert (await client.get(f"{PLANS}/{plan_id}", headers=neighbour)).status_code == 404
    assert (
        await client.put(f"{PLANS}/{plan_id}/slots", json=slot(), headers=neighbour)
    ).status_code == 404
    assert (await client.delete(f"{PLANS}/{plan_id}", headers=neighbour)).status_code == 404


async def test_a_period_longer_than_a_month_is_refused(
    client: AsyncClient, cook: dict[str, str]
) -> None:
    """Beyond about a month it is a calendar rather than a plan — nobody knows who is
    coming to dinner in November — and it is what stops a screen laying out a row per day
    for a period somebody typed by accident."""
    response = await client.post(
        PLANS, json={"starts_on": MONDAY, "ends_on": "2027-08-30"}, headers=cook
    )

    assert response.status_code == 422
