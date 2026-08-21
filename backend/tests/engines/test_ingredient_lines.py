"""Reading an ingredient line (V2).

A pure function, so this file is a table of cases. The strings are taken from live pages —
BBC Good Food, Allrecipes and Jamie Oliver — rather than invented, because the point of
the exercise is the shapes real sites actually write.

The rule underneath every case: a quantity that cannot be read is left absent. A line
keeps its words and loses its number, rather than acquiring a guessed one.
"""

from decimal import Decimal

import pytest

from quookly.contracts.interpretation import InterpretedLine
from quookly.contracts.measure import Unit
from quookly.engines import interpretation


def read(text: str) -> InterpretedLine:
    line = interpretation.read_ingredient(text)
    assert line is not None, f"{text!r} read as nothing"
    return line


class TestFromLivePages:
    """Every string here was fetched from a real recipe page."""

    @pytest.mark.parametrize(
        ("written", "magnitude", "unit", "ingredient"),
        [
            ("100g plain flour", "100", Unit.GRAM, "plain flour"),
            ("300ml milk", "300", Unit.MILLILITRE, "milk"),
            ("125g plain flour", "125", Unit.GRAM, "plain flour"),
            ("250ml milk", "250", Unit.MILLILITRE, "milk"),
            ("1 large egg", "1", Unit.PIECE, "large egg"),
            ("3 large free-range eggs", "3", Unit.PIECE, "large free-range eggs"),
            ("1.5 cups all-purpose flour", "1.5", Unit.CUP_US, "all-purpose flour"),
            ("3.5 teaspoons baking powder", "3.5", Unit.TEASPOON_METRIC, "baking powder"),
            ("1 tablespoon white sugar", "1", Unit.TABLESPOON_METRIC, "white sugar"),
        ],
    )
    def test_it_reads_what_the_page_wrote(
        self, written: str, magnitude: str, unit: Unit, ingredient: str
    ) -> None:
        line = read(written)
        assert line.magnitude == Decimal(magnitude)
        assert line.unit is unit
        assert line.ingredient == ingredient

    def test_the_line_keeps_what_it_was_read_from(self) -> None:
        """So a cook can check a reading against the page rather than trusting it."""
        assert read("100g plain flour").written == "100g plain flour"


class TestNotesAfterTheComma:
    def test_a_preparation_is_separated_from_the_ingredient(self) -> None:
        line = read("225g unsalted butter, softened")
        assert line.ingredient == "unsalted butter"
        assert line.preparation == "softened"

    def test_a_qualifier_is_kept_rather_than_dropped(self) -> None:
        line = read("0.25 teaspoon salt, or more to taste")
        assert line.ingredient == "salt"
        assert line.preparation == "or more to taste"

    def test_a_line_that_is_only_a_purpose_keeps_it(self) -> None:
        """From BBC Good Food, verbatim: a line with no quantity at all."""
        line = read("oil or melted butter, for frying")
        assert line.ingredient == "oil or melted butter"
        assert line.preparation == "for frying"
        assert line.magnitude is None
        assert line.unit is None


class TestQuantitiesPeopleWrite:
    @pytest.mark.parametrize(
        ("written", "magnitude"),
        [
            ("1/2 cup sugar", "0.5"),
            ("1 1/2 cups sugar", "1.5"),
            ("½ cup sugar", "0.5"),
            ("1½ cups sugar", "1.5"),
            ("¾ cup sugar", "0.75"),
            ("2 cups sugar", "2"),
        ],
    )
    def test_fractions_are_read(self, written: str, magnitude: str) -> None:
        assert read(written).magnitude == Decimal(magnitude)

    def test_a_range_takes_the_smaller_amount(self) -> None:
        """You can always add more. A recipe that starts at the top of the range cannot
        be walked back."""
        line = read("2-3 tablespoons olive oil")
        assert line.magnitude == Decimal("2")

    def test_a_range_written_with_the_word_also_takes_the_smaller(self) -> None:
        assert read("2 to 3 tablespoons olive oil").magnitude == Decimal("2")


