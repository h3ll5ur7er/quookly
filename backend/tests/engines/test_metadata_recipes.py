"""Reading a schema.org Recipe block (V2, ADR-028).

Checked against live pages, the major publishers embed one of these, and it beats any
reading of the surrounding article: the ingredient list is already a list, the steps are
already in order, and nobody had to guess which paragraph was preamble.

Believing it is still a judgement, and this is where that judgement lives. The blocks
below are shaped the way real sites shape them, including the ways they disagree with each
other about what a field holds.
"""

from decimal import Decimal
from typing import Any

import pytest

from quookly.contracts.execution import Attention
from quookly.contracts.interpretation import Source
from quookly.contracts.measure import Unit
from quookly.engines import interpretation


def block(**overrides: Any) -> dict[str, Any]:
    """A recipe block shaped the way BBC Good Food shapes one."""
    return {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Classic pancakes",
        "description": "A foolproof batter.",
        "recipeYield": "Makes 8 pancakes",
        "recipeIngredient": ["100g plain flour", "1 large egg", "300ml milk"],
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Sift the flour into a bowl."},
            {"@type": "HowToStep", "text": "Whisk in the egg and milk."},
        ],
        **overrides,
    }


class TestFindingIt:
    def test_the_recipe_block_is_picked_out_of_the_page(self) -> None:
        """A page carries several blocks; only one of them is the recipe."""
        blocks = [{"@type": "BreadcrumbList"}, {"@type": "WebSite"}, block()]
        read = interpretation.read_metadata(blocks)
        assert read is not None
        assert read.title == "Classic pancakes"

    def test_a_page_with_no_recipe_block_gives_nothing(self) -> None:
        assert interpretation.read_metadata([{"@type": "WebSite"}]) is None

    def test_a_type_written_as_a_list_is_still_a_recipe(self) -> None:
        """Some sites publish `"@type": ["Recipe", "NewsArticle"]`."""
        read = interpretation.read_metadata([block(**{"@type": ["Recipe", "NewsArticle"]})])
        assert read is not None

    def test_a_recipe_nested_in_a_graph_is_found(self) -> None:
        """`@graph` is how a page publishes several linked entities at once."""
        blocks = [{"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, block()]}]
        read = interpretation.read_metadata(blocks)
        assert read is not None
        assert read.title == "Classic pancakes"

    def test_a_block_with_no_name_is_not_usable(self) -> None:
        """A recipe with no title cannot be listed, found, or told apart from another."""
        assert interpretation.read_metadata([block(name="")]) is None

    def test_a_block_with_no_ingredients_is_not_usable(self) -> None:
        """The ingredients are the recipe. Steps without them are an essay."""
        assert interpretation.read_metadata([block(recipeIngredient=[])]) is None


class TestWhatItReads:
    def test_it_says_where_it_came_from(self) -> None:
        read = interpretation.read_metadata([block()])
        assert read is not None
        assert read.source is Source.METADATA

    def test_the_ingredients_are_read_as_lines(self) -> None:
        read = interpretation.read_metadata([block()])
        assert read is not None
        assert [line.ingredient for line in read.lines] == ["plain flour", "large egg", "milk"]
        assert read.lines[0].magnitude == Decimal("100")
        assert read.lines[0].unit is Unit.GRAM

    def test_the_steps_keep_their_order(self) -> None:
        read = interpretation.read_metadata([block()])
        assert read is not None
        assert read.steps[0].instruction == "Sift the flour into a bowl."
        assert read.steps[1].instruction == "Whisk in the egg and milk."

    def test_plain_strings_are_accepted_as_steps(self) -> None:
        """Sites disagree about whether an instruction is an object or a string."""
        read = interpretation.read_metadata([block(recipeInstructions=["Mix.", "Fry."])])
        assert read is not None
        assert [step.instruction for step in read.steps] == ["Mix.", "Fry."]

    def test_a_single_block_of_prose_is_split_into_steps(self) -> None:
        """Some sites put the whole method in one string with line breaks in it."""
        read = interpretation.read_metadata(
            [block(recipeInstructions="Sift the flour.\nWhisk in the egg.\nFry.")]
        )
        assert read is not None
        assert len(read.steps) == 3

    def test_a_section_of_steps_is_flattened(self) -> None:
        """`HowToSection` is how a site groups "for the batter" and "to serve"."""
        read = interpretation.read_metadata(
            [
                block(
                    recipeInstructions=[
                        {
                            "@type": "HowToSection",
                            "name": "For the batter",
                            "itemListElement": [
                                {"@type": "HowToStep", "text": "Sift."},
                                {"@type": "HowToStep", "text": "Whisk."},
                            ],
                        },
                        {"@type": "HowToStep", "text": "Fry."},
                    ]
                )
            ]
        )
        assert read is not None
        assert [step.instruction for step in read.steps] == ["Sift.", "Whisk.", "Fry."]


class TestTheYield:
    @pytest.mark.parametrize(
        ("written", "magnitude", "unit"),
        [
            ("Makes 8 pancakes", "8", Unit.PIECE),
            ("8", "8", Unit.SERVING),
            (8, "8", Unit.SERVING),
            ("Serves 4", "4", Unit.SERVING),
            ("4 servings", "4", Unit.SERVING),
            ("12 muffins", "12", Unit.PIECE),
            # Jamie Oliver writes this, and it means eight pancakes.
            ("Makes 8", "8", Unit.PIECE),
            ("Makes 4 servings", "4", Unit.SERVING),
        ],
    )
    def test_it_reads_the_forms_sites_write(
        self, written: object, magnitude: str, unit: Unit
    ) -> None:
        read = interpretation.read_metadata([block(recipeYield=written)])
        assert read is not None
        assert read.yield_magnitude == Decimal(magnitude)
        assert read.yield_unit is unit

    def test_a_yield_it_cannot_read_is_left_absent(self) -> None:
        """Not one, and not four. A guessed yield misscales every quantity in the recipe."""
        read = interpretation.read_metadata([block(recipeYield="a generous amount")])
        assert read is not None
        assert read.yield_magnitude is None
        assert read.yield_unit is None

    def test_an_unqualified_makes_is_read_as_things_rather_than_portions(self) -> None:
        """The two mistakes are not equal. Calling portions "pieces" makes a recipe refuse
        to scale to a household, which a cook sees. Calling pieces "portions" makes it
        scale silently to a fraction of the batter."""
        read = interpretation.read_metadata([block(recipeYield="Makes 8")])
        assert read is not None
        assert read.yield_unit is Unit.PIECE

    def test_a_list_of_yields_takes_the_first(self) -> None:
        """Sites publish `["4", "4 servings"]` — the same number said twice."""
        read = interpretation.read_metadata([block(recipeYield=["4", "4 servings"])])
        assert read is not None
        assert read.yield_magnitude == Decimal("4")


class TestTimings:
    def test_a_cook_time_becomes_a_duration_on_the_last_step(self) -> None:
        """ISO-8601 durations are what schema.org uses, and a timer needs seconds."""
        read = interpretation.read_metadata([block(cookTime="PT30M")])
        assert read is not None
        assert read.steps[-1].duration_seconds == 1800

    def test_hours_and_minutes_are_both_read(self) -> None:
        read = interpretation.read_metadata([block(cookTime="PT1H30M")])
        assert read is not None
        assert read.steps[-1].duration_seconds == 5400

    def test_a_duration_it_cannot_read_is_left_absent(self) -> None:
        read = interpretation.read_metadata([block(cookTime="about half an hour")])
        assert read is not None
        assert read.steps[-1].duration_seconds is None

    def test_a_cook_time_is_time_the_cook_spends_waiting(self) -> None:
        """`cookTime` is the site saying how long it is in the oven. Read as work, an
        imported cake would claim ninety minutes of it (ADR-037)."""
        read = interpretation.read_metadata([block(cookTime="PT30M")])
        assert read is not None
        assert read.steps[-1].attention is Attention.WAITING
        assert all(step.attention is Attention.HANDS_ON for step in read.steps[:-1])


class TestWhatItWillNotDo:
    def test_html_in_a_step_is_stripped(self) -> None:
        """Sites embed markup in instruction text. A cook should not read a tag."""
        read = interpretation.read_metadata(
            [block(recipeInstructions=["<p>Sift the <b>flour</b>.</p>"])]
        )
        assert read is not None
        assert read.steps[0].instruction == "Sift the flour."

    def test_an_empty_step_is_dropped_rather_than_shown(self) -> None:
        read = interpretation.read_metadata([block(recipeInstructions=["Mix.", "   ", ""])])
        assert read is not None
        assert len(read.steps) == 1

    def test_an_empty_ingredient_is_dropped(self) -> None:
        read = interpretation.read_metadata([block(recipeIngredient=["100g flour", "", "  "])])
        assert read is not None
        assert len(read.lines) == 1


class TestHowManyItFeeds:
    """Sites express "makes 12, serves 4" by putting both in `recipeYield`, usually as a
    list. `read_yield` takes the first; the servings can be anywhere in it."""

    def test_a_list_carrying_both_gives_up_both(self) -> None:
        read = interpretation.read_metadata([block(recipeYield=["12 pancakes", "4 servings"])])

        assert read is not None
        assert (read.yield_magnitude, read.yield_unit) == (Decimal("12"), Unit.PIECE)
        assert read.serves == Decimal("4")

    def test_a_yield_already_in_portions_answers_for_itself(self) -> None:
        read = interpretation.read_metadata([block(recipeYield="Serves 4")])

        assert read is not None
        assert read.yield_unit is Unit.SERVING
        assert read.serves is None

    def test_a_site_that_only_counts_things_says_nothing_about_people(self) -> None:
        """Which is most of them, and absent is the honest answer."""
        read = interpretation.read_metadata([block(recipeYield="Makes 8 pancakes")])

        assert read is not None
        assert read.serves is None
