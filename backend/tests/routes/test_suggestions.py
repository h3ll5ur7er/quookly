"""Discovery through the API (UC-3.1, UC-3.3, UC-3.4).

Phase 6's promise, end to end: *what should I cook* answered with recipes that use up what
is about to go off, ranked and with their reasons.

So these tests are mostly about the order, and about the one thing the order must never do —
lead with something somebody at the table cannot eat.
"""

from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.ingredient import Allergen, IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

RECIPES = "/api/v1/recipes"
SUGGESTIONS = f"{RECIPES}/suggestions"


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


@pytest.fixture
async def cook(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "chef@example.com")


@pytest.fixture
async def pantry() -> dict[str, int]:
    entries = {}
    for slug, name, kind, allergens in [
        ("plain-flour", "plain flour", IngredientKind.POWDER, frozenset({Allergen.GLUTEN})),
        ("spinach", "spinach", IngredientKind.SOLID, frozenset()),
        ("rhubarb", "rhubarb", IngredientKind.SOLID, frozenset()),
        ("saffron", "saffron", IngredientKind.POWDER, frozenset()),
    ]:
        created = await registry.register(
            slug=slug,
            kind=kind,
            density=None,
            names={"en-GB": [name]},
            allergens=allergens,
        )
        entries[slug] = created.id
    return entries


async def a_recipe(
    client: AsyncClient, headers: dict[str, str], title: str, *ingredient_ids: int
) -> int:
    created = await client.post(
        RECIPES,
        json={
            "title": title,
            "yield_magnitude": "4",
            "yield_unit": "serving",
            "lines": [
                {"ingredient_id": one, "magnitude": "100", "unit": "g"} for one in ingredient_ids
            ],
            "steps": [{"instruction": "Cook it."}],
        },
        headers=headers,
    )
    return int(created.json()["id"])


async def in_the_pantry(ingredient_id: int, expires_in: int | None = None) -> None:
    await pantry_access.receive(
        cook_id=1,
        ingredient_id=ingredient_id,
        quantity=Quantity(Decimal(500), Unit.GRAM),
        expires_on=None if expires_in is None else date.today() + timedelta(days=expires_in),
        note=None,
    )


def titles(response: Any) -> list[str]:
    return [one["recipe"]["title"] for one in response.json()]


