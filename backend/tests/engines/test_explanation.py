"""Asking a model what a word means (UC-7.5, ADR-062).

A capability engine, so what is checked is **what it asks** and what it does with an
answer — not the answer itself, which is the model's.

The one thing here that is not ordinary prompt plumbing: what comes back is prose, and
prose is the only thing in this application that can state something untrue while looking
exactly like something true. So the engine's job is to constrain the shape and to refuse
an answer that is not one, and every judgement about whether it is *right* belongs to the
person who approves it.
"""

import json
from typing import Any

import pytest
from pytest import MonkeyPatch

from quookly.access import model as inference
from quookly.contracts.errors import NothingToExplain
from quookly.contracts.inference import Completion
from quookly.engines import explanation

ANSWER = {
    "name": "spatchcock",
    "spellings": ["spatchcocked", "butterflied"],
    "summary": "Flatten a bird so it cooks evenly.",
    "explanation": "Cut out the backbone with shears and press down on the breastbone.",
    "caution": "",
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
    async def test_it_asks_about_the_term(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await explanation.explain("spatchcock", "en-GB")
        assert "spatchcock" in asked["prompt"]

    async def test_it_asks_in_the_readers_language(self, monkeypatch: MonkeyPatch) -> None:
        """A cook reading in German wants a German page, not an English one to translate."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await explanation.explain("unterheben", "de-CH")
        assert "de-CH" in asked["prompt"] or "German" in (asked["system"] or "")

    async def test_it_says_this_is_about_cooking(self, monkeypatch: MonkeyPatch) -> None:
        """`fold` is a laundry word too, and the Academy is not about laundry."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await explanation.explain("fold", "en-GB")
        assert "cook" in (asked["system"] or "").lower()

    async def test_it_is_told_not_to_write_about_a_food(self, monkeypatch: MonkeyPatch) -> None:
        """The instruction half of ADR-062. The manager refuses the request outright, and
        this is what stops an answer drifting into one anyway."""
        asked: dict[str, Any] = {}
        answering(ANSWER, monkeypatch, asked)
        await explanation.explain("blanch", "en-GB")
        said = (asked["system"] or "").lower()
        assert "allergen" in said or "ingredient" in said


class TestWhatItDoesWithAnAnswer:
    async def test_it_reads_the_answer_back(self, monkeypatch: MonkeyPatch) -> None:
        answering(ANSWER, monkeypatch)
        written = await explanation.explain("spatchcock", "en-GB")
        assert written.name == "spatchcock"
        assert written.summary == "Flatten a bird so it cooks evenly."

    async def test_the_spellings_come_with_it(self, monkeypatch: MonkeyPatch) -> None:
        """What a step is matched against, once a person has approved it (ADR-055)."""
        answering(ANSWER, monkeypatch)
        written = await explanation.explain("spatchcock", "en-GB")
        assert written.spellings == ["spatchcocked", "butterflied"]

    async def test_an_empty_caution_is_no_caution(self, monkeypatch: MonkeyPatch) -> None:
        """A warning on every page is a warning on none, and a model asked for a field
        will fill it. Empty means absent rather than a sentence saying nothing."""
        answering(ANSWER, monkeypatch)
        assert (await explanation.explain("spatchcock", "en-GB")).caution is None

    async def test_a_caution_that_says_something_is_kept(self, monkeypatch: MonkeyPatch) -> None:
        answering({**ANSWER, "caution": "Never put water into hot fat."}, monkeypatch)
        written = await explanation.explain("deep-fry", "en-GB")
        assert written.caution == "Never put water into hot fat."

    async def test_the_term_asked_about_is_always_a_spelling(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Otherwise the page would not answer to the word that produced it, and the cook
        who asked would tap the same word again and be told nobody has explained it."""
        answering(ANSWER, monkeypatch)
        written = await explanation.explain("spatchcocking", "en-GB")
        assert "spatchcocking" in written.spellings

    async def test_it_does_not_repeat_a_spelling_it_already_has(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        answering(ANSWER, monkeypatch)
        written = await explanation.explain("butterflied", "en-GB")
        assert written.spellings.count("butterflied") == 1

    async def test_an_answer_with_no_explanation_is_not_one(self, monkeypatch: MonkeyPatch) -> None:
        """The shape a refusal takes. Storing it would put an empty page in the Academy and
        call it an explanation."""
        answering({**ANSWER, "explanation": ""}, monkeypatch)
        with pytest.raises(NothingToExplain):
            await explanation.explain("spatchcock", "en-GB")

    async def test_an_answer_with_no_summary_is_not_one(self, monkeypatch: MonkeyPatch) -> None:
        answering({**ANSWER, "summary": "   "}, monkeypatch)
        with pytest.raises(NothingToExplain):
            await explanation.explain("spatchcock", "en-GB")

    async def test_link_markup_does_not_survive_the_trip(self, monkeypatch: MonkeyPatch) -> None:
        """Only a person may say a word means a particular page (ADR-059), and prose is
        exactly where a model would try."""
        answering(
            {**ANSWER, "explanation": "Cut out the [[backbone|spine]] with shears."}, monkeypatch
        )
        written = await explanation.explain("spatchcock", "en-GB")
        assert written.explanation == "Cut out the spine with shears."
