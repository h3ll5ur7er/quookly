"""A cook's preferred unit per ingredient kind (UC-6.2).

Per kind, not per system: "metric" is not a fine enough answer to be useful in a kitchen,
where the same cook wants powders in grams and liquids in decilitres.
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import preferences as preference_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Unit
from quookly.utilities.configuration import get_settings


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


class TestDefaults:
    async def test_a_new_cook_gets_workable_defaults(self, cook_id: int) -> None:
        """An empty preference set would show scraped cups to a Swiss cook forever."""
        preferences = await preference_access.for_cook(cook_id)
        assert preferences.for_kind(IngredientKind.POWDER) is Unit.GRAM
        assert preferences.for_kind(IngredientKind.LIQUID) is Unit.MILLILITRE
        assert preferences.for_kind(IngredientKind.SOLID) is Unit.GRAM

    async def test_countables_are_counted(self, cook_id: int) -> None:
        preferences = await preference_access.for_cook(cook_id)
        assert preferences.for_kind(IngredientKind.COUNTABLE) is Unit.PIECE

    async def test_every_kind_has_a_default(self, cook_id: int) -> None:
        preferences = await preference_access.for_cook(cook_id)
        for kind in IngredientKind:
            assert preferences.for_kind(kind) is not None, kind


class TestChoosing:
    async def test_a_choice_is_remembered(self, cook_id: int) -> None:
        await preference_access.choose(cook_id, IngredientKind.LIQUID, Unit.DECILITRE)
        preferences = await preference_access.for_cook(cook_id)
        assert preferences.for_kind(IngredientKind.LIQUID) is Unit.DECILITRE

    async def test_choosing_again_replaces_rather_than_accumulates(self, cook_id: int) -> None:
        await preference_access.choose(cook_id, IngredientKind.LIQUID, Unit.DECILITRE)
        await preference_access.choose(cook_id, IngredientKind.LIQUID, Unit.LITRE)
        preferences = await preference_access.for_cook(cook_id)
        assert preferences.for_kind(IngredientKind.LIQUID) is Unit.LITRE

    async def test_choosing_one_kind_leaves_the_others_alone(self, cook_id: int) -> None:
        await preference_access.choose(cook_id, IngredientKind.LIQUID, Unit.DECILITRE)
        preferences = await preference_access.for_cook(cook_id)
        assert preferences.for_kind(IngredientKind.POWDER) is Unit.GRAM

    async def test_cooks_do_not_share_preferences(self, cook_id: int) -> None:
        """A household disagreeing about units is the normal case."""
        await preference_access.choose(cook_id, IngredientKind.LIQUID, Unit.DECILITRE)
        other = await cook_access.register("other@example.com", "Someone", "hash")
        preferences = await preference_access.for_cook(other.id)
        assert preferences.for_kind(IngredientKind.LIQUID) is Unit.MILLILITRE
