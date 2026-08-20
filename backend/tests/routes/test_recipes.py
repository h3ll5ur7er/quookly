"""Recipes through the API: authored, listed, scaled, and rendered in a cook's units."""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access import preferences as preference_access
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.contracts.measure import Unit
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"


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
async def pantry() -> dict[str, int]:
    entries = {}
    for slug, name, kind, density in [
        ("plain-flour", "plain flour", IngredientKind.POWDER, Decimal("0.53")),
        ("milk", "milk", IngredientKind.LIQUID, Decimal("1.03")),
        ("egg", "egg", IngredientKind.COUNTABLE, None),
    ]:
        created = await registry.register(
            slug=slug, kind=kind, density=density, names={ENGLISH: [name]}, origin=Origin.SEED
        )
        entries[slug] = created.id
    return entries


def pancakes(pantry: dict[str, int]) -> dict[str, Any]:
    return {
        "title": "Pancakes",
        "summary": "Batter, pan, patience.",
        "yield_magnitude": "12",
        "yield_unit": "piece",
        "lines": [
            {"ingredient_id": pantry["plain-flour"], "magnitude": "1", "unit": "cup (US)"},
            {"ingredient_id": pantry["milk"], "magnitude": "300", "unit": "ml"},
            {"ingredient_id": pantry["egg"], "magnitude": "2", "unit": "piece"},
        ],
        "steps": [
            {"instruction": "Whisk everything together."},
            {"instruction": "Rest the batter.", "duration_seconds": 1800},
            {"instruction": "Fry until golden.", "temperature_celsius": 180},
        ],
    }


class TestAuthoring:
    async def test_a_recipe_can_be_authored(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        response = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert response.status_code == 201
        assert response.json()["title"] == "Pancakes"

    async def test_a_recipe_needs_ingredients_and_steps(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        response = await client.post(
            "/api/v1/recipes", json={**pancakes(pantry), "lines": []}, headers=headers
        )
        assert response.status_code == 422

    async def test_an_unknown_unit_is_refused_rather_than_guessed(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe = pancakes(pantry)
        recipe["lines"][0]["unit"] = "handfuls"
        response = await client.post("/api/v1/recipes", json=recipe, headers=headers)
        assert response.status_code in (400, 422)


class TestReading:
    async def test_a_cook_lists_their_own_recipes(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        listed = await client.get("/api/v1/recipes", headers=headers)
        assert [item["title"] for item in listed.json()] == ["Pancakes"]

    async def test_another_cooks_recipe_is_absent_not_forbidden(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """A 403 would confirm the recipe exists. Private means invisible."""
        mine = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=mine)
        recipe_id = created.json()["id"]

        theirs = await sign_up(client, "other@example.com")
        response = await client.get(f"/api/v1/recipes/{recipe_id}", headers=theirs)
        assert response.status_code == 404

    async def test_an_unknown_recipe_is_not_found(self, client: AsyncClient) -> None:
        headers = await sign_up(client, "chef@example.com")
        assert (await client.get("/api/v1/recipes/9999", headers=headers)).status_code == 404


class TestRendering:
    async def test_a_cup_of_flour_is_shown_in_grams(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """The founding annoyance, fixed end to end."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        flour = created.json()["lines"][0]
        assert flour["ingredient"] == "plain flour"
        assert flour["quantity"]["display"] == "125 g"

    async def test_a_count_is_left_as_a_count(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert created.json()["lines"][2]["quantity"]["display"] == "2"

    async def test_quantities_follow_the_cooks_preference(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """A Swiss cook asked for decilitres, so 300 ml of milk reads as 3 dl."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        listed = await client.get("/api/v1/recipes", headers=headers)
        assert listed.status_code == 200
        cook_id = 1
        await preference_access.choose(cook_id, IngredientKind.LIQUID, Unit.DECILITRE)

        response = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        milk = response.json()["lines"][1]
        assert milk["quantity"]["display"] == "3 dl"

    async def test_a_quantity_is_a_string_not_a_json_number(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """A browser's JSON numbers are binary floats; a gram is not worth losing to that."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert isinstance(created.json()["lines"][0]["quantity"]["magnitude"], str)


class TestDisplayStrings:
    async def test_a_listed_yield_reads_as_a_number(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Stored precision is not display precision. "12.0000 pieces" is not a yield."""
        headers = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)

        listed = await client.get("/api/v1/recipes", headers=headers)
        assert listed.json()[0]["yield_quantity"]["display"] == "12"

    async def test_the_precise_magnitude_is_still_available(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Display is tidied; the value a client might compute with is not."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert created.json()["lines"][1]["quantity"]["magnitude"]


class TestScaling:
    async def test_halving_the_yield_halves_the_ingredients(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        response = await client.get(f"/api/v1/recipes/{recipe_id}?servings=6", headers=headers)
        body = response.json()
        assert body["yield_quantity"]["display"] == "6"
        assert body["lines"][0]["quantity"]["display"] == "62.7 g"
        assert body["lines"][1]["quantity"]["display"] == "150 ml"

    async def test_scaling_up_works_the_same_way(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        response = await client.get(f"/api/v1/recipes/{recipe_id}?servings=24", headers=headers)
        assert response.json()["lines"][1]["quantity"]["display"] == "600 ml"

    async def test_the_unscaled_recipe_is_unchanged_by_a_scaled_reading(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Scaling is a view. Reading a recipe for six must not edit it."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        await client.get(f"/api/v1/recipes/{recipe_id}?servings=6", headers=headers)
        again = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert again.json()["lines"][1]["quantity"]["display"] == "300 ml"

    async def test_a_yield_of_zero_is_refused(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]
        response = await client.get(f"/api/v1/recipes/{recipe_id}?servings=0", headers=headers)
        assert response.status_code == 422


class TestExchange:
    async def test_export_is_not_mistaken_for_a_recipe_id(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """`/recipes/export` and `/recipes/{id}` share a prefix; order decides which wins."""
        headers = await sign_up(client, "chef@example.com")
        response = await client.get("/api/v1/recipes/export", headers=headers)
        assert response.status_code == 200
        assert response.json()["quookly"] == 1

    async def test_a_cook_can_take_their_recipes_with_them(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)

        exported = (await client.get("/api/v1/recipes/export", headers=headers)).json()
        assert [recipe["title"] for recipe in exported["recipes"]] == ["Pancakes"]
        assert {entry["slug"] for entry in exported["ingredients"]} == {
            "plain-flour",
            "milk",
            "egg",
        }

    async def test_what_was_exported_can_be_imported(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """FR-11 end to end: the export format is the import format."""
        mine = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=mine)
        exported = (await client.get("/api/v1/recipes/export", headers=mine)).json()

        theirs = await sign_up(client, "other@example.com")
        response = await client.post(
            "/api/v1/recipes/import", json=exported, headers=theirs
        )
        assert response.status_code == 201
        assert response.json() == {"recipes_added": 1, "ingredients_added": 0}

        listed = await client.get("/api/v1/recipes", headers=theirs)
        assert [item["title"] for item in listed.json()] == ["Pancakes"]

    async def test_a_document_this_build_cannot_read_is_refused(
        self, client: AsyncClient
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        response = await client.post(
            "/api/v1/recipes/import", json={"quookly": 99, "recipes": []}, headers=headers
        )
        assert response.status_code == 422

    async def test_export_requires_signing_in(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/recipes/export")).status_code == 401
