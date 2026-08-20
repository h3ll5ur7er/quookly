"""Export and import through the manager (UC-1.2, FR-11).

The engine moves data between shapes; this is the part that decides what a document's
slugs mean *here* — matching the local registry, and creating what is missing so an
import into a fresh instance works at all.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.errors import UnsupportedDocument
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.contracts.recipe import IngredientLineInput, RecipeInput, StepInput
from quookly.managers import recipe as recipe_manager
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def cook_id() -> int:
    cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
    return cook.id


async def seed_pantry() -> dict[str, int]:
    entries = {}
    for slug, name, kind, density in [
        ("plain-flour", "plain flour", IngredientKind.POWDER, Decimal("0.53")),
        ("egg", "egg", IngredientKind.COUNTABLE, None),
    ]:
        created = await registry.register(
            slug=slug, kind=kind, density=density, names={ENGLISH: [name]}, origin=Origin.SEED
        )
        entries[slug] = created.id
    return entries


def pancakes(pantry: dict[str, int]) -> RecipeInput:
    return RecipeInput(
        title="Pancakes",
        summary="Batter, pan, patience.",
        yield_magnitude=Decimal("12"),
        yield_unit="piece",
        lines=[
            IngredientLineInput(
                ingredient_id=pantry["plain-flour"], magnitude=Decimal("225"), unit="g"
            ),
            IngredientLineInput(
                ingredient_id=pantry["egg"], magnitude=Decimal("2"), unit="piece"
            ),
        ],
        steps=[StepInput(instruction="Whisk."), StepInput(instruction="Fry.")],
    )


async def export_of(cook_id: int) -> dict[str, Any]:
    document = await recipe_manager.export_for(cook_id, ENGLISH)
    return document.model_dump(mode="json")


class TestExporting:
    async def test_a_cook_exports_their_own_recipes(self, cook_id: int) -> None:
        pantry = await seed_pantry()
        await recipe_manager.author(pancakes(pantry), cook_id, ENGLISH)
        document = await export_of(cook_id)
        assert [recipe["title"] for recipe in document["recipes"]] == ["Pancakes"]

    async def test_an_export_carries_the_ingredients_it_needs(self, cook_id: int) -> None:
        pantry = await seed_pantry()
        await recipe_manager.author(pancakes(pantry), cook_id, ENGLISH)
        document = await export_of(cook_id)
        assert {entry["slug"] for entry in document["ingredients"]} == {"plain-flour", "egg"}

    async def test_a_cook_with_nothing_exports_an_empty_document(self, cook_id: int) -> None:
        document = await export_of(cook_id)
        assert document["recipes"] == []
        assert document["ingredients"] == []


class TestImportingIntoAnEmptyInstance:
    async def test_a_recipe_arrives_with_its_ingredients(self, cook_id: int) -> None:
        """The promise of FR-11: a document is enough on its own."""
        pantry = await seed_pantry()
        await recipe_manager.author(pancakes(pantry), cook_id, ENGLISH)
        document = await export_of(cook_id)

        elsewhere = await cook_access.register("other@example.com", "Someone", "hash")
        imported = await recipe_manager.import_document(document, elsewhere.id, ENGLISH)

        assert imported.recipes_added == 1
        listed = await recipe_manager.list_for(elsewhere.id)
        assert [summary.title for summary in listed] == ["Pancakes"]

    async def test_quantities_survive_the_journey(self, cook_id: int) -> None:
        pantry = await seed_pantry()
        await recipe_manager.author(pancakes(pantry), cook_id, ENGLISH)
        document = await export_of(cook_id)

        elsewhere = await cook_access.register("other@example.com", "Someone", "hash")
        await recipe_manager.import_document(document, elsewhere.id, ENGLISH)

        listed = await recipe_manager.list_for(elsewhere.id)
        presented = await recipe_manager.present(listed[0].id, elsewhere.id, ENGLISH)
        assert presented is not None
        assert presented.lines[0].quantity.display == "225 g"
        assert presented.lines[1].quantity.display == "2 piece"

    async def test_missing_ingredients_are_created(self, cook_id: int) -> None:
        pantry = await seed_pantry()
        await recipe_manager.author(pancakes(pantry), cook_id, ENGLISH)
        document = await export_of(cook_id)

        elsewhere = await cook_access.register("other@example.com", "Someone", "hash")
        result = await recipe_manager.import_document(document, elsewhere.id, ENGLISH)
        assert result.ingredients_added == 0, "they already exist on this instance"

    async def test_an_imported_ingredient_is_the_importers_own(self, cook_id: int) -> None:
        """A document must not be able to forge seeded rows an upgrade would replace."""
        await registry.register(
            slug="saffron",
            kind=IngredientKind.POWDER,
            density=Decimal("0.4"),
            names={ENGLISH: ["saffron"]},
            origin=Origin.SEED,
        )
        document = {
            "quookly": 1,
            "exported_at": "2026-08-20T12:00:00Z",
            "locale": ENGLISH,
            "ingredients": [
                {
                    "slug": "vanilla-pod",
                    "kind": "powder",
                    "density": "0.5",
                    "names": ["vanilla pod"],
                }
            ],
            "recipes": [
                {
                    "title": "Custard",
                    "yield_magnitude": "4",
                    "yield_unit": "serving",
                    "provenance": "imported_json",
                    "lines": [{"ingredient": "vanilla-pod", "magnitude": "1", "unit": "piece"}],
                    "steps": [{"instruction": "Infuse."}],
                }
            ],
        }
        result = await recipe_manager.import_document(document, cook_id, ENGLISH)
        assert result.ingredients_added == 1
        created = await registry.resolve("vanilla pod", ENGLISH)
        assert created is not None
        assert created.origin is Origin.USER


class TestImportingWhereThingsAlreadyExist:
    async def test_the_local_registry_wins(self, cook_id: int) -> None:
        """An instance's own density is its business; a document does not overwrite it."""
        await registry.register(
            slug="plain-flour",
            kind=IngredientKind.POWDER,
            density=Decimal("0.55"),
            names={ENGLISH: ["plain flour"]},
            origin=Origin.SEED,
        )
        document = {
            "quookly": 1,
            "exported_at": "2026-08-20T12:00:00Z",
            "locale": ENGLISH,
            "ingredients": [
                {
                    "slug": "plain-flour",
                    "kind": "powder",
                    "density": "0.99",
                    "names": ["plain flour"],
                }
            ],
            "recipes": [
                {
                    "title": "Roux",
                    "yield_magnitude": "1",
                    "yield_unit": "serving",
                    "provenance": "imported_json",
                    "lines": [{"ingredient": "plain-flour", "magnitude": "50", "unit": "g"}],
                    "steps": [{"instruction": "Cook out."}],
                }
            ],
        }
        await recipe_manager.import_document(document, cook_id, ENGLISH)
        flour = await registry.resolve("plain flour", ENGLISH)
        assert flour is not None
        assert flour.density == Decimal("0.55")


class TestRefusing:
    async def test_a_document_from_a_newer_format_is_refused(self, cook_id: int) -> None:
        with pytest.raises(UnsupportedDocument):
            await recipe_manager.import_document({"quookly": 99}, cook_id, ENGLISH)

    async def test_a_refused_document_changes_nothing(self, cook_id: int) -> None:
        """A partial import would leave a cook unable to tell what arrived."""
        document = {
            "quookly": 1,
            "exported_at": "2026-08-20T12:00:00Z",
            "locale": ENGLISH,
            "ingredients": [
                {"slug": "sound", "kind": "powder", "density": "0.5", "names": ["sound"]}
            ],
            "recipes": [
                {
                    "title": "Broken",
                    "yield_magnitude": "1",
                    "yield_unit": "serving",
                    "provenance": "imported_json",
                    "lines": [{"ingredient": "sound", "magnitude": "1", "unit": "handfuls"}],
                    "steps": [{"instruction": "Do it."}],
                }
            ],
        }
        with pytest.raises(UnsupportedDocument):
            await recipe_manager.import_document(document, cook_id, ENGLISH)
        assert await registry.resolve("sound", ENGLISH) is None
        assert await recipe_manager.list_for(cook_id) == []
