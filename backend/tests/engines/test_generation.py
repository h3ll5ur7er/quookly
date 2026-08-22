"""Asking for a recipe that does not exist yet (V1, V3, UC-1.4, UC-1.5).

A capability engine, so what is checked is **what it asks** and what it does with an answer
— not the answer itself, which is the model's.

The division being defended: generation knows what to ask, and never what an answer means.
The shape that comes back is the same shape a page's recipe comes back in, so "what does
225 g mean" has one implementation however the words arrived.
"""

import json
from typing import Any

from pytest import MonkeyPatch

from quookly.access import model as inference
from quookly.contracts.errors import NotARecipe
from quookly.contracts.execution import Attention
from quookly.contracts.inference import Completion
from quookly.contracts.interpretation import Source
from quookly.contracts.measure import Unit
from quookly.engines import generation, interpretation

ANSWER = {
    "title": "Spinach and Ricotta Pie",
    "summary": "A Tuesday pie.",
    "recipe_yield": "Serves 4",
    "serves": "",
    "ingredients": ["400 g spinach", "250 g ricotta", "2 eggs", "salt, to taste"],
    "steps": [
        {"instruction": "Wilt the spinach.", "attention": "hands_on"},
        {"instruction": "Bake for 25 minutes.", "attention": "waiting"},
    ],
}


def answering(
    body: dict[str, Any], monkeypatch: MonkeyPatch, capture: dict[str, Any] | None = None
) -> None:
    async def complete_structured(
        prompt: str, schema: dict[str, Any], system: str | None = None, **asked_for: Any
    ) -> tuple[dict[str, Any], Completion]:
        if capture is not None:
            capture.update({"prompt": prompt, "schema": schema, "system": system})
        return body, Completion(text=json.dumps(body), model="test")

    monkeypatch.setattr(inference, "complete_structured", complete_structured)


class TestWhatItAsksFor:
    async def test_it_asks_for_the_same_shape_a_page_comes_back_in(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """One shape, because the reader that makes sense of it is one reader. A second
        spelling of "ingredients" would be a second set of parsing bugs."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await generation.compose(description="something with spinach")
        assert asked["schema"] is interpretation.RECIPE_SHAPE

    async def test_what_the_cook_asked_for_is_passed_on(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await generation.compose(description="something with spinach")
        assert "something with spinach" in asked["prompt"]

    async def test_the_ingredients_are_things_to_use_rather_than_the_only_things_allowed(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """A recipe constrained to five items and nothing else is a list, not a dish. The
        cook wants the spinach used up, not a meal of spinach."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await generation.compose(ingredients=["spinach", "ricotta"])
        assert "spinach, ricotta" in asked["prompt"]
        assert "use up" in asked["prompt"]
        assert "may be added" in asked["prompt"]

    async def test_constraints_are_stated_plainly(self, monkeypatch: MonkeyPatch) -> None:
        """In the prompt to improve the odds. The guarantee is the verdict afterwards —
        a model asserting "this is dairy-free" carries no weight (ADR-006)."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await generation.compose(constraints=["peanuts", "milk"])
        assert "must not contain: peanuts, milk" in asked["prompt"]

    async def test_how_many_it_is_for(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await generation.compose(description="a pie", serves=6)
        assert "serve 6" in asked["prompt"]

    async def test_it_is_told_to_write_amounts_a_reader_can_read(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """The whole division of labour rests on this: the model writes "225 g plain
        flour" and a tested reader turns it into a quantity."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await generation.compose(description="a pie")
        told = str(asked["system"]).lower()
        assert "metric" in told
        assert "to taste" in told

    async def test_it_is_told_not_to_invent_an_ingredient(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await generation.compose(description="a pie")
        assert "invent" in str(asked["system"]).lower()


class TestWhatItDoesWithTheAnswer:
    async def test_a_recipe_comes_out(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        written = await generation.compose(description="a pie")
        assert written.title == "Spinach and Ricotta Pie"
        assert written.source is Source.MODEL

    async def test_the_same_reader_handles_the_quantities(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        written = await generation.compose(description="a pie")
        spinach = written.lines[0]
        assert spinach.ingredient == "spinach"
        assert spinach.magnitude == 400
        assert spinach.unit is Unit.GRAM

    async def test_a_vague_amount_stays_vague(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        written = await generation.compose(description="a pie")
        salt = next(line for line in written.lines if line.ingredient == "salt")
        assert salt.magnitude is None

    async def test_the_yield_is_read_the_same_way(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        written = await generation.compose(description="a pie")
        assert written.yield_magnitude == 4
        assert written.yield_unit is Unit.SERVING

    async def test_what_each_step_asks_of_the_cook_comes_through(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        answering(ANSWER, monkeypatch)
        written = await generation.compose(description="a pie")
        assert [step.attention for step in written.steps] == [
            Attention.HANDS_ON,
            Attention.WAITING,
        ]

    async def test_a_time_in_a_step_is_not_read_here(self, monkeypatch: MonkeyPatch) -> None:
        """Steps arrive as written. Reading a duration out of them is the tidying pass's
        job, and doing it in two places would be two answers to one question."""
        answering(ANSWER, monkeypatch)
        written = await generation.compose(description="a pie")
        assert written.steps[1].duration_seconds is None


class TestWhenNothingUsableComesBack:
    async def test_an_answer_with_no_title(self, monkeypatch: MonkeyPatch) -> None:
        answering({**ANSWER, "title": ""}, monkeypatch)
        try:
            await generation.compose(description="a pie")
        except NotARecipe:
            return
        raise AssertionError("a recipe with no title is not a recipe")

    async def test_an_answer_with_no_ingredients(self, monkeypatch: MonkeyPatch) -> None:
        """The shape a model's refusal takes. Storing it would put an empty recipe in a
        cook's collection and call it generated."""
        answering({**ANSWER, "ingredients": []}, monkeypatch)
        try:
            await generation.compose(description="a pie")
        except NotARecipe:
            return
        raise AssertionError("a recipe with no ingredients is not a recipe")
