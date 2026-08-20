"""Quantities, units, and conversion between them (V4).

MeasureEngine is a rule engine: a pure function of its arguments, with no I/O. Densities
and preferences arrive as parameters, which is what makes this file a table of cases
rather than a set of fixtures.
"""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from quookly.contracts.errors import DensityRequired, IncompatibleUnits
from quookly.contracts.measure import Dimension, Quantity, Unit
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
