"""Recipe lines that carry no quantity.

"Salt, to taste." "Oil, for frying." "A pinch of nutmeg." These are ordinary lines in
every cookbook ever written, and until now a recipe holding one could not be stored — so
importing a real page would either fail or quietly drop the line, and dropping an
ingredient is the failure this project refuses.

A missing quantity is not zero and not one. It is a line the cook judges for themselves.
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
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

ENGLISH = "en-GB"
RECIPES = "/api/v1/recipes"


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
    for slug, name, kind, density in [
        ("plain-flour", "plain flour", IngredientKind.POWDER, Decimal("0.53")),
        ("fine-salt", "fine salt", IngredientKind.POWDER, Decimal("1.2")),
        ("vegetable-oil", "vegetable oil", IngredientKind.LIQUID, Decimal("0.92")),
    ]:
        created = await registry.register(
            slug=slug, kind=kind, density=density, names={ENGLISH: [name]}, origin=Origin.SEED
        )
        entries[slug] = created.id
    return entries


def flatbread(pantry: dict[str, int]) -> dict[str, Any]:
    """Two measured lines and two the cook judges for themselves."""
    return {
        "title": "Flatbread",
        "yield_magnitude": "4",
        "yield_unit": "piece",
        "lines": [
            {"ingredient_id": pantry["plain-flour"], "magnitude": "250", "unit": "g"},
            {"ingredient_id": pantry["fine-salt"], "preparation": "to taste"},
            {"ingredient_id": pantry["vegetable-oil"], "preparation": "for frying"},
        ],
        "steps": [{"instruction": "Mix, rest, roll, fry."}],
    }


class TestStoring:
    async def test_a_line_without_a_quantity_is_accepted(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        response = await client.post(RECIPES, json=flatbread(pantry), headers=cook)
        assert response.status_code == 201, response.text

    async def test_it_is_read_back_without_one(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """Not zero, and not one. Inventing either would misweigh or mislead."""
        created = await client.post(RECIPES, json=flatbread(pantry), headers=cook)
        salt = next(line for line in created.json()["lines"] if line["ingredient"] == "fine salt")
        assert salt["quantity"] is None

    async def test_the_ingredient_and_its_note_survive(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        created = await client.post(RECIPES, json=flatbread(pantry), headers=cook)
        salt = next(line for line in created.json()["lines"] if line["ingredient"] == "fine salt")
        assert salt["preparation"] == "to taste"

    async def test_measured_lines_are_unaffected(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        created = await client.post(RECIPES, json=flatbread(pantry), headers=cook)
        flour = next(
            line for line in created.json()["lines"] if line["ingredient"] == "plain flour"
        )
        assert flour["quantity"]["display"] == "250 g"

    async def test_a_magnitude_without_a_unit_is_still_refused(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """Half a *what*. A number with no unit is not a smaller amount of information,
        it is a wrong one."""
        recipe = flatbread(pantry)
        recipe["lines"][0] = {"ingredient_id": pantry["plain-flour"], "magnitude": "250"}
        response = await client.post(RECIPES, json=recipe, headers=cook)
        assert response.status_code == 422


class TestScaling:
    async def test_scaling_leaves_an_unmeasured_line_alone(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """Twice as much "to taste" is still "to taste"."""
        created = await client.post(RECIPES, json=flatbread(pantry), headers=cook)
        doubled = await client.get(
            f"{RECIPES}/{created.json()['id']}", params={"servings": "8"}, headers=cook
        )
        lines = {line["ingredient"]: line for line in doubled.json()["lines"]}
        assert lines["plain flour"]["quantity"]["display"] == "500 g"
        assert lines["fine salt"]["quantity"] is None


class TestExchange:
    async def test_an_unmeasured_line_survives_a_round_trip(
        self, client: AsyncClient, cook: dict[str, str], pantry: dict[str, int]
    ) -> None:
        """A recipe must not gain a quantity by being exported and imported."""
        await client.post(RECIPES, json=flatbread(pantry), headers=cook)
        document = (await client.get(f"{RECIPES}/export", headers=cook)).json()
        salt = next(
            line for line in document["recipes"][0]["lines"] if line["ingredient"] == "fine-salt"
        )
        assert salt["magnitude"] is None
        assert salt["unit"] is None

        neighbour = await sign_up(client, "neighbour@example.com")
        theirs = neighbour
        imported = await client.post("/api/v1/recipes/import", json=document, headers=theirs)
        assert imported.status_code == 201, imported.text

        listed = (await client.get(RECIPES, headers=theirs)).json()
        detail = (await client.get(f"{RECIPES}/{listed[0]['id']}", headers=theirs)).json()
        arrived = next(line for line in detail["lines"] if line["ingredient"] == "fine salt")
        assert arrived["quantity"] is None
        assert arrived["preparation"] == "to taste"
