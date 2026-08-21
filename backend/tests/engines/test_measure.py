"""Quantities, units, and conversion between them (V4).

MeasureEngine is a rule engine: a pure function of its arguments, with no I/O. Densities
and preferences arrive as parameters, which is what makes this file a table of cases
rather than a set of fixtures.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from quookly.contracts.eater import AgeBand, Eater
from quookly.contracts.errors import DensityRequired, IncompatibleUnits, PortionsUnknown
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Dimension, Quantity, Unit
from quookly.contracts.preferences import UnitPreferences
from quookly.engines import measure

# g/ml. Water is 1 by definition; flour is famously not, which is why a cup of it is a
# bad way to measure.
WATER = Decimal("1.0")
FLOUR = Decimal("0.53")


def q(magnitude: str, unit: Unit) -> Quantity:
    return Quantity(Decimal(magnitude), unit)


class TestDimensions:
    def test_mass_units_measure_mass(self) -> None:
        assert Unit.GRAM.dimension is Dimension.MASS
        assert Unit.POUND.dimension is Dimension.MASS

    def test_volume_units_measure_volume(self) -> None:
        assert Unit.MILLILITRE.dimension is Dimension.VOLUME
        assert Unit.CUP_US.dimension is Dimension.VOLUME

    def test_a_count_is_neither(self) -> None:
        assert Unit.PIECE.dimension is Dimension.COUNT


class TestConvertingWithinADimension:
    @pytest.mark.parametrize(
        ("magnitude", "source", "target", "expected"),
        [
            ("1", Unit.KILOGRAM, Unit.GRAM, "1000"),
            ("250", Unit.GRAM, Unit.KILOGRAM, "0.25"),
            ("1", Unit.LITRE, Unit.MILLILITRE, "1000"),
            # Swiss and German recipes are written in decilitres.
            ("2", Unit.DECILITRE, Unit.MILLILITRE, "200"),
            ("1", Unit.DECILITRE, Unit.CENTILITRE, "10"),
        ],
    )
    def test_metric_conversions_are_exact(
        self, magnitude: str, source: Unit, target: Unit, expected: str
    ) -> None:
        assert measure.convert(q(magnitude, source), target).magnitude == Decimal(expected)

    def test_ounces_convert_to_grams(self) -> None:
        converted = measure.convert(q("1", Unit.OUNCE), Unit.GRAM)
        assert converted.magnitude == pytest.approx(Decimal("28.3495"), abs=Decimal("0.001"))

    def test_pounds_convert_to_grams(self) -> None:
        converted = measure.convert(q("1", Unit.POUND), Unit.GRAM)
        assert converted.magnitude == pytest.approx(Decimal("453.592"), abs=Decimal("0.01"))

    def test_converting_to_its_own_unit_changes_nothing(self) -> None:
        original = q("120", Unit.GRAM)
        assert measure.convert(original, Unit.GRAM) == original

    def test_a_round_trip_returns_the_original(self) -> None:
        original = q("250", Unit.GRAM)
        there_and_back = measure.convert(measure.convert(original, Unit.OUNCE), Unit.GRAM)
        assert there_and_back.magnitude == pytest.approx(
            original.magnitude, abs=Decimal("0.000001")
        )


class TestTheUnitsThatQuietlyDisagree:
    """A cup is not a cup. Conflating them is a real recipe bug, so they are separate units."""

    def test_a_us_cup_is_not_a_metric_cup(self) -> None:
        us = measure.convert(q("1", Unit.CUP_US), Unit.MILLILITRE).magnitude
        metric = measure.convert(q("1", Unit.CUP_METRIC), Unit.MILLILITRE).magnitude
        assert us != metric
        assert metric == Decimal("250")
        assert us == pytest.approx(Decimal("236.588"), abs=Decimal("0.001"))

    def test_a_us_tablespoon_is_not_a_metric_tablespoon(self) -> None:
        us = measure.convert(q("1", Unit.TABLESPOON_US), Unit.MILLILITRE).magnitude
        metric = measure.convert(q("1", Unit.TABLESPOON_METRIC), Unit.MILLILITRE).magnitude
        assert metric == Decimal("15")
        assert us < metric

    def test_a_us_fluid_ounce_is_not_an_imperial_one(self) -> None:
        us = measure.convert(q("1", Unit.FLUID_OUNCE_US), Unit.MILLILITRE).magnitude
        imperial = measure.convert(q("1", Unit.FLUID_OUNCE_IMPERIAL), Unit.MILLILITRE).magnitude
        assert us != imperial


class TestConvertingBetweenMassAndVolume:
    def test_water_weighs_what_it_measures(self) -> None:
        converted = measure.convert(q("200", Unit.MILLILITRE), Unit.GRAM, density=WATER)
        assert converted.magnitude == Decimal("200.0")

    def test_flour_does_not(self) -> None:
        """The whole reason a cup of flour is a bad measurement."""
        converted = measure.convert(q("200", Unit.MILLILITRE), Unit.GRAM, density=FLOUR)
        assert converted.magnitude == Decimal("106.000")

    def test_mass_converts_back_to_volume(self) -> None:
        converted = measure.convert(q("106", Unit.GRAM), Unit.MILLILITRE, density=FLOUR)
        assert converted.magnitude == pytest.approx(Decimal("200"), abs=Decimal("0.001"))

    def test_without_a_density_it_refuses_rather_than_guesses(self) -> None:
        """Assuming water would silently misweigh every dry ingredient."""
        with pytest.raises(DensityRequired):
            measure.convert(q("200", Unit.MILLILITRE), Unit.GRAM)

    def test_a_density_of_zero_is_refused(self) -> None:
        with pytest.raises(DensityRequired):
            measure.convert(q("200", Unit.MILLILITRE), Unit.GRAM, density=Decimal("0"))


class TestConversionsThatCannotBeMade:
    def test_a_count_does_not_become_a_mass(self) -> None:
        """Three eggs weigh something, but not something this engine can know."""
        with pytest.raises(IncompatibleUnits):
            measure.convert(q("3", Unit.PIECE), Unit.GRAM, density=WATER)

    def test_a_mass_does_not_become_a_count(self) -> None:
        with pytest.raises(IncompatibleUnits):
            measure.convert(q("150", Unit.GRAM), Unit.PIECE)

    def test_the_error_names_both_units(self) -> None:
        with pytest.raises(IncompatibleUnits) as raised:
            measure.convert(q("3", Unit.PIECE), Unit.GRAM)
        assert "piece" in str(raised.value)
        assert "g" in str(raised.value)


class TestScaling:
    def test_halving_halves(self) -> None:
        assert measure.scale(q("200", Unit.GRAM), Decimal("0.5")) == q("100.0", Unit.GRAM)

    def test_scaling_keeps_the_unit(self) -> None:
        assert measure.scale(q("2", Unit.DECILITRE), Decimal("3")).unit is Unit.DECILITRE

    def test_a_fractional_factor_is_exact(self) -> None:
        """Appetite multipliers sum to things like 3.5, and floats would drift."""
        scaled = measure.scale(q("100", Unit.GRAM), Decimal("3.5"))
        assert scaled.magnitude == Decimal("350.0")

    def test_scaling_by_one_changes_nothing(self) -> None:
        original = q("175", Unit.GRAM)
        assert measure.scale(original, Decimal("1")) == original

    def test_a_negative_factor_is_refused(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            measure.scale(q("100", Unit.GRAM), Decimal("-1"))


class TestQuantities:
    def test_a_quantity_is_immutable(self) -> None:
        """Scaling returns a new quantity; nothing edits one in place."""
        quantity = q("100", Unit.GRAM)
        with pytest.raises(FrozenInstanceError):
            quantity.magnitude = Decimal("200")  # type: ignore[misc]

    def test_a_negative_quantity_is_refused(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            Quantity(Decimal("-1"), Unit.GRAM)

    def test_zero_is_allowed(self) -> None:
        """A recipe may legitimately call for none of something in a variant."""
        assert Quantity(Decimal("0"), Unit.GRAM).magnitude == Decimal("0")

    def test_decimal_arithmetic_does_not_drift(self) -> None:
        total = measure.scale(q("0.1", Unit.GRAM), Decimal("3"))
        assert total.magnitude == Decimal("0.3")


class TestRendering:
    """Turning a stored quantity into the one a particular cook wants to read (UC-2.2).

    Rendering is a *display* operation: it converts, tidies, and rounds. The stored
    quantity stays exact, because rounding on the way in would compound every time a
    recipe was scaled.
    """

    POWDERS_IN_GRAMS = UnitPreferences(
        {
            IngredientKind.POWDER: Unit.GRAM,
            IngredientKind.LIQUID: Unit.MILLILITRE,
            IngredientKind.SOLID: Unit.GRAM,
        }
    )

    def test_a_cup_of_flour_becomes_grams(self) -> None:
        """The founding annoyance: a cup of flour is a mass pretending to be a volume."""
        rendered = measure.render(
            q("1", Unit.CUP_US), IngredientKind.POWDER, FLOUR, self.POWDERS_IN_GRAMS
        )
        assert rendered == q("125", Unit.GRAM)

    def test_a_cup_of_water_becomes_millilitres(self) -> None:
        rendered = measure.render(
            q("1", Unit.CUP_US), IngredientKind.LIQUID, WATER, self.POWDERS_IN_GRAMS
        )
        assert rendered == q("237", Unit.MILLILITRE)

    def test_a_count_is_left_alone(self) -> None:
        """Three eggs are three eggs, whatever anybody prefers."""
        rendered = measure.render(
            q("3", Unit.PIECE), IngredientKind.COUNTABLE, None, self.POWDERS_IN_GRAMS
        )
        assert rendered == q("3", Unit.PIECE)

    def test_without_a_density_the_original_unit_stands(self) -> None:
        """Rendering must not fail a page. An unconvertible quantity is shown as written."""
        rendered = measure.render(
            q("1", Unit.CUP_US), IngredientKind.POWDER, None, self.POWDERS_IN_GRAMS
        )
        assert rendered.unit is Unit.CUP_US

    def test_a_kind_with_no_preference_keeps_its_unit(self) -> None:
        rendered = measure.render(
            q("2", Unit.TABLESPOON_METRIC), IngredientKind.COUNTABLE, None, UnitPreferences({})
        )
        assert rendered.unit is Unit.TABLESPOON_METRIC

    def test_a_decilitre_preference_is_honoured(self) -> None:
        """Swiss recipes are written in decilitres, and a cook who asks for them means it."""
        rendered = measure.render(
            q("500", Unit.MILLILITRE),
            IngredientKind.LIQUID,
            WATER,
            UnitPreferences({IngredientKind.LIQUID: Unit.DECILITRE}),
        )
        assert rendered == q("5", Unit.DECILITRE)


class TestHumanising:
    """Nobody writes 1500 g on a shopping list."""

    @pytest.mark.parametrize(
        ("magnitude", "unit", "expected_magnitude", "expected_unit"),
        [
            ("1500", Unit.GRAM, "1.5", Unit.KILOGRAM),
            ("2000", Unit.MILLILITRE, "2", Unit.LITRE),
            ("0.5", Unit.GRAM, "500", Unit.MILLIGRAM),
            ("999", Unit.GRAM, "999", Unit.GRAM),
            ("32", Unit.OUNCE, "2", Unit.POUND),
        ],
    )
    def test_magnitudes_move_to_a_readable_unit(
        self, magnitude: str, unit: Unit, expected_magnitude: str, expected_unit: Unit
    ) -> None:
        humanised = measure.humanise(q(magnitude, unit))
        assert humanised.unit is expected_unit
        assert humanised.magnitude == Decimal(expected_magnitude)

    def test_units_a_cook_chose_deliberately_are_left_alone(self) -> None:
        """Decilitres, cups and spoons are choices, not accidents of magnitude."""
        for unit in (Unit.DECILITRE, Unit.CUP_US, Unit.TABLESPOON_METRIC):
            assert measure.humanise(q("2000", unit)).unit is unit

    def test_zero_is_left_alone(self) -> None:
        assert measure.humanise(q("0", Unit.GRAM)) == q("0", Unit.GRAM)


class TestRounding:
    """Precision a cook can act on: nobody weighs 125.39 grams."""

    @pytest.mark.parametrize(
        ("magnitude", "expected"),
        [
            ("125.39", "125"),
            ("1234.56", "1235"),
            ("12.345", "12.3"),
            ("2.345", "2.35"),
            ("0.257", "0.26"),
            ("225", "225"),
        ],
    )
    def test_precision_falls_as_the_number_grows(self, magnitude: str, expected: str) -> None:
        assert measure.round_for_display(q(magnitude, Unit.GRAM)).magnitude == Decimal(expected)

    @pytest.mark.parametrize(
        ("magnitude", "expected"),
        [("2000", "2000 g"), ("1500", "1500 g"), ("1234.56", "1235 g"), ("12.30", "12.3 g")],
    )
    def test_a_rounded_quantity_reads_as_a_number(self, magnitude: str, expected: str) -> None:
        """Trailing zeros must not turn into an exponent. `2E+3 g` is not a quantity."""
        assert str(measure.round_for_display(q(magnitude, Unit.GRAM))) == expected

    def test_a_humanised_quantity_reads_as_a_number(self) -> None:
        assert str(measure.humanise(q("1500", Unit.GRAM))) == "1.5 kg"

    def test_rounding_never_reaches_zero_for_a_real_amount(self) -> None:
        """A pinch rounded to nothing would silently drop an ingredient."""
        rounded = measure.round_for_display(q("0.004", Unit.GRAM))
        assert rounded.magnitude > 0


def person(name: str, appetite: str) -> Eater:
    return Eater(id=1, cook_id=1, name=name, age_band=AgeBand.ADULT, appetite=Decimal(appetite))


class TestRequiredYield:
    """Portion sizing is part of V4: it changes for the same reason quantities do."""

    def test_one_standard_eater_needs_one_serving(self) -> None:
        assert measure.required_yield([person("Ana", "1")]) == q("1", Unit.SERVING)

    def test_multipliers_are_summed_rather_than_counted(self) -> None:
        """Four people where one eats half is 3.5 servings, not 4 (FR-18)."""
        table = [person(str(n), "1") for n in range(3)] + [person("Mira", "0.5")]
        assert measure.required_yield(table).magnitude == Decimal("3.5")

    def test_the_sum_is_exact(self) -> None:
        """0.3 + 1.4 + 0.6 is 2.3. In binary floats it is 2.3000000000000003."""
        table = [person("Toddler", "0.3"), person("Teen", "1.4"), person("Nonna", "0.6")]
        assert measure.required_yield(table).magnitude == Decimal("2.3")

    def test_one_large_appetite_is_not_rounded_to_a_head(self) -> None:
        assert measure.required_yield([person("Teen", "1.4")]).magnitude == Decimal("1.4")

    def test_cooking_for_nobody_is_refused(self) -> None:
        """A yield of zero would scale every ingredient out of the recipe."""
        with pytest.raises(ValueError):
            measure.required_yield([])


class TestScalingToAppetite:
    def test_a_recipe_for_four_shrinks_to_the_table(self) -> None:
        table = [person("Toddler", "0.3"), person("Teen", "1.4"), person("Nonna", "0.6")]
        assert measure.scaling_for(q("4", Unit.SERVING), table) == Decimal("0.575")

    def test_a_recipe_already_the_right_size_scales_by_one(self) -> None:
        assert measure.scaling_for(q("2", Unit.SERVING), [person("A", "1"), person("B", "1")]) == 1

    def test_a_recipe_measured_in_pieces_is_refused_when_it_does_not_say_who_it_feeds(
        self,
    ) -> None:
        """Nothing in "makes 12 pancakes" says how many of them feed one person.

        Guessing would misportion every meal planned from it, quietly.
        """
        with pytest.raises(PortionsUnknown):
            measure.scaling_for(q("12", Unit.PIECE), [person("Ana", "1")])

    def test_a_recipe_measured_in_pieces_scales_once_it_says_who_it_feeds(self) -> None:
        """Makes 12, serves 4. Six people at one portion each want one and a half times
        the recipe — and twelve pancakes never had to become a unit of appetite."""
        table = [person(f"Guest {n}", "1") for n in range(6)]

        assert measure.scaling_for(q("12", Unit.PIECE), table, Decimal("4")) == Decimal("1.5")

    def test_a_yield_in_servings_answers_for_itself(self) -> None:
        """`serves` is absent on such a recipe by construction, so nothing has to decide
        which of two numbers to believe."""
        assert measure.scaling_for(q("2", Unit.SERVING), [person("A", "1")]) == Decimal("0.5")

    def test_a_recipe_measured_in_grams_is_refused(self) -> None:
        with pytest.raises(PortionsUnknown):
            measure.scaling_for(q("900", Unit.GRAM), [person("Ana", "1")])

    def test_a_recipe_that_yields_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError):
            measure.scaling_for(q("0", Unit.SERVING), [person("Ana", "1")])
