"""What language a recipe is written in (Phase 8b, ADR-032).

Without this nothing downstream can tell a German recipe from an English one, and a
translation has no *from*. It is read rather than assumed: a page says so in `<html lang>`,
and where it does not, the honest answer is that nobody knows.
"""

from typing import Any

import pytest
from pytest import MonkeyPatch

from quookly.contracts.interpretation import InterpretedRecipe, Source
from quookly.contracts.web import ReadableContent
from quookly.engines import interpretation


def page(**overrides: Any) -> ReadableContent:
    return ReadableContent(
        url="https://example.test/pancakes",
        text="",
        title="Pancakes",
        structured=[
            {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "name": "Pancakes",
                "recipeYield": "Serves 4",
                "recipeIngredient": ["225 g plain flour", "2 eggs"],
                "recipeInstructions": [{"@type": "HowToStep", "text": "Whisk it all together."}],
            }
        ],
        **overrides,
    )


@pytest.fixture(autouse=True)
def no_editing(monkeypatch: MonkeyPatch) -> None:
    """The step-tidying pass wants a model. This is about the language, not the steps."""

    async def unchanged(steps: Any) -> Any:
        return steps

    monkeypatch.setattr(interpretation, "tidy_steps", unchanged)


class TestWhatThePageSays:
    async def test_a_page_that_says_english_gives_an_english_recipe(self) -> None:
        read = await interpretation.read_page(page(language="en"))
        assert read.language == "en"

    async def test_a_page_that_says_german_gives_a_german_recipe(self) -> None:
        read = await interpretation.read_page(page(language="de"))
        assert read.language == "de"

    async def test_a_page_that_says_nothing_leaves_it_unknown(self) -> None:
        """Absent rather than guessed. A recipe whose language nobody knows is one nothing
        can translate *from*, which is a better answer than translating from the wrong
        language."""
        read = await interpretation.read_page(page())
        assert read.language is None

    async def test_a_regional_tag_keeps_only_the_language(self) -> None:
        """`de-CH` and `de-DE` are the same language to translate out of, and a page that
        says `de_AT` is saying German with a different punctuation habit."""
        assert (await interpretation.read_page(page(language="de-AT"))).language == "de"
        assert (await interpretation.read_page(page(language="de_DE"))).language == "de"

    async def test_case_does_not_matter(self) -> None:
        assert (await interpretation.read_page(page(language="DE"))).language == "de"

    async def test_something_that_is_not_a_language_is_not_one(self) -> None:
        """Pages put all sorts of things in that attribute."""
        assert (await interpretation.read_page(page(language="  "))).language is None
        assert (await interpretation.read_page(page(language="javascript"))).language is None


class TestARecipeReadWithoutAPage:
    async def test_one_composed_here_has_no_language_of_its_own_to_read(self) -> None:
        """A model writing a recipe writes it in the language it was asked in, which the
        caller knows and this does not."""
        assert InterpretedRecipe(title="x", source=Source.MODEL).language is None
