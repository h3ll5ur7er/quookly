"""Reading a recipe out of prose, when the page carries no metadata (V2, UC-1.3).

The blog case: a thousand words of childhood memory around forty of recipe. This is the
half of `InterpretationEngine` that mediates a model, which makes it a capability engine
rather than a rule engine — it is allowed to reach resource access, and an import-linter
contract names the rule engines explicitly so that stays a decision rather than a drift.

The division of labour is the point. **The model decides what is a recipe; the reader
decides what a quantity means.** The model is asked for ingredient lines as written, and
the same tested reader turns "0.25 teaspoon salt, or more to taste" into a quantity — so
there is one implementation of that, not two that disagree.
"""

import json
from decimal import Decimal
from typing import Any

import pytest
from pytest import MonkeyPatch

from quookly.access import model as inference
from quookly.contracts.errors import InferenceNotConfigured, NotARecipe
from quookly.contracts.inference import Completion
from quookly.contracts.interpretation import Source
from quookly.contracts.measure import Unit
from quookly.contracts.web import ReadableContent
from quookly.engines import interpretation

BLOG = """
My grandmother, on a windswept morning in 1962, first showed me the secret to pancakes.
It was a Tuesday. The kitchen smelled of rain and possibility.

Ingredients: 225g plain flour, 300ml milk, 2 eggs, a knob of butter.
Whisk the dry ingredients, beat in the milk and eggs, rest the batter, fry until set.
"""


def page(text: str = BLOG, structured: list[dict[str, Any]] | None = None) -> ReadableContent:
    return ReadableContent(
        url="https://example.com/pancakes",
        text=text,
        title="The Best Pancakes You Will Ever Make",
        structured=structured or [],
    )


ANSWER = {
    "title": "Pancakes",
    "summary": "A family batter.",
    "recipe_yield": "Makes 8",
    "serves": "",
    "ingredients": ["225g plain flour", "300ml milk", "2 eggs", "a knob of butter"],
    "steps": ["Whisk the dry ingredients.", "Rest the batter.", "Fry until set."],
}


def answering(
    body: dict[str, Any], monkeypatch: MonkeyPatch, capture: dict[str, Any] | None = None
) -> None:
    """Stand in for the model, and optionally record what it was asked."""

    async def respond(
        prompt: str, schema: dict[str, Any], **options: Any
    ) -> tuple[dict[str, Any], Completion]:
        if capture is not None:
            capture.update({"prompt": prompt, "schema": schema, **options})
        return body, Completion(text=json.dumps(body), model="a-model")

    monkeypatch.setattr(inference, "complete_structured", respond)


