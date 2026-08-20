"""Allergen classification in the ingredient registry.

The distinction that matters here is between an ingredient classified as containing no
allergens and one nobody has ever looked at. They are different facts, and conflating them
is how "unknown" silently becomes "safe" (ADR-006).
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
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


async def add(slug: str, name: str, allergens: frozenset[Allergen] | None) -> None:
    await registry.register(
        slug=slug,
        kind=IngredientKind.POWDER,
        density=Decimal("0.5"),
        names={ENGLISH: [name]},
        origin=Origin.SEED,
        allergens=allergens,
    )


class TestClassifying:
    async def test_an_ingredient_can_be_classified_when_registered(self) -> None:
        await add("plain-flour", "plain flour", frozenset({Allergen.GLUTEN}))
        flour = await registry.resolve("plain flour", ENGLISH)
        assert flour is not None
        assert flour.allergens == frozenset({Allergen.GLUTEN})
        assert flour.classified is True

    async def test_an_ingredient_may_carry_several_allergens(self) -> None:
        await add("marzipan", "marzipan", frozenset({Allergen.TREE_NUTS, Allergen.EGGS}))
        marzipan = await registry.resolve("marzipan", ENGLISH)
        assert marzipan is not None
        assert marzipan.allergens == frozenset({Allergen.TREE_NUTS, Allergen.EGGS})


class TestTheDistinctionThatMatters:
    async def test_classified_as_containing_none_is_not_the_same_as_unclassified(self) -> None:
        """The whole basis of ADR-006, expressed in two rows."""
        await add("caster-sugar", "caster sugar", frozenset())
        await add("mystery-powder", "mystery powder", None)

        sugar = await registry.resolve("caster sugar", ENGLISH)
        mystery = await registry.resolve("mystery powder", ENGLISH)
        assert sugar is not None and mystery is not None

        assert sugar.allergens == frozenset()
        assert sugar.classified is True

        assert mystery.allergens == frozenset()
        assert mystery.classified is False

    async def test_an_ingredient_is_unclassified_until_somebody_looks(self) -> None:
        """A cook adding their own ingredient has not classified it by doing so."""
        await registry.register(
            slug="grandmothers-spice-mix",
            kind=IngredientKind.POWDER,
            density=Decimal("0.5"),
            names={ENGLISH: ["grandmother's spice mix"]},
        )
        mix = await registry.resolve("grandmother's spice mix", ENGLISH)
        assert mix is not None
        assert mix.classified is False


class TestClassifyingLater:
    async def test_an_unclassified_ingredient_can_be_classified(self) -> None:
        await add("mystery-powder", "mystery powder", None)
        await registry.classify("mystery-powder", frozenset({Allergen.PEANUTS}))

        mystery = await registry.resolve("mystery powder", ENGLISH)
        assert mystery is not None
        assert mystery.allergens == frozenset({Allergen.PEANUTS})
        assert mystery.classified is True

    async def test_classifying_replaces_rather_than_accumulates(self) -> None:
        await add("mystery-powder", "mystery powder", frozenset({Allergen.PEANUTS}))
        await registry.classify("mystery-powder", frozenset({Allergen.SESAME}))

        mystery = await registry.resolve("mystery powder", ENGLISH)
        assert mystery is not None
        assert mystery.allergens == frozenset({Allergen.SESAME})

    async def test_an_ingredient_can_be_classified_as_containing_nothing(self) -> None:
        await add("mystery-powder", "mystery powder", None)
        await registry.classify("mystery-powder", frozenset())

        mystery = await registry.resolve("mystery powder", ENGLISH)
        assert mystery is not None
        assert mystery.allergens == frozenset()
        assert mystery.classified is True


class TestFactsForTheEngine:
    async def test_facts_are_fetched_for_a_whole_recipe_at_once(self) -> None:
        """One query for a verdict, not one per ingredient."""
        await add("plain-flour", "plain flour", frozenset({Allergen.GLUTEN}))
        await add("caster-sugar", "caster sugar", frozenset())
        flour = await registry.resolve("plain flour", ENGLISH)
        sugar = await registry.resolve("caster sugar", ENGLISH)
        assert flour is not None and sugar is not None

        found = await registry.allergens_for([flour.id, sugar.id])
        assert found == {
            flour.id: (frozenset({Allergen.GLUTEN}), True),
            sugar.id: (frozenset(), True),
        }

    async def test_an_unclassified_ingredient_says_so(self) -> None:
        await add("mystery-powder", "mystery powder", None)
        mystery = await registry.resolve("mystery powder", ENGLISH)
        assert mystery is not None
        assert await registry.allergens_for([mystery.id]) == {mystery.id: (frozenset(), False)}
