"""Editing a real page's method with a real model (UC-1.3).

Skipped unless a provider is configured. The stubbed tests next door cover what the engine
does with an answer; this covers the thing no stub can — whether a real model, given these
instructions, produces steps a cook can actually follow.

    QUOOKLY_INFERENCE_BASE_URL=http://localhost:8000/v1 \\
    QUOOKLY_INFERENCE_MODEL=your-model \\
    just backend test -- -m live

The assertions are about behaviour rather than wording, because the wording is the model's
and will differ between them. What must hold for any model worth pointing at: the parts of
a page that are not instructions do not survive, and the parts that change the result do.
"""

import json
from pathlib import Path

import pytest

from quookly.contracts.interpretation import InterpretedRecipe
from quookly.contracts.web import ReadableContent
from quookly.engines import interpretation
from quookly.utilities.configuration import get_settings

pytestmark = pytest.mark.live

PAGES = Path(__file__).parent.parent / "fixtures" / "pages"


def captured(name: str) -> ReadableContent:
    raw = json.loads((PAGES / f"{name}.json").read_text(encoding="utf-8"))
    return ReadableContent(
        url=raw["url"], text="", title=raw["title"], structured=raw["structured"]
    )


@pytest.fixture(autouse=True)
def a_model_is_configured() -> None:
    get_settings.cache_clear()
    if not get_settings().inference_base_url:
        pytest.skip("no QUOOKLY_INFERENCE_BASE_URL configured")


async def read(name: str) -> InterpretedRecipe:
    recipe = await interpretation.read_page(captured(name))
    assert recipe is not None
    return recipe


class TestWhatDoesNotSurvive:
    async def test_gathering_the_ingredients_is_not_a_step(self) -> None:
        """Allrecipes opens every method with it. It is a heading, not an instruction."""
        recipe = await read("allrecipes-old-fashioned-pancakes")
        assert all("gather" not in step.instruction.lower() for step in recipe.steps)

    async def test_the_sign_off_goes(self) -> None:
        recipe = await read("allrecipes-old-fashioned-pancakes")
        assert all("enjoy" not in step.instruction.lower() for step in recipe.steps)

    async def test_how_long_it_keeps_is_not_a_step(self) -> None:
        """BBC Good Food ends the brownies with a fortnight in an airtight container.
        Useful, and not something to be walked through at the hob."""
        recipe = await read("bbcgoodfood-chocolate-brownies")
        assert all("airtight" not in step.instruction.lower() for step in recipe.steps)


class TestWhatSurvives:
    async def test_a_warning_that_changes_the_result_stays(self) -> None:
        """The one thing this pass must never lose. A shorter method that dropped it would
        be a worse import than the wordy one it replaced."""
        recipe = await read("bbcgoodfood-chocolate-brownies")
        assert any("overmix" in step.instruction.lower() for step in recipe.steps)

    async def test_the_oven_temperature_stays(self) -> None:
        recipe = await read("bbcgoodfood-chocolate-brownies")
        assert any(step.temperature_celsius == 180 for step in recipe.steps)

    async def test_a_time_in_the_words_becomes_a_timer(self) -> None:
        """What the metadata path never had: the duration on the step it belongs to,
        rather than the whole dish's figure landing on the last one."""
        recipe = await read("jamieoliver-easy-pancakes")
        assert any(step.duration_seconds == 900 for step in recipe.steps)

    async def test_the_quantities_a_step_names_stay(self) -> None:
        recipe = await read("bbcgoodfood-chocolate-brownies")
        assert any(
            "185g" in step.instruction or "185 g" in step.instruction for step in recipe.steps
        )


class TestWhatItReadsLike:
    async def test_the_steps_get_shorter(self) -> None:
        """The complaint this pass exists to answer: a method written to be read on a sofa,
        several actions to a paragraph."""
        before = interpretation.read_metadata(captured("bbcgoodfood-classic-pancakes").structured)
        after = await read("bbcgoodfood-classic-pancakes")
        assert before is not None

        longest_before = max(len(step.instruction) for step in before.steps)
        longest_after = max(len(step.instruction) for step in after.steps)
        assert longest_after < longest_before / 2

    async def test_a_step_that_waits_is_its_own_step(self) -> None:
        """Which is what gives the waiting a timer, and what stops a cook holding a pan
        while they read three more sentences."""
        recipe = await read("bbcgoodfood-classic-pancakes")
        timed = [step for step in recipe.steps if step.duration_seconds is not None]
        assert timed
        assert all(len(step.instruction) < 160 for step in timed)

    async def test_it_writes_sentences_rather_than_notes(self) -> None:
        """ "Sift flour into bowl" is a telegram. A cook reading at arm's length reads
        words, and dropped articles cost more attention than they save."""
        recipe = await read("bbcgoodfood-classic-pancakes")
        assert any(
            " the " in step.instruction or " a " in step.instruction for step in recipe.steps
        )