class TestReadingTheProse:
    async def test_a_recipe_comes_out(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        read = await interpretation.read_page(page())
        assert read.title == "Pancakes"

    async def test_it_says_a_model_read_it(self, monkeypatch: MonkeyPatch) -> None:
        """A recipe that came out wrong is a different investigation depending on whether
        the page lied in its metadata or a model misread its prose."""
        answering(ANSWER, monkeypatch)
        assert (await interpretation.read_page(page())).source is Source.MODEL

    async def test_the_same_reader_handles_the_quantities(self, monkeypatch: MonkeyPatch) -> None:
        """One implementation of "what does 225g mean", not two that drift apart."""
        answering(ANSWER, monkeypatch)
        read = await interpretation.read_page(page())
        flour = read.lines[0]
        assert flour.ingredient == "plain flour"
        assert flour.magnitude == 225
        assert flour.unit is Unit.GRAM

    async def test_a_vague_amount_stays_vague(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        butter = (await interpretation.read_page(page())).lines[-1]
        assert butter.ingredient == "butter"
        assert butter.preparation == "a knob"
        assert butter.magnitude is None

    async def test_the_yield_is_read_the_same_way(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        read = await interpretation.read_page(page())
        assert read.yield_magnitude == 8
        assert read.yield_unit is Unit.PIECE

    async def test_the_steps_survive_in_order(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        read = await interpretation.read_page(page())
        assert [step.instruction for step in read.steps] == [
            "Whisk the dry ingredients.",
            "Rest the batter.",
            "Fry until set.",
        ]


class TestWhatItAsksFor:
    async def test_it_asks_for_a_shape_rather_than_prose(self, monkeypatch: MonkeyPatch) -> None:
        """The model fills a shape; it does not author one (UC-1.3)."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await interpretation.read_prose(page())
        assert asked["schema"]["required"] == [
            "title",
            "recipe_yield",
            "serves",
            "ingredients",
            "steps",
        ]
        assert asked["schema"]["additionalProperties"] is False

    async def test_the_page_text_is_what_it_reads(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await interpretation.read_prose(page())
        assert "windswept morning in 1962" in asked["prompt"]

    async def test_a_very_long_page_is_cut_before_it_is_sent(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """A model has a context limit, and an answer cut short by it is refused. Better
        to send less than to be refused for sending too much."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await interpretation.read_page(page(text="x" * (interpretation.MOST_TEXT_SENT * 2)))
        assert len(asked["prompt"]) < interpretation.MOST_TEXT_SENT * 2

    async def test_it_is_told_not_to_invent(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await interpretation.read_prose(page())
        assert "invent" in asked["prompt"].lower() or "invent" in str(asked).lower()

    async def test_it_must_answer_about_the_yield_rather_than_omitting_it(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """An empty string means the page does not say, which is a different thing from
        not having looked — and a recipe with no yield cannot be scaled to a household."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await interpretation.read_prose(page())
        assert "recipe_yield" in asked["schema"]["required"]


class TestPagesThatAreNotRecipes:
    async def test_a_page_with_no_ingredients_is_reported(self, monkeypatch: MonkeyPatch) -> None:
        """Half a recipe is worse than an error: it looks complete on the screen."""
        answering({**ANSWER, "ingredients": []}, monkeypatch)
        with pytest.raises(NotARecipe):
            await interpretation.read_page(page())

    async def test_a_page_with_no_title_is_reported(self, monkeypatch: MonkeyPatch) -> None:
        answering({**ANSWER, "title": ""}, monkeypatch)
        with pytest.raises(NotARecipe):
            await interpretation.read_page(page())

    async def test_an_empty_page_is_not_sent_to_a_model_at_all(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Asking a model to read nothing produces an invented recipe."""

        async def refuse(*args: Any, **options: Any) -> tuple[dict[str, Any], Completion]:
            raise AssertionError("the model should not have been asked")

        monkeypatch.setattr(inference, "complete_structured", refuse)
        with pytest.raises(NotARecipe):
            await interpretation.read_page(page(text="   "))


class TestMetadataComesFirst:
    async def test_a_page_with_a_recipe_block_is_not_sent_to_a_model(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """The metadata is better and free. Asking anyway spends a model round trip to
        get a worse answer."""

        async def refuse(*args: Any, **options: Any) -> tuple[dict[str, Any], Completion]:
            raise AssertionError("the model should not have been asked")

        monkeypatch.setattr(inference, "complete_structured", refuse)
        block = {
            "@type": "Recipe",
            "name": "Classic pancakes",
            "recipeIngredient": ["100g plain flour"],
            "recipeInstructions": ["Whisk."],
        }
        read = await interpretation.read_page(page(structured=[block]))
        assert read.source is Source.METADATA

    async def test_an_unusable_block_falls_through_to_the_model(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """A block with no ingredients is an essay, not a recipe. The prose may still
        hold one."""
        answering(ANSWER, monkeypatch)
        block = {"@type": "Recipe", "name": "Pancakes", "recipeIngredient": []}
        read = await interpretation.read_page(page(structured=[block]))
        assert read.source is Source.MODEL


class TestWithoutAModel:
    async def test_a_page_with_metadata_still_reads(self, monkeypatch: MonkeyPatch) -> None:
        """An instance with no model configured is not a broken instance. It cannot read a
        blog, and it can still import from every site that publishes its recipes properly.
        """

        async def unconfigured(*args: Any, **options: Any) -> tuple[dict[str, Any], Completion]:
            raise InferenceNotConfigured("no provider")

        monkeypatch.setattr(inference, "complete_structured", unconfigured)
        block = {
            "@type": "Recipe",
            "name": "Classic pancakes",
            "recipeIngredient": ["100g plain flour"],
            "recipeInstructions": ["Whisk."],
        }
        read = await interpretation.read_page(page(structured=[block]))
        assert read.title == "Classic pancakes"

    async def test_a_page_without_metadata_says_why_it_cannot(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        async def unconfigured(*args: Any, **options: Any) -> tuple[dict[str, Any], Completion]:
            raise InferenceNotConfigured("no provider")

        monkeypatch.setattr(inference, "complete_structured", unconfigured)
        with pytest.raises(InferenceNotConfigured):
            await interpretation.read_page(page())


class TestHowManyItFeeds:
    """A page saying "Makes 12 pancakes (serves 4)" states two facts, and only the second
    lets the recipe be scaled to a table. Asked for separately, because a single field
    cannot hold both — and required, so an empty answer means the page did not say rather
    than that the model did not look."""

    async def test_a_page_that_says_both_carries_both(self, monkeypatch: MonkeyPatch) -> None:
        answering({**ANSWER, "recipe_yield": "Makes 12 pancakes", "serves": "4"}, monkeypatch)

        read = await interpretation.read_page(page())

        assert (read.yield_magnitude, read.yield_unit) == (Decimal("12"), Unit.PIECE)
        assert read.serves == Decimal("4")

    async def test_a_page_that_says_only_what_it_makes_says_nothing_about_people(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Absent, not guessed. A pieces-per-serving figure invented here would misportion
        every meal planned from the recipe, silently."""
        answering({**ANSWER, "recipe_yield": "Makes 12 pancakes", "serves": ""}, monkeypatch)

        read = await interpretation.read_page(page())

        assert read.serves is None

    async def test_a_yield_already_in_portions_answers_for_itself(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Carrying a second copy of the same number is how the two come to disagree."""
        answering({**ANSWER, "recipe_yield": "Serves 4", "serves": "4"}, monkeypatch)

        read = await interpretation.read_page(page())

        assert (read.yield_magnitude, read.yield_unit) == (Decimal("4"), Unit.SERVING)
        assert read.serves is None