class TestUnitsThatDisagree:
    def test_a_cup_is_read_as_an_american_one(self) -> None:
        """A US cup is 236.6ml and a metric one is 250ml — a 6% error on everything
        measured that way. "Cup" is an American word in recipes, and reading it as the
        metric unit would be the quieter of two wrong answers rather than the right one.
        """
        assert read("1 cup flour").unit is Unit.CUP_US

    @pytest.mark.parametrize(
        ("written", "unit"),
        [
            ("2 tsp salt", Unit.TEASPOON_METRIC),
            ("2 tbsp oil", Unit.TABLESPOON_METRIC),
            ("2 oz butter", Unit.OUNCE),
            ("1 lb beef", Unit.POUND),
            ("1kg potatoes", Unit.KILOGRAM),
            ("2 dl cream", Unit.DECILITRE),
            ("1 litre stock", Unit.LITRE),
            ("2 fl oz milk", Unit.FLUID_OUNCE_US),
        ],
    )
    def test_the_rest_keep_what_quookly_already_means_by_them(
        self, written: str, unit: Unit
    ) -> None:
        assert read(written).unit is unit

    def test_a_plural_is_the_same_unit(self) -> None:
        assert read("200 grams flour").unit is Unit.GRAM


class TestVagueAmounts:
    """V2 names this case explicitly: "a knob of butter"."""

    @pytest.mark.parametrize(
        ("written", "ingredient", "preparation"),
        [
            ("a knob of butter", "butter", "a knob"),
            ("a pinch of salt", "salt", "a pinch"),
            ("a handful of parsley", "parsley", "a handful"),
            ("a splash of vinegar", "vinegar", "a splash"),
            ("A dash of Tabasco", "Tabasco", "A dash"),
        ],
    )
    def test_the_amount_becomes_a_note_and_the_ingredient_stays_clean(
        self, written: str, ingredient: str, preparation: str
    ) -> None:
        line = read(written)
        assert line.ingredient == ingredient
        assert line.preparation == preparation
        assert line.magnitude is None


class TestPurposesAndAdjectives:
    """Shapes a model produces when it is reading prose rather than copying a list."""

    @pytest.mark.parametrize(
        ("written", "ingredient", "preparation"),
        [
            ("a good pinch of salt", "salt", "a good pinch"),
            ("a generous knob of butter", "butter", "a generous knob"),
        ],
    )
    def test_an_adjective_belongs_to_the_hand_waving(
        self, written: str, ingredient: str, preparation: str
    ) -> None:
        line = read(written)
        assert line.ingredient == ingredient
        assert line.preparation == preparation

    @pytest.mark.parametrize(
        ("written", "ingredient", "preparation"),
        [
            ("butter for the pan", "butter", "for the pan"),
            ("olive oil for frying", "olive oil", "for frying"),
            ("icing sugar to dust", "icing sugar to dust", None),
            ("flour for dusting", "flour", "for dusting"),
            ("a knob of butter for the pan", "butter", "a knob, for the pan"),
        ],
    )
    def test_a_trailing_purpose_leaves_the_ingredient_resolvable(
        self, written: str, ingredient: str, preparation: str | None
    ) -> None:
        """ "butter for the pan" will never match a registry entry, and "butter" will."""
        line = read(written)
        assert line.ingredient == ingredient
        assert line.preparation == preparation

    def test_an_ordinary_name_is_not_carved_up(self) -> None:
        """ "Cream of tartar" is an ingredient, not a cream with a purpose."""
        assert read("2 tsp cream of tartar").ingredient == "cream of tartar"

    @pytest.mark.parametrize(
        "written",
        ["1 tbsp caster sugar — optional", "1 tbsp caster sugar (optional)"],
    )
    def test_optional_is_recognised_however_it_is_marked(self, written: str) -> None:
        assert read(written).optional is True


class TestWhatItWillNotGuess:
    def test_a_line_with_no_number_gets_no_number(self) -> None:
        line = read("unsalted butter")
        assert line.ingredient == "unsalted butter"
        assert line.magnitude is None
        assert line.unit is None

    def test_an_unrecognised_unit_leaves_the_line_unmeasured(self) -> None:
        """Better a line a cook can see is unread than a number that is wrong."""
        line = read("2 wineglasses of sherry")
        assert line.magnitude is None
        assert line.unit is None

    def test_and_the_words_are_all_still_there(self) -> None:
        assert read("2 wineglasses of sherry").written == "2 wineglasses of sherry"

    def test_an_empty_line_is_not_an_ingredient(self) -> None:
        assert interpretation.read_ingredient("   ") is None


class TestOptionalLines:
    @pytest.mark.parametrize(
        "written",
        ["100g walnuts (optional)", "100g walnuts, optional", "100g walnuts (Optional)"],
    )
    def test_a_line_marked_optional_is_marked_optional(self, written: str) -> None:
        line = read(written)
        assert line.optional is True
        assert line.ingredient == "walnuts"

    def test_an_ordinary_line_is_not(self) -> None:
        assert read("100g walnuts").optional is False
