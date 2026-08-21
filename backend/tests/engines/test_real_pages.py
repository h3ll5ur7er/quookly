"""Reading metadata captured from live recipe sites.

The fixture corpus the roadmap names as the mitigation for interpretation risk: real
pages, fetched once and kept, so a change to the reader is measured against what sites
actually publish rather than against what is convenient to invent.

These are the *metadata* blocks exactly as four publishers served them, with the page HTML
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
        because the recipe still looks complete."""
        recipe = read(name)
        measured = [line for line in recipe.lines if line.magnitude is not None]
        assert len(measured) >= len(recipe.lines) - 1, [
            line.written for line in recipe.lines if line.magnitude is None
        ]


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
