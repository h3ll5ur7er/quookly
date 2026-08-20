"""Recipes as structured data.

A recipe is a yield, an ordered set of ingredient lines pointing at registry entries, and
an ordered set of steps. It is never a title and a body of prose that happens to contain
a list — that shape cannot be scaled, converted, adapted or planned against, and
reproducing it is the failure this product exists to correct.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import recipe as recipes
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.errors import IngredientNotRegistered
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.recipe import (
    IngredientLineDraft,
    Provenance,
    RecipeDraft,
    StepDraft,
    Visibility,
)
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


@pytest.fixture
async def pantry() -> dict[str, int]:
    """A few registry entries to point ingredient lines at."""
    entries = {}
    for slug, name, kind, density in [
        ("plain-flour", "plain flour", IngredientKind.POWDER, Decimal("0.53")),
        ("unsalted-butter", "unsalted butter", IngredientKind.SOLID, Decimal("0.911")),
        ("egg", "egg", IngredientKind.COUNTABLE, None),
    ]:
        created = await registry.register(
            slug=slug, kind=kind, density=density, names={ENGLISH: [name]}, origin=Origin.SEED
        )
        entries[slug] = created.id
    return entries


def shortbread(pantry: dict[str, int]) -> RecipeDraft:
    return RecipeDraft(
        title="Shortbread",
        summary="Three ingredients, one bowl.",
        yield_quantity=Quantity(Decimal("12"), Unit.PIECE),
        provenance=Provenance.AUTHORED,
        lines=[
            IngredientLineDraft(
                ingredient_id=pantry["plain-flour"],
                quantity=Quantity(Decimal("225"), Unit.GRAM),
                preparation="sifted",
            ),
            IngredientLineDraft(
                ingredient_id=pantry["unsalted-butter"],
                quantity=Quantity(Decimal("150"), Unit.GRAM),
                preparation="softened",
            ),
            IngredientLineDraft(
                ingredient_id=pantry["egg"],
                quantity=Quantity(Decimal("1"), Unit.PIECE),
                optional=True,
            ),
        ],
        steps=[
            StepDraft(instruction="Cream the butter."),
            StepDraft(instruction="Work in the flour.", duration_seconds=180),
            StepDraft(
                instruction="Bake until pale gold.",
                duration_seconds=2400,
                temperature_celsius=160,
            ),
        ],
    )


class TestStoring:
    async def test_a_stored_recipe_comes_back_whole(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        fetched = await recipes.fetch(stored.id, ENGLISH)
        assert fetched == stored

    async def test_ingredient_lines_keep_the_order_they_were_written_in(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """A recipe read out of order is a different recipe."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert [line.ingredient.slug for line in stored.lines] == [
            "plain-flour",
            "unsalted-butter",
            "egg",
        ]

    async def test_steps_keep_their_order(self, cook_id: int, pantry: dict[str, int]) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert [step.instruction for step in stored.steps] == [
            "Cream the butter.",
            "Work in the flour.",
            "Bake until pale gold.",
        ]

    async def test_a_recipe_is_private_until_published(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """FR-5: publishing is explicit."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.visibility is Visibility.PRIVATE

    async def test_provenance_is_recorded(self, cook_id: int, pantry: dict[str, int]) -> None:
        """How a recipe came to exist is worth knowing; its usefulness does not depend on it."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.provenance is Provenance.AUTHORED


class TestIngredientLines:
    async def test_a_line_points_at_a_registry_entry_not_a_string(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        flour = stored.lines[0]
        assert flour.ingredient.slug == "plain-flour"
        assert flour.ingredient.name == "plain flour"

    async def test_a_line_carries_the_density_needed_to_convert_it(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """This is what lets MeasureEngine turn 225 g of flour into millilitres."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.lines[0].ingredient.density == Decimal("0.53")

    async def test_quantities_survive_the_round_trip_exactly(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        fetched = await recipes.fetch(stored.id, ENGLISH)
        assert fetched is not None
        assert fetched.lines[0].quantity == Quantity(Decimal("225"), Unit.GRAM)

    async def test_a_preparation_note_belongs_to_the_line(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """'Softened' is about this use of butter, not about butter."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.lines[1].preparation == "softened"

    async def test_an_optional_line_says_so(self, cook_id: int, pantry: dict[str, int]) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.lines[2].optional is True
        assert stored.lines[0].optional is False


class TestSteps:
    async def test_a_timed_step_carries_its_duration(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """Cooking mode derives its timers from this rather than from parsing prose."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.steps[1].duration_seconds == 180

    async def test_an_untimed_step_has_no_duration(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.steps[0].duration_seconds is None

    async def test_a_temperature_is_structured_not_buried_in_the_text(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.steps[2].temperature_celsius == 160


class TestFetching:
    async def test_an_unknown_recipe_is_absent_not_an_error(self) -> None:
        assert await recipes.fetch(9999, ENGLISH) is None

    async def test_a_cook_sees_their_own_recipes(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await recipes.store(shortbread(pantry), cook_id)
        listed = await recipes.list_for_cook(cook_id)
        assert [summary.title for summary in listed] == ["Shortbread"]

    async def test_a_cook_does_not_see_another_cooks_recipes(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """Private by default means private from other accounts, not merely unpublished."""
        await recipes.store(shortbread(pantry), cook_id)
        other = await cook_access.register("other@example.com", "Someone", "hash")
        assert await recipes.list_for_cook(other.id) == []


class TestUnregisteredIngredients:
    async def test_a_line_pointing_at_nothing_is_refused(self, cook_id: int) -> None:
        """FR-9: an unresolvable ingredient is reported, never silently dropped."""
        draft = RecipeDraft(
            title="Ghost",
            yield_quantity=Quantity(Decimal("1"), Unit.PIECE),
            provenance=Provenance.AUTHORED,
            lines=[
                IngredientLineDraft(
                    ingredient_id=9999, quantity=Quantity(Decimal("1"), Unit.GRAM)
                )
            ],
            steps=[StepDraft(instruction="Do it.")],
        )
        with pytest.raises(IngredientNotRegistered):
            await recipes.store(draft, cook_id)


class TestDrafts:
    def test_a_recipe_needs_at_least_one_ingredient(self, pantry: dict[str, int]) -> None:
        with pytest.raises(ValueError):
            RecipeDraft(
                title="Nothing",
                yield_quantity=Quantity(Decimal("1"), Unit.PIECE),
                provenance=Provenance.AUTHORED,
                lines=[],
                steps=[StepDraft(instruction="Wait.")],
            )

    def test_a_recipe_needs_at_least_one_step(self, pantry: dict[str, int]) -> None:
        with pytest.raises(ValueError):
            RecipeDraft(
                title="Nothing",
                yield_quantity=Quantity(Decimal("1"), Unit.PIECE),
                provenance=Provenance.AUTHORED,
                lines=[
                    IngredientLineDraft(
                        ingredient_id=pantry["egg"], quantity=Quantity(Decimal("1"), Unit.PIECE)
                    )
                ],
                steps=[],
            )
