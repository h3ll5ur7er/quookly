"""Ingredient lines as sites really write them (V2, UC-1.3).

Every case here is a line off a page a cook actually imported. They are the two shapes the
reader had no answer for: a note in brackets, and a number that counts something other than
the ingredient.

The failure that matters is not an unread quantity — this codebase leaves those absent on
purpose. It is a **wrong name**: "cloves garlic" resolves against no registry, so importing
one recipe invents an ingredient nobody has heard of, unclassified for allergens.
"""

from decimal import Decimal

import pytest

from quookly.contracts.interpretation import InterpretedLine
from quookly.contracts.measure import Unit
from quookly.engines import interpretation


def read(written: str) -> InterpretedLine:
    line = interpretation.read_ingredient(written)
    assert line is not None
    return line


class TestNotesInBrackets:
    def test_a_bracketed_note_is_a_note(self) -> None:
        line = read("2 ounces chicken fat (taken from the cavity of the chicken)")
        assert line.ingredient == "chicken fat"
        assert line.preparation == "taken from the cavity of the chicken"
        assert line.magnitude == Decimal(2)

    def test_a_comma_inside_the_brackets_does_not_split_the_name(self) -> None:
        """The bug as reported: the name ended at the first comma, so half the note became
        the ingredient — "neutral oil ((such as vegetable"."""
        line = read("1 teaspoon neutral oil ((such as vegetable, canola, or avocado oil))")
        assert line.ingredient == "neutral oil"
        assert line.preparation == "such as vegetable, canola, or avocado oil"

    def test_doubled_brackets_are_one_pair(self) -> None:
        """A real site emits them. Left alone they end up in the ingredient's name."""
        line = read("3 cups uncooked white rice ((preferably jasmine rice, washed and drained))")
        assert line.ingredient == "uncooked white rice"
        assert line.preparation == "preferably jasmine rice, washed and drained"

    def test_brackets_that_do_not_match_are_still_a_note(self) -> None:
        """ "((… ) )" is what one page publishes. A reader that insisted on balance would
        put the whole apology in the ingredient's name."""
        line = read("3 fresh red chilies ((choose a chili with medium spice level) )")
        assert line.ingredient == "fresh red chilies"
        assert line.preparation == "choose a chili with medium spice level"

    def test_square_brackets_too(self) -> None:
        line = read("200 g flour [plain, not self-raising]")
        assert line.ingredient == "flour"
        assert line.preparation == "plain, not self-raising"

    def test_a_line_with_no_amount_keeps_its_note(self) -> None:
        line = read("Chicken stock ((from cooking the chicken))")
        assert line.ingredient == "Chicken stock"
        assert line.preparation == "from cooking the chicken"
        assert line.magnitude is None

    def test_a_bracketed_note_and_a_comma_note_are_both_kept(self) -> None:
        line = read("225 g unsalted butter (cold), cubed")
        assert line.ingredient == "unsalted butter"
        assert line.preparation is not None
        assert "cold" in line.preparation
        assert "cubed" in line.preparation

    def test_optional_is_still_read_rather_than_becoming_a_note(self) -> None:
        line = read("1 tsp vanilla extract (optional)")
        assert line.optional
        assert line.preparation is None

    def test_a_line_that_is_only_brackets_keeps_its_words(self) -> None:
        """Emptying the name would lose the ingredient, which is the one thing importing
        must never do."""
        line = read("(a splash of something)")
        assert line.ingredient


class TestCountingWords:
    @pytest.mark.parametrize(
        ("written", "count", "name"),
        [
            ("4 cloves garlic", 4, "garlic"),
            ("4-5 slices ginger", 4, "ginger"),
            ("2 sprigs thyme", 2, "thyme"),
            ("1 stick celery", 1, "celery"),
            ("2 cans chopped tomatoes", 2, "chopped tomatoes"),
            ("6 rashers streaky bacon", 6, "streaky bacon"),
            ("2 Zehen Knoblauch", 2, "Knoblauch"),
        ],
    )
    def test_the_thing_counted_is_not_the_ingredient(
        self, written: str, count: int, name: str
    ) -> None:
        line = read(written)
        assert line.magnitude == Decimal(count)
        assert line.unit is Unit.PIECE
        assert line.ingredient == name

    def test_what_was_counted_is_kept(self) -> None:
        """A slice is not a clove, and the shape a thing arrives in is worth a word."""
        line = read("4-5 slices ginger")
        assert line.preparation == "slices"

    @pytest.mark.parametrize(
        "written",
        ["2 gousses d'ail", "2 gousses d’ail", "2 cloves of garlic"],
    )
    def test_the_little_word_between_does_not_stick_to_the_name(self, written: str) -> None:
        """A French page types the typographic apostrophe. A pattern that only knows the
        straight one leaves an ingredient called "d’ail", which resolves against nothing."""
        line = read(written)
        assert line.ingredient in {"ail", "garlic"}
        assert line.magnitude == Decimal(2)

    def test_a_bare_count_is_unchanged(self) -> None:
        """No counting word, so nothing is taken out. The size and provenance adjectives
        are dropped later, where names are matched against the registry."""
        line = read("3 large free-range eggs")
        assert line.ingredient == "large free-range eggs"
        assert line.magnitude == Decimal(3)
        assert line.unit is Unit.PIECE


class TestASizeIsNotACount:
    def test_a_length_of_ginger_is_not_four_gingers(self) -> None:
        """The bug as reported. Four pieces of ginger is nine times the recipe, and a
        wrong number is worse than a visible gap because a cook cannot see it is wrong."""
        line = read("4-inch piece ginger ((roughly chopped))")
        assert line.magnitude is None
        assert line.ingredient == "ginger"
        assert line.preparation is not None
        assert "4-inch piece" in line.preparation
        assert "roughly chopped" in line.preparation

    def test_a_fractional_length(self) -> None:
        line = read("1.5-inch piece ginger")
        assert line.magnitude is None
        assert line.ingredient == "ginger"

    def test_centimetres_too(self) -> None:
        line = read("5 cm piece of ginger")
        assert line.magnitude is None
        assert line.ingredient == "ginger"

    def test_an_inch_that_is_a_real_amount_is_not_a_size(self) -> None:
        """ "2 inches of rain" is not a recipe line, but "4 slices" is, and the tell is the
        word after the measure rather than the measure itself."""
        line = read("4 slices ginger")
        assert line.magnitude == Decimal(4)
