"""Asking a real model to explain a word (UC-7.5, ADR-062).

Skipped unless a provider is configured. The stubbed tests next door cover what the engine
does with an answer; this covers what no stub can — whether a real model, given these
instructions and this shape, writes something a cook could actually use, and whether it
stays off the ground ADR-062 puts out of bounds.

    QUOOKLY_INFERENCE_BASE_URL=http://localhost:8000/v1 \\
    QUOOKLY_INFERENCE_MODEL=your-model \\
    just backend test -- -m live
"""

import pytest

from quookly.contracts.academy import Wording
from quookly.engines import explanation
from quookly.utilities.configuration import get_settings

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def a_model_is_configured() -> None:
    get_settings.cache_clear()
    if not get_settings().inference_base_url:
        pytest.skip("no QUOOKLY_INFERENCE_BASE_URL configured")


@pytest.fixture(scope="module")
async def written() -> Wording:
    return await explanation.explain("spatchcock", "en-GB")


async def test_it_explains_the_word_that_was_asked_about(written: Wording) -> None:
    said = f"{written.summary} {written.explanation}".lower()
    assert "backbone" in said or "flat" in said


async def test_it_is_a_paragraph_rather_than_an_essay(written: Wording) -> None:
    """The reader met this word mid-recipe. Three sentences they can act on beats a page
    they will not read standing at a hob."""
    assert len(written.explanation) < 900


async def test_it_answers_to_the_word_a_step_would_use(written: Wording) -> None:
    assert "spatchcock" in {one.casefold() for one in [written.name, *written.spellings]}


async def test_it_does_not_write_about_what_a_food_contains() -> None:
    """The instruction half of ADR-062, against a real model. Allergens are computed from
    the registry and read from there; a sentence here that disagrees is worse than none.
    """
    said = await explanation.explain("blanch", "en-GB")
    prose = f"{said.summary} {said.explanation} {said.caution or ''}".lower()
    assert "allergen" not in prose
    assert "gluten-free" not in prose


async def test_it_reads_a_word_the_way_a_recipe_uses_it() -> None:
    """`fold` is a laundry word too, and the Academy is not about laundry."""
    said = await explanation.explain("fold", "en-GB")
    prose = f"{said.summary} {said.explanation}".lower()
    assert "laundry" not in prose and "towel" not in prose


async def test_it_writes_in_the_language_it_was_asked_in() -> None:
    """A cook reading in German wants a German page, not an English one to translate."""
    said = await explanation.explain("unterheben", "de-CH")
    assert any(word in said.explanation.lower() for word in ("der", "die", "das", "und", "mit"))