class TestWhatToCook:
    async def test_signing_in_is_required(self, client: AsyncClient) -> None:
        assert (await client.get(SUGGESTIONS)).status_code == 401

    async def test_an_empty_collection_suggests_nothing(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        assert (await client.get(SUGGESTIONS, headers=cook)).json() == []

    async def test_something_that_needs_eating_comes_first(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """Phase 6's "done when", in one assertion. A full cupboard gives a cook plenty of
        options; the spinach going off on Thursday is the one that costs money if ignored."""
        await a_recipe(client, cook, "Flour Pudding", pantry["plain-flour"])
        await a_recipe(client, cook, "Spinach Pie", pantry["spinach"], pantry["saffron"])
        await in_the_pantry(pantry["plain-flour"])
        await in_the_pantry(pantry["spinach"], expires_in=1)

        suggested = await client.get(SUGGESTIONS, headers=cook)
        assert titles(suggested)[0] == "Spinach Pie"

    async def test_it_names_what_needs_eating(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """ "Uses 1 thing that needs eating" does not tell a cook whether to bother."""
        await a_recipe(client, cook, "Spinach Pie", pantry["spinach"])
        await in_the_pantry(pantry["spinach"], expires_in=1)

        first = (await client.get(SUGGESTIONS, headers=cook)).json()[0]
        assert first["pressing"] == ["spinach"]
        assert "uses_soon" in first["reasons"]

    async def test_a_packet_that_keeps_is_not_pressing(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Spinach Pie", pantry["spinach"])
        await in_the_pantry(pantry["spinach"], expires_in=90)

        first = (await client.get(SUGGESTIONS, headers=cook)).json()[0]
        assert first["pressing"] == []

    async def test_having_everything_is_said_rather_than_implied(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Flour Pudding", pantry["plain-flour"])
        await in_the_pantry(pantry["plain-flour"])

        first = (await client.get(SUGGESTIONS, headers=cook)).json()[0]
        assert "have_everything" in first["reasons"]
        assert first["missing"] == 0

    async def test_what_is_missing_is_counted(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Saffron Buns", pantry["plain-flour"], pantry["saffron"])
        await in_the_pantry(pantry["plain-flour"])

        first = (await client.get(SUGGESTIONS, headers=cook)).json()[0]
        assert first["missing"] == 1

    async def test_a_recipe_somebody_cannot_eat_is_last_rather_than_gone(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """Ranked down, not hidden (ADR-010). A cook may still want it and the badge says
        why — but a suggestion is a recommendation, and this one should not lead."""
        await client.post(
            "/api/v1/eaters",
            json={
                "name": "Mira",
                "age_band": "adult",
                "constraints": [{"allergen": "gluten", "severity": "medical"}],
            },
            headers=cook,
        )
        await a_recipe(client, cook, "Flour Pudding", pantry["plain-flour"])
        await a_recipe(client, cook, "Rhubarb Fool", pantry["rhubarb"])
        await in_the_pantry(pantry["plain-flour"], expires_in=1)

        suggested = await client.get(SUGGESTIONS, headers=cook)
        assert titles(suggested) == ["Rhubarb Fool", "Flour Pudding"]
        assert "not_for_everyone" in suggested.json()[-1]["reasons"]

    async def test_a_suggestion_carries_the_recipe_a_list_row_would(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """The same row as the plain listing, so a recipe reads alike wherever it appears."""
        await a_recipe(client, cook, "Flour Pudding", pantry["plain-flour"])

        first = (await client.get(SUGGESTIONS, headers=cook)).json()[0]
        assert first["recipe"]["title"] == "Flour Pudding"
        assert first["recipe"]["yield_quantity"]["display"] == "4 servings"


class TestSearching:
    async def test_words_find_a_recipe_by_its_title(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Rhubarb Fool", pantry["rhubarb"])
        await a_recipe(client, cook, "Flour Pudding", pantry["plain-flour"])

        assert titles(await client.get(f"{SUGGESTIONS}?q=rhubarb", headers=cook)) == [
            "Rhubarb Fool"
        ]

    async def test_words_find_a_recipe_by_what_is_in_it(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Sunday Pudding", pantry["rhubarb"])

        assert titles(await client.get(f"{SUGGESTIONS}?q=rhubarb", headers=cook)) == [
            "Sunday Pudding"
        ]

    async def test_nothing_matching_is_an_empty_answer_rather_than_everything(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Rhubarb Fool", pantry["rhubarb"])
        assert (await client.get(f"{SUGGESTIONS}?q=lobster", headers=cook)).json() == []

    async def test_an_empty_search_is_a_suggestion_rather_than_a_search(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Rhubarb Fool", pantry["rhubarb"])
        assert len((await client.get(f"{SUGGESTIONS}?q=%20%20", headers=cook)).json()) == 1

    async def test_what_matched_beats_what_the_kitchen_holds(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """A search is a question. Answering it with something else because the spinach is
        going off would be the interface ignoring what was asked."""
        await a_recipe(client, cook, "Rhubarb Fool", pantry["rhubarb"])
        await a_recipe(client, cook, "Spinach Pie", pantry["spinach"])
        await in_the_pantry(pantry["spinach"], expires_in=1)

        assert titles(await client.get(f"{SUGGESTIONS}?q=rhubarb", headers=cook)) == [
            "Rhubarb Fool"
        ]

    async def test_a_newly_imported_recipe_is_findable_without_a_restart(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """The index is kept in step where recipes are stored, so no path can forget."""
        await a_recipe(client, cook, "Rhubarb Fool", pantry["rhubarb"])
        assert titles(await client.get(f"{SUGGESTIONS}?q=fool", headers=cook)) == ["Rhubarb Fool"]

    async def test_another_cooks_recipes_are_not_findable(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        await a_recipe(client, cook, "Rhubarb Fool", pantry["rhubarb"])
        signed_up = await sign_up(client, "neighbour@example.com")
        other = signed_up
        assert (await client.get(f"{SUGGESTIONS}?q=rhubarb", headers=other)).json() == []
