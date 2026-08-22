"""Asking a real model for a recipe (UC-1.4, UC-1.5).

Skipped unless a provider is configured. The stubbed tests next door cover what the engine
does with an answer; this covers what no stub can — whether a real model, given these
instructions and this shape, produces something the reader can actually use.

    QUOOKLY_INFERENCE_BASE_URL=http://localhost:8000/v1 \\
    QUOOKLY_INFERENCE_MODEL=your-model \\
    just backend test -- -m live
"""

import pytest

from quookly.contracts.interpretation import InterpretedRecipe
from quookly.contracts.measure import Unit
from quookly.engines import generation
from quookly.utilities.configuration import get_settings

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def a_model_is_configured() -> None:
    get_settings.cache_clear()
    if not get_settings().inference_base_url:
        pytest.skip("no QUOOKLY_INFERENCE_BASE_URL configured")


@pytest.fixture(scope="module")
async def written() -> InterpretedRecipe:
    return await generation.compose(
        ingredients=["spinach", "double cream", "plain flour"], serves=4
    )


class TestWhatComesBack:
    async def test_a_recipe_with_a_name(self, written: InterpretedRecipe) -> None:
        assert written.title

    async def test_it_says_how_much_it_makes(self, written: InterpretedRecipe) -> None:
        """Without this it cannot be scaled to a table, and it is refused before storing."""
        assert written.yield_magnitude is not None
        assert written.yield_unit is not None

    async def test_the_amounts_are_readable(self, written: InterpretedRecipe) -> None:
        """The whole division of labour: the model writes "400 g spinach" and the tested
        reader turns it into a quantity. If most lines come back unmeasured, the
        instructions have drifted."""
        measured = [line for line in written.lines if line.magnitude is not None]
        assert len(measured) >= len(written.lines) - 2

    async def test_the_names_are_things_a_registry_could_know(
        self, written: InterpretedRecipe
    ) -> None:
        """Short, plain, and without a bracketed aside — otherwise every generated recipe
        invents ingredients nobody has classified for allergens (ADR-029)."""
        for line in written.lines:
            assert "(" not in line.ingredient, line.ingredient
            assert len(line.ingredient.split()) <= 4, line.ingredient

    async def test_it_uses_what_it_was_given(self, written: InterpretedRecipe) -> None:
        named = " ".join(line.ingredient.lower() for line in written.lines)
        assert "spinach" in named

    async def test_it_is_metric(self, written: InterpretedRecipe) -> None:
        """A Swiss kitchen has scales, not cups."""
        imperial = {Unit.OUNCE, Unit.POUND, Unit.CUP_US, Unit.FLUID_OUNCE_US}
        assert not [line for line in written.lines if line.unit in imperial]

    async def test_there_is_a_method(self, written: InterpretedRecipe) -> None:
        assert len(written.steps) >= 3


class TestWhatItIsToldToAvoid:
    async def test_a_constraint_still_produces_a_recipe(self) -> None:
        """Note what this does **not** assert.

        An earlier version of this test asserted the constraint was honoured. It failed on
        the first live run: told plainly that a recipe must not contain milk, this model
        wrote one with parmesan in it.

        That is not a bug in this engine and asserting against it would be testing a
        model's obedience rather than this codebase's behaviour. It is exactly why the
        constraint goes in the prompt to change the *odds* and the verdict is taken
        afterwards from the resolved ingredients (ADR-006). `RecipeManager` refuses what
        came back, and the tests for that use a stub precisely so they cannot flake.

        What is worth checking live is that constraints do not break the asking.
        """
        written = await generation.compose(
            description="a quick weeknight pasta", constraints=["milk", "tree nuts"], serves=2
        )
        assert written.title
        assert written.lines


class TestWhenTheAnswerRunsAway:
    async def test_asking_again_is_enough_most_of_the_time(self) -> None:
        """Guided decoding sometimes loops on an array it cannot close. Bounding the arrays
        and asking again is what makes this a feature rather than a coin toss — so this
        asks several times and expects them all to land."""
        for _ in range(3):
            written = await generation.compose(description="something with rhubarb")
            assert written.title


class TestMakingAVersion:
    """UC-1.7. What is checked is that a version is still the same dish — a dairy-free
    shortbread that comes back as a salad has not answered the question."""

    async def shortbread(self, change: str) -> InterpretedRecipe:
        return await generation.vary(
            title="Shortbread",
            made="16 pieces",
            lines=[
                "225 g unsalted butter, softened",
                "110 g caster sugar",
                "340 g plain flour",
            ],
            steps=[
                "Cream the butter and sugar until pale.",
                "Work in the flour until it just comes together.",
                "Press into a tin and bake at 160 °C until the palest gold.",
            ],
            change=change,
        )

    async def test_the_change_is_made(self) -> None:
        varied = await self.shortbread("make it dairy-free")
        named = " ".join(line.ingredient.lower() for line in varied.lines)
        assert "butter" not in named or "dairy" in named, named

    async def test_it_is_still_the_same_dish(self) -> None:
        """The failure mode worth guarding: a version that quietly becomes something else."""
        varied = await self.shortbread("make it dairy-free")
        named = " ".join(line.ingredient.lower() for line in varied.lines)
        assert "flour" in named
        assert "sugar" in named

    async def test_it_is_named_as_a_version(self) -> None:
        varied = await self.shortbread("make it dairy-free")
        assert "shortbread" in varied.title.lower()

    async def test_a_substitution_rather_than_a_diet(self) -> None:
        varied = await self.shortbread("use olive oil instead of butter")
        named = " ".join(line.ingredient.lower() for line in varied.lines)
        assert "oil" in named
