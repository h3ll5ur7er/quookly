"""Reading metadata captured from live recipe sites.

The fixture corpus the roadmap names as the mitigation for interpretation risk: real
pages, fetched once and kept, so a change to the reader is measured against what sites
actually publish rather than against what is convenient to invent.

These are the *metadata* blocks exactly as the publishers served them, with the page HTML
discarded — the blocks are the part being read, and keeping four megabytes of markup to
test a parser would be keeping the wrong thing.

Refresh with the capture script when a site changes shape; a failure here after a refresh
is real news about the web, not a broken test.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from quookly.contracts.interpretation import InterpretedRecipe
from quookly.contracts.measure import Unit
from quookly.engines import interpretation

PAGES = Path(__file__).resolve().parents[1] / "fixtures" / "pages"


def captured(name: str) -> list[dict[str, Any]]:
    body = json.loads((PAGES / f"{name}.json").read_text(encoding="utf-8"))
    blocks: list[dict[str, Any]] = body["structured"]
    return blocks


def read(name: str) -> InterpretedRecipe:
    recipe = interpretation.read_metadata(captured(name))
    assert recipe is not None, f"{name} produced no recipe"
    return recipe


ALL_PAGES = [
    "bbcgoodfood-classic-pancakes",
    "bbcgoodfood-chocolate-brownies",
    "allrecipes-old-fashioned-pancakes",
    "jamieoliver-easy-pancakes",
    # Added after a cook reported what it did to their recipe. Its notes come in doubled
    # brackets, its garlic in cloves and its ginger by the inch — three shapes the reader
    # had no answer for, on one page.
    "woksoflife-hainanese-chicken-rice",
]


class TestEveryCapturedPage:
    @pytest.mark.parametrize("name", ALL_PAGES)
    def test_a_recipe_comes_out(self, name: str) -> None:
        assert read(name).title

    @pytest.mark.parametrize("name", ALL_PAGES)
    def test_it_has_ingredients_and_a_method(self, name: str) -> None:
        recipe = read(name)
        assert recipe.lines, "no ingredient lines"
        assert recipe.steps, "no method"

    @pytest.mark.parametrize("name", ALL_PAGES)
    def test_no_ingredient_line_is_empty(self, name: str) -> None:
        assert all(line.ingredient.strip() for line in read(name).lines)

    @pytest.mark.parametrize("name", ALL_PAGES)
    def test_a_measured_line_carries_both_halves_or_neither(self, name: str) -> None:
        """Half a *what* is wrong information rather than less of it."""
        for line in read(name).lines:
            assert (line.magnitude is None) == (line.unit is None), line.written

    @pytest.mark.parametrize("name", ALL_PAGES)
    def test_no_step_carries_markup(self, name: str) -> None:
        """Sites embed tags in instruction text; a cook should not be reading one."""
        assert all("<" not in step.instruction for step in read(name).steps)

    @pytest.mark.parametrize("name", ALL_PAGES)
    def test_most_lines_are_read_rather_than_given_up_on(self, name: str) -> None:
        """A reader that quietly gives up on half a page is worse than a broken one,
        because the recipe still looks complete.

        A proportion rather than "all but one". A long ingredient list has more lines that
        genuinely carry no number — ice, stock from the pot, salt to taste, a piece of
        ginger measured by the inch — and a fixed allowance made a page fail for being
        long rather than for being read badly.
        """
        recipe = read(name)
        unread = [line.written for line in recipe.lines if line.magnitude is None]
        assert len(unread) <= len(recipe.lines) // 4, unread


class TestWhatEachPageSays:
    """Specific facts, so a regression is legible rather than just a count going down."""

    def test_bbc_pancakes(self) -> None:
        recipe = read("bbcgoodfood-classic-pancakes")
        assert recipe.title == "Classic pancakes"
        assert recipe.yield_magnitude == 8
        assert recipe.yield_unit is Unit.PIECE
        flour = recipe.lines[0]
        assert flour.ingredient == "plain flour"
        assert flour.magnitude == 100
        assert flour.unit is Unit.GRAM
        # "oil or melted butter, for frying" — a line with no quantity at all.
        assert recipe.lines[-1].magnitude is None
        assert recipe.lines[-1].preparation == "for frying"

    def test_allrecipes_pancakes(self) -> None:
        recipe = read("allrecipes-old-fashioned-pancakes")
        assert recipe.yield_unit is Unit.SERVING
        flour = recipe.lines[0]
        assert flour.ingredient == "all-purpose flour"
        assert flour.magnitude == 1.5
        # A US site writing "cups" means US cups — 6% away from the metric one.
        assert flour.unit is Unit.CUP_US
        salt = next(line for line in recipe.lines if line.ingredient == "salt")
        assert salt.preparation == "or more to taste"

    def test_jamie_oliver_pancakes(self) -> None:
        recipe = read("jamieoliver-easy-pancakes")
        assert recipe.title == "Easy pancakes"
        # "Makes 8" — eight pancakes, not eight portions.
        assert recipe.yield_unit is Unit.PIECE
        assert [line.ingredient for line in recipe.lines[:3]] == [
            "large free-range eggs",
            "plain flour",
            "milk",
        ]

    def test_bbc_brownies(self) -> None:
        recipe = read("bbcgoodfood-chocolate-brownies")
        assert recipe.yield_magnitude == 16
        assert recipe.yield_unit is Unit.PIECE
        assert len(recipe.lines) == 8
        assert all(line.magnitude is not None for line in recipe.lines)


class TestTheShapesThisPageBrought:
    """One page, three failures, all of them about the ingredient's *name*.

    An unread quantity is a visible gap a cook can fill. A wrong name is not: "cloves
    garlic" resolves against no registry, so it is recorded as a new ingredient nobody has
    heard of and nobody has classified for allergens (ADR-029, ADR-006).
    """

    def named(self, name: str) -> dict[str, str | None]:
        return {line.ingredient: line.preparation for line in read(name).lines}

    def test_a_bracketed_note_does_not_end_up_in_the_name(self) -> None:
        lines = self.named("woksoflife-hainanese-chicken-rice")
        assert "chicken fat" in lines
        assert lines["chicken fat"] == "taken from the cavity of the chicken"

    def test_a_comma_inside_a_note_does_not_cut_the_name_in_half(self) -> None:
        lines = self.named("woksoflife-hainanese-chicken-rice")
        assert "neutral oil" in lines
        assert not any("such as vegetable" in name for name in lines)

    def test_garlic_is_garlic_rather_than_cloves_garlic(self) -> None:
        lines = self.named("woksoflife-hainanese-chicken-rice")
        assert "garlic" in lines
        assert not any("cloves garlic" in name for name in lines)

    def test_a_four_inch_piece_of_ginger_is_not_four_gingers(self) -> None:
        ginger = [
            line
            for line in read("woksoflife-hainanese-chicken-rice").lines
            if line.ingredient == "ginger" and line.magnitude is None
        ]
        assert ginger
        assert any("4-inch" in (line.preparation or "") for line in ginger)

    def test_only_the_lines_that_carry_no_number_are_unmeasured(self) -> None:
        """Named rather than counted, so a regression says which line stopped being read."""
        unmeasured = {
            line.ingredient
            for line in read("woksoflife-hainanese-chicken-rice").lines
            if line.magnitude is None
        }
        assert unmeasured == {"Ice", "Chicken stock", "ginger", "salt"}

    def test_every_name_is_something_a_registry_could_know(self) -> None:
        """The test that would have caught all three at once: no brackets, no commas, and
        short enough to be an ingredient rather than a sentence."""
        for line in read("woksoflife-hainanese-chicken-rice").lines:
            assert "(" not in line.ingredient, line.ingredient
            assert ")" not in line.ingredient, line.ingredient
            assert "," not in line.ingredient, line.ingredient
            assert len(line.ingredient.split()) <= 4, line.ingredient
