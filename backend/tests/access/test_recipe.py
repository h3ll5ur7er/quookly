"""Recipes as structured data.

A recipe is a yield, an ordered set of ingredient lines pointing at registry entries, and
an ordered set of steps. It is never a title and a body of prose that happens to contain
a list — that shape cannot be scaled, converted, adapted or planned against, and
reproducing it is the failure this product exists to correct.
"""

from collections.abc import AsyncIterator
from dataclasses import replace
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import recipe as recipes
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.errors import IngredientNotRegistered
from quookly.contracts.execution import Attention
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
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
                attention=Attention.WAITING,
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

    async def test_what_each_step_asks_of_the_cook_survives_the_round_trip(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """The field the two times are derived from (ADR-037). Lost in storage, every
        recipe would report its baking as work."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert [step.attention for step in stored.steps] == [
            Attention.HANDS_ON,
            Attention.HANDS_ON,
            Attention.WAITING,
        ]

    async def test_every_step_of_every_recipe_in_one_query(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """What the list screen times its recipes from. Fetching each recipe whole to put
        a duration on a row would be several queries per row."""
        first = await recipes.store(shortbread(pantry), cook_id)
        second = await recipes.store(shortbread(pantry), cook_id)

        grouped = await recipes.steps_for_cook(cook_id)

        assert set(grouped) == {first.id, second.id}
        assert [step.instruction for step in grouped[first.id]] == [
            "Cream the butter.",
            "Work in the flour.",
            "Bake until pale gold.",
        ]

    async def test_another_cooks_steps_are_not_in_the_answer(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await recipes.store(shortbread(pantry), cook_id)
        other = await cook_access.register("other@example.com", "Someone", "hash")
        assert await recipes.steps_for_cook(other.id) == {}

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
                IngredientLineDraft(ingredient_id=9999, quantity=Quantity(Decimal("1"), Unit.GRAM))
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


class TestAllergensOnALine:
    """A recipe read back has to carry what is known about its ingredients.

    Without this a line's `allergens` is an empty set on every recipe, which reads as
    "contains none" to anybody who does not also check `classified` — the exact confusion
    ADR-006 exists to prevent.
    """

    async def test_a_line_carries_the_allergens_of_its_ingredient(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await registry.classify("plain-flour", frozenset({Allergen.GLUTEN}))
        stored = await recipes.store(shortbread(pantry), cook_id)
        fetched = await recipes.fetch(stored.id, "en-GB")
        assert fetched is not None
        flour = next(line for line in fetched.lines if line.ingredient.slug == "plain-flour")
        assert flour.ingredient.allergens == frozenset({Allergen.GLUTEN})
        assert flour.ingredient.classified is True

    async def test_an_unexamined_ingredient_says_so(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        fetched = await recipes.fetch(stored.id, "en-GB")
        assert fetched is not None
        assert all(line.ingredient.classified is False for line in fetched.lines)

    async def test_examined_and_clear_is_not_the_same_as_unexamined(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await registry.classify("plain-flour", frozenset())
        stored = await recipes.store(shortbread(pantry), cook_id)
        fetched = await recipes.fetch(stored.id, "en-GB")
        assert fetched is not None
        flour = next(line for line in fetched.lines if line.ingredient.slug == "plain-flour")
        assert flour.ingredient.allergens == frozenset()
        assert flour.ingredient.classified is True


class TestLinesToJudge:
    """What a verdict needs for a whole list of recipes, without loading any of them.

    The list is the most-visited screen, so this exists to keep it a fixed number of
    queries rather than a handful per recipe.
    """

    async def test_it_returns_a_line_per_ingredient(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        judged = await recipes.lines_to_judge(cook_id, ENGLISH)
        assert {line.slug for line in judged} == {"plain-flour", "unsalted-butter", "egg"}
        assert all(line.recipe_id == stored.id for line in judged)

    async def test_lines_carry_their_allergen_classification(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await registry.classify("plain-flour", frozenset({Allergen.GLUTEN}))
        await recipes.store(shortbread(pantry), cook_id)
        judged = await recipes.lines_to_judge(cook_id, ENGLISH)
        flour = next(line for line in judged if line.slug == "plain-flour")
        assert flour.allergens == frozenset({Allergen.GLUTEN})
        assert flour.classified is True

    async def test_an_unexamined_ingredient_says_so(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await recipes.store(shortbread(pantry), cook_id)
        judged = await recipes.lines_to_judge(cook_id, ENGLISH)
        assert all(line.classified is False for line in judged)

    async def test_lines_carry_the_name_a_finding_would_use(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await recipes.store(shortbread(pantry), cook_id)
        judged = await recipes.lines_to_judge(cook_id, ENGLISH)
        assert {line.name for line in judged} == {"plain flour", "unsalted butter", "egg"}

    async def test_optional_lines_are_marked(self, cook_id: int, pantry: dict[str, int]) -> None:
        """An avoidable violation is not a refusal, and the list must not report it as one."""
        await recipes.store(shortbread(pantry), cook_id)
        judged = await recipes.lines_to_judge(cook_id, ENGLISH)
        assert next(line for line in judged if line.slug == "egg").optional is True

    async def test_several_recipes_are_kept_apart(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        first = await recipes.store(shortbread(pantry), cook_id)
        second = await recipes.store(shortbread(pantry), cook_id)
        judged = await recipes.lines_to_judge(cook_id, ENGLISH)
        assert {line.recipe_id for line in judged} == {first.id, second.id}

    async def test_another_cooks_recipes_are_not_returned(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        await recipes.store(shortbread(pantry), cook_id)
        other = await cook_access.register("other@example.com", "Someone", "hash")
        assert await recipes.lines_to_judge(other.id, ENGLISH) == []


class TestRestating:
    """Editing a recipe (ADR-059).

    A recipe could be created and never changed: no update, no delete. A typo in an
    imported recipe was permanent, a misread quantity was permanent, and a bad import
    could only be lived with.

    Replacement rather than patching, because lines and steps are *ordered* collections.
    Patching one would mean an instruction for reordering, which is a language nobody
    asked for; sending the recipe as it should now read says the same thing with nothing
    to interpret.
    """

    async def test_the_title_can_be_corrected(self, cook_id: int, pantry: dict[str, int]) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        amended = replace(shortbread(pantry), title="Scottish Shortbread")
        restated = await recipes.restate(stored.id, amended, cook_id)
        assert restated is not None
        assert restated.title == "Scottish Shortbread"

    async def test_it_keeps_its_identity(self, cook_id: int, pantry: dict[str, int]) -> None:
        """The plans, cooked meals and shopping ticks pointing at it must still point."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        amended = replace(shortbread(pantry), title="Scottish Shortbread")
        restated = await recipes.restate(stored.id, amended, cook_id)
        assert restated is not None
        assert restated.id == stored.id

    async def test_a_step_can_be_rewritten(self, cook_id: int, pantry: dict[str, int]) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        amended = replace(
            shortbread(pantry), steps=[StepDraft(instruction="Rub the butter into the flour.")]
        )
        restated = await recipes.restate(stored.id, amended, cook_id)
        assert restated is not None
        assert [step.instruction for step in restated.steps] == ["Rub the butter into the flour."]

    async def test_a_line_can_be_removed(self, cook_id: int, pantry: dict[str, int]) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert len(stored.lines) == 3
        written = shortbread(pantry)
        amended = replace(written, lines=written.lines[:2])
        restated = await recipes.restate(stored.id, amended, cook_id)
        assert restated is not None
        assert len(restated.lines) == 2

    async def test_the_old_lines_do_not_linger(self, cook_id: int, pantry: dict[str, int]) -> None:
        """Replacement has to replace. Lines left behind would double the shopping list."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        written = shortbread(pantry)
        amended = replace(written, lines=[written.lines[0]], steps=[written.steps[0]])
        restated = await recipes.restate(stored.id, amended, cook_id)
        assert restated is not None
        assert len(restated.lines) == 1
        assert len(restated.steps) == 1

    async def test_the_order_it_was_sent_in_is_the_order_it_keeps(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        written = shortbread(pantry)
        amended = replace(written, lines=list(reversed(written.lines)))
        restated = await recipes.restate(stored.id, amended, cook_id)
        assert restated is not None
        assert [line.ingredient.id for line in restated.lines] == [
            line.ingredient_id for line in amended.lines
        ]

    async def test_where_it_came_from_is_not_rewritten(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """Provenance is where a recipe came from, not who last touched it. Editing an
        imported recipe does not make it authored — that is how it came in, for ever."""
        stored = await recipes.store(
            replace(shortbread(pantry), provenance=Provenance.IMPORTED_URL), cook_id
        )
        amended = replace(shortbread(pantry), provenance=Provenance.AUTHORED)
        restated = await recipes.restate(stored.id, amended, cook_id)
        assert restated is not None
        assert restated.provenance is Provenance.IMPORTED_URL

    async def test_another_cooks_recipe_is_absent_not_forbidden(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """The same rule reading one already follows: saying "forbidden" confirms it
        exists."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        other = await cook_access.register("other@example.com", "Other", "hash")
        assert await recipes.restate(stored.id, shortbread(pantry), other.id) is None

    async def test_a_recipe_that_is_not_there_is_absent(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        assert await recipes.restate(9999, shortbread(pantry), cook_id) is None


class TestArchiving:
    """Putting a recipe away rather than deleting it.

    A recipe is referenced by plans, by cooked meals and by shopping ticks. Deleting one
    would be the merge problem again with the same shape and less to repoint — and a
    cooked meal that lost its recipe is a hole in a history nobody can fill back in.
    Archived is reachable; deleted is not.
    """

    async def test_an_archived_recipe_leaves_the_cooks_list(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        await recipes.archive(stored.id, cook_id)
        assert [one.id for one in await recipes.list_for_cook(cook_id)] == []

    async def test_it_is_still_there_when_asked_for_by_name(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        """A plan that points at it must still resolve, which is the whole reason this is
        an archive and not a delete."""
        stored = await recipes.store(shortbread(pantry), cook_id)
        await recipes.archive(stored.id, cook_id)
        found = await recipes.fetch(stored.id, ENGLISH)
        assert found is not None
        assert found.title == "Shortbread"

    async def test_it_says_it_is_archived(self, cook_id: int, pantry: dict[str, int]) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert stored.archived_at is None
        await recipes.archive(stored.id, cook_id)
        found = await recipes.fetch(stored.id, ENGLISH)
        assert found is not None
        assert found.archived_at is not None

    async def test_it_can_be_brought_back(self, cook_id: int, pantry: dict[str, int]) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        await recipes.archive(stored.id, cook_id)
        await recipes.restore(stored.id, cook_id)
        assert [one.id for one in await recipes.list_for_cook(cook_id)] == [stored.id]

    async def test_archiving_twice_is_the_same_as_once(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        assert await recipes.archive(stored.id, cook_id) is True
        assert await recipes.archive(stored.id, cook_id) is True
        found = await recipes.fetch(stored.id, ENGLISH)
        assert found is not None and found.archived_at is not None

    async def test_another_cooks_recipe_cannot_be_archived(
        self, cook_id: int, pantry: dict[str, int]
    ) -> None:
        stored = await recipes.store(shortbread(pantry), cook_id)
        other = await cook_access.register("other@example.com", "Other", "hash")
        assert await recipes.archive(stored.id, other.id) is False
        found = await recipes.fetch(stored.id, ENGLISH)
        assert found is not None and found.archived_at is None
