"""Seed content (UC-10.4, FR-17, ADR-016).

An empty instance is indistinguishable from a broken one, and a cook with nothing to look
at has no reason to return. The seed file is an ordinary exchange document, so the format
that carries a cook's recipes out is the same one that brings the starter set in.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import recipe as recipe_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.engines import exchange
from quookly.managers import seed
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


class TestTheSeedFile:
    def test_it_is_an_ordinary_exchange_document(self) -> None:
        """One format in and out, so the seed set is exercised by the same tests."""
        document = seed.read_seed_file()
        # From the engine rather than a literal: the seed set ships in whatever format
        # this build writes, and bumping one should not be a change to two places.
        assert document["quookly"] == exchange.FORMAT_VERSION
        assert len(document["ingredients"]) > 10

    def test_it_covers_the_kinds_a_cook_measures_differently(self) -> None:
        kinds = {entry["kind"] for entry in seed.read_seed_file()["ingredients"]}
        assert kinds == {"powder", "liquid", "solid", "countable"}

    def test_countable_things_have_no_density(self) -> None:
        for entry in seed.read_seed_file()["ingredients"]:
            if entry["kind"] == "countable":
                assert entry["density"] is None, entry["slug"]

    def test_everything_else_has_one(self) -> None:
        """Without a density, a scraped cup cannot become a weight."""
        for entry in seed.read_seed_file()["ingredients"]:
            if entry["kind"] != "countable":
                assert entry["density"] is not None, entry["slug"]

    def test_aliases_are_carried(self) -> None:
        """Recipes say cornflour or cornstarch; both must resolve."""
        entries = {e["slug"]: e for e in seed.read_seed_file()["ingredients"]}
        assert "cornstarch" in entries["cornflour"]["names"]


class TestStockingTheRegistry:
    async def test_a_fresh_instance_gets_a_registry(self) -> None:
        added = await seed.stock_registry()
        assert added > 10
        assert await registry.resolve("plain flour", ENGLISH) is not None

    async def test_seeded_entries_are_marked_as_seeded(self) -> None:
        """So an upgrade may replace them and never a cook's own (ADR-016)."""
        await seed.stock_registry()
        flour = await registry.resolve("plain flour", ENGLISH)
        assert flour is not None
        assert flour.origin is Origin.SEED

    async def test_aliases_resolve_to_the_same_entry(self) -> None:
        await seed.stock_registry()
        one = await registry.resolve("cornflour", ENGLISH)
        other = await registry.resolve("cornstarch", ENGLISH)
        assert one is not None and other is not None
        assert one.id == other.id

    async def test_stocking_twice_adds_nothing(self) -> None:
        """Every start-up runs this; it must be safe to run repeatedly."""
        first = await seed.stock_registry()
        second = await seed.stock_registry()
        assert first > 0
        assert second == 0

    async def test_a_cooks_own_entry_is_never_replaced(self) -> None:
        """An upgrade may refresh the seed set; it may not touch somebody's own work."""
        await registry.register(
            slug="plain-flour",
            kind=IngredientKind.POWDER,
            density=Decimal("0.61"),
            names={ENGLISH: ["plain flour"]},
        )
        await seed.stock_registry()
        flour = await registry.resolve("plain flour", ENGLISH)
        assert flour is not None
        assert flour.density == Decimal("0.61")
        assert flour.origin is Origin.USER


class TestStarterRecipes:
    async def test_the_first_cook_is_given_something_to_look_at(self, cook_id: int) -> None:
        await seed.stock_registry()
        added = await seed.install_starter_recipes(cook_id)
        assert added == 2

    async def test_the_starter_recipes_are_theirs_to_change(self, cook_id: int) -> None:
        """Given to the cook rather than owned by the instance, so they can be edited."""
        from quookly.managers import recipe as recipe_manager

        await seed.stock_registry()
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id)
        assert {summary.title for summary in listed} == {"Buttermilk Pancakes", "Shortbread"}

    async def test_a_starter_recipe_reads_correctly(self, cook_id: int) -> None:
        from quookly.managers import recipe as recipe_manager

        await seed.stock_registry()
        await seed.install_starter_recipes(cook_id)
        listed = await recipe_manager.list_for(cook_id)
        shortbread = next(s for s in listed if s.title == "Shortbread")
        presented = await recipe_manager.present(shortbread.id, cook_id, ENGLISH)
        assert presented is not None
        butter = presented.lines[0].quantity
        assert butter is not None and butter.display == "225 g"
        assert presented.lines[0].ingredient == "unsalted butter"


class TestTheSeededClassification:
    def test_every_seeded_ingredient_is_classified(self) -> None:
        """An unclassified staple would make ordinary recipes read as unknown forever."""
        unclassified = [
            entry["slug"]
            for entry in seed.read_seed_file()["ingredients"]
            if entry.get("allergens") is None
        ]
        assert unclassified == []

    def test_the_obvious_ones_are_right(self) -> None:
        entries = {e["slug"]: e for e in seed.read_seed_file()["ingredients"]}
        assert entries["plain-flour"]["allergens"] == ["gluten"]
        assert entries["unsalted-butter"]["allergens"] == ["milk"]
        assert entries["egg"]["allergens"] == ["eggs"]
        assert entries["ground-almonds"]["allergens"] == ["tree_nuts"]

    def test_something_containing_none_says_so_rather_than_staying_silent(self) -> None:
        entries = {e["slug"]: e for e in seed.read_seed_file()["ingredients"]}
        assert entries["caster-sugar"]["allergens"] == []

    async def test_the_classification_survives_into_the_registry(self) -> None:
        await seed.stock_registry()
        butter = await registry.resolve("unsalted butter", ENGLISH)
        sugar = await registry.resolve("caster sugar", ENGLISH)
        assert butter is not None and sugar is not None

        assert butter.classified and Allergen.MILK in butter.allergens
        assert sugar.classified and sugar.allergens == frozenset()


class TestWhatTheStarterRecipesSay:
    async def test_they_say_how_many_they_feed(self, cook_id: int) -> None:
        """Both starter recipes count things — twelve pancakes, sixteen biscuits — so
        without this neither could be scaled to a table, which is the first thing a cook
        does with a recipe. It was missed once: the starter path built its own draft and
        quietly dropped the field, and an end-to-end run found it."""
        await seed.stock_registry()
        await seed.install_starter_recipes(cook_id)

        stored = await recipe_access.list_for_cook(cook_id)

        assert stored
        assert all(recipe.servings is not None for recipe in stored)
