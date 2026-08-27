"""Translating a recipe's prose (Phase 8b, ADR-032, ADR-064).

A capability engine, the same shape as `InterpretationEngine` pointed at a different
question: what is checked is **what it asks** and what it does with an answer, never
whether the answer is a good translation. That is the reader's judgement, and a person's
correction is the mechanism for it (ADR-064).

The safety line is untouched, and that is the point of testing it here: no verdict has
ever consulted prose (ADR-006), so an entire feature can be built over machine-generated
text without any of it reaching the safety path.
"""

import json
from typing import Any

import pytest
from pytest import MonkeyPatch

from quookly.access import model as inference
from quookly.contracts.errors import NothingToTranslate
from quookly.contracts.inference import Completion
from quookly.contracts.translation import Translatable
from quookly.engines import translation

ORIGINAL = Translatable(
    title="Schokoladenkuchen",
    summary="Ein einfacher Kuchen.",
    steps=["Butter und Zucker schaumig rühren.", "Bei 180 °C backen."],
)

ANSWER = {
    "title": "Chocolate cake",
    "summary": "A simple cake.",
    "steps": ["Cream the butter and sugar.", "Bake at 180 °C."],
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


class TestWhatItAsks:
    async def test_it_says_both_languages(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await translation.render(ORIGINAL, "de", "en")
        assert "de" in asked["prompt"] and "en" in asked["prompt"]

    async def test_it_asks_for_the_whole_recipe_at_once(self, monkeypatch: MonkeyPatch) -> None:
        """One round trip, not one per step. A step translated alone loses what the step
        before it established — "it" is the batter, and only the whole recipe says so."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await translation.render(ORIGINAL, "de", "en")
        assert "Bei 180 °C backen." in asked["prompt"]
        assert "Butter und Zucker" in asked["prompt"]

    async def test_it_is_told_to_leave_the_numbers_alone(self, monkeypatch: MonkeyPatch) -> None:
        """Amounts, temperatures and times are stored as columns and rendered per cook.
        A model rewriting 180 °C into 350 °F inside prose would put a second, worse copy
        of a number the application already knows beside the one it renders."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await translation.render(ORIGINAL, "de", "en")
        said = (asked["system"] or "").lower()
        assert "number" in said or "amount" in said

    async def test_it_is_told_it_is_translating_rather_than_improving(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """A model asked for a recipe will write a better one. This one is not being asked
        for a recipe."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await translation.render(ORIGINAL, "de", "en")
        assert "translat" in (asked["system"] or "").lower()


class TestWhatItDoesWithAnAnswer:
    async def test_it_reads_the_answer_back(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        said = await translation.render(ORIGINAL, "de", "en")
        assert said.title == "Chocolate cake"
        assert said.steps == ["Cream the butter and sugar.", "Bake at 180 °C."]

    async def test_a_recipe_without_a_summary_gets_none(self, monkeypatch: MonkeyPatch) -> None:
        answering({**ANSWER, "summary": ""}, monkeypatch)
        assert (await translation.render(ORIGINAL, "de", "en")).summary is None

    async def test_an_answer_with_the_wrong_number_of_steps_is_refused(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """The one check worth making. A translation with a step missing is a recipe with
        a step missing, and pairing them up by position is the only thing that makes a
        stored translation usable at all."""
        answering({**ANSWER, "steps": ["Only one."]}, monkeypatch)
        with pytest.raises(NothingToTranslate):
            await translation.render(ORIGINAL, "de", "en")

    async def test_an_answer_with_no_title_is_refused(self, monkeypatch: MonkeyPatch) -> None:
        answering({**ANSWER, "title": "  "}, monkeypatch)
        with pytest.raises(NothingToTranslate):
            await translation.render(ORIGINAL, "de", "en")

    async def test_link_markup_does_not_survive_the_trip(self, monkeypatch: MonkeyPatch) -> None:
        """Only a person may say a word means a particular page (ADR-059)."""
        answering({**ANSWER, "steps": ["Sift the [[plain-flour|flour]].", "Bake."]}, monkeypatch)
        said = await translation.render(ORIGINAL, "de", "en")
        assert said.steps[0] == "Sift the flour."

    async def test_a_recipe_with_no_steps_needs_no_model(self, monkeypatch: MonkeyPatch) -> None:
        """Nothing to translate is not a failure, and it should not cost a round trip."""

        async def never(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("asked a model about nothing")

        monkeypatch.setattr(inference, "complete_structured", never)
        said = await translation.render(Translatable(title="Rösti"), "de", "en")
        assert said.title == "Rösti"
        assert said.steps == []


class TestTranslatingIntoTheLanguageItIsAlreadyIn:
    async def test_it_is_not_asked_for(self, monkeypatch: MonkeyPatch) -> None:
        """A German recipe read by a German cook needs nothing, and asking would spend a
        round trip to get back what was sent."""

        async def never(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("asked a model to translate German into German")

        monkeypatch.setattr(inference, "complete_structured", never)
        assert await translation.render(ORIGINAL, "de", "de") == ORIGINAL
