"""The recipe index (V10, UC-3.1).

What is checked here is retrieval, not order: pantry coverage, expiry and suitability are
ranking policy and belong to the engine. So these tests are mostly about the two things an
index has to get right — that a cook's words find the recipe they mean, and that whatever
they type into a search box is a search rather than a syntax error.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import recipe as recipe_access
from quookly.access import search
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.recipe import IngredientLineDraft, Provenance, RecipeDraft, StepDraft
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        # The index comes with the rest: it is a virtual table, so it hangs off
        # `after_create` rather than being declared as a model.
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def cook_id() -> int:
    cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
    return cook.id


@pytest.fixture
async def flour() -> int:
    entry = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=None,
        names={ENGLISH: ["plain flour"], "de-CH": ["Mehl"]},
    )
    return entry.id


@pytest.fixture
async def rhubarb() -> int:
    entry = await registry.register(
        slug="rhubarb", kind=IngredientKind.SOLID, density=None, names={ENGLISH: ["rhubarb"]}
    )
    return entry.id


async def store(cook_id: int, title: str, ingredient_id: int, summary: str | None = None) -> int:
    stored = await recipe_access.store(
        RecipeDraft(
            title=title,
            summary=summary,
            yield_quantity=Quantity(Decimal(4), Unit.SERVING),
            provenance=Provenance.AUTHORED,
            lines=[
                IngredientLineDraft(
                    ingredient_id=ingredient_id, quantity=Quantity(Decimal(100), Unit.GRAM)
                )
            ],
            steps=[StepDraft(instruction="Cook it.")],
        ),
        cook_id,
    )
    await search.index_recipe(stored.id)
    return stored.id


class TestFinding:
    async def test_a_word_from_the_title(self, cook_id: int, flour: int) -> None:
        pancakes = await store(cook_id, "Buttermilk Pancakes", flour)
        assert [hit.recipe_id for hit in await search.query("pancakes", cook_id)] == [pancakes]

    async def test_a_half_typed_word(self, cook_id: int, flour: int) -> None:
        """A search box that answers as you type has to match what is there so far."""
        pancakes = await store(cook_id, "Buttermilk Pancakes", flour)
        assert [hit.recipe_id for hit in await search.query("panc", cook_id)] == [pancakes]

    async def test_an_ingredient_rather_than_a_title(self, cook_id: int, rhubarb: int) -> None:
        """ "What can I do with rhubarb" is a question about ingredients."""
        crumble = await store(cook_id, "Sunday Pudding", rhubarb)
        assert [hit.recipe_id for hit in await search.query("rhubarb", cook_id)] == [crumble]

    async def test_an_ingredient_in_another_language(self, cook_id: int, flour: int) -> None:
        """A Swiss household reads the app in German and copies recipes titled in English.
        The index holds every name the registry knows, so either one finds it."""
        pancakes = await store(cook_id, "Buttermilk Pancakes", flour)
        assert [hit.recipe_id for hit in await search.query("Mehl", cook_id)] == [pancakes]

    async def test_every_word_has_to_appear(self, cook_id: int, flour: int) -> None:
        await store(cook_id, "Buttermilk Pancakes", flour)
        assert await search.query("buttermilk waffles", cook_id) == []

    async def test_a_title_counts_for_more_than_an_ingredient(
        self, cook_id: int, flour: int, rhubarb: int
    ) -> None:
        """A recipe called "Rhubarb Crumble" is a better answer to "rhubarb" than one that
        merely uses some."""
        named = await store(cook_id, "Rhubarb Crumble", rhubarb)
        using = await store(cook_id, "Sunday Pudding", rhubarb)

        found = [hit.recipe_id for hit in await search.query("rhubarb", cook_id)]
        assert found.index(named) < found.index(using)

    async def test_the_summary_is_searched_too(self, cook_id: int, flour: int) -> None:
        found = await store(cook_id, "Sunday Pudding", flour, summary="A childhood favourite")
        assert [hit.recipe_id for hit in await search.query("childhood", cook_id)] == [found]

    async def test_another_cooks_recipes_are_not_findable(self, cook_id: int, flour: int) -> None:
        await store(cook_id, "Buttermilk Pancakes", flour)
        other = await cook_access.register("neighbour@example.com", "Someone", "hash")
        assert await search.query("pancakes", other.id) == []


class TestWhateverSomebodyTypes:
    """A search box is a place to type words. Handing back a syntax error would be a strange
    thing to do to somebody looking for a pancake."""

    @pytest.mark.parametrize(
        "written", ['pancakes"', "pancakes AND OR", "(pancakes", "pancakes*", "NEAR(a b)", "^"]
    )
    async def test_the_index_query_language_does_not_leak(
        self, written: str, cook_id: int, flour: int
    ) -> None:
        await store(cook_id, "Buttermilk Pancakes", flour)
        await search.query(written, cook_id)

    async def test_nothing_typed_finds_nothing(self, cook_id: int) -> None:
        assert await search.query("   ", cook_id) == []

    async def test_accents_do_not_have_to_be_typed(self, cook_id: int, flour: int) -> None:
        """A phone keyboard makes finding the accent work. "creme" should find the crème."""
        brulee = await store(cook_id, "Crème brûlée", flour)
        assert [hit.recipe_id for hit in await search.query("creme brulee", cook_id)] == [brulee]

    async def test_case_is_not_a_difference(self, cook_id: int, flour: int) -> None:
        pancakes = await store(cook_id, "Buttermilk Pancakes", flour)
        assert [hit.recipe_id for hit in await search.query("BUTTERMILK", cook_id)] == [pancakes]


class TestKeepingItInStep:
    async def test_a_recipe_that_is_gone_is_not_found(self, cook_id: int, flour: int) -> None:
        """A hit on a recipe that no longer exists is worse than a miss: the cook taps it."""
        pancakes = await store(cook_id, "Buttermilk Pancakes", flour)
        await search.remove(pancakes)
        assert await search.query("pancakes", cook_id) == []

    async def test_indexing_twice_does_not_find_it_twice(self, cook_id: int, flour: int) -> None:
        pancakes = await store(cook_id, "Buttermilk Pancakes", flour)
        await search.index_recipe(pancakes)
        assert len(await search.query("pancakes", cook_id)) == 1

    async def test_rebuilding_recovers_an_index_that_fell_behind(
        self, cook_id: int, flour: int
    ) -> None:
        """The index is derived, so it is rebuilt at start-up rather than migrated. That is
        what makes a change to *what* is indexed cost nothing to roll out — and what makes
        an index that somehow fell behind heal itself rather than needing a repair tool."""
        pancakes = await store(cook_id, "Buttermilk Pancakes", flour)
        await search.remove(pancakes)
        assert await search.query("pancakes", cook_id) == []

        assert await search.reindex() == 1
        assert [hit.recipe_id for hit in await search.query("pancakes", cook_id)] == [pancakes]

    async def test_rebuilding_does_not_leave_the_old_index_behind(
        self, cook_id: int, flour: int
    ) -> None:
        await store(cook_id, "Buttermilk Pancakes", flour)
        await search.reindex()
        assert len(await search.query("pancakes", cook_id)) == 1
