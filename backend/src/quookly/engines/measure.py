"""Conversion and scaling of quantities (V4).

A rule engine: pure functions of their arguments. Density and unit preferences arrive as
parameters rather than being fetched, which is what keeps this exhaustively testable and
usable identically by recipes, planning, shopping, and cooking.
"""

from decimal import Decimal

from quookly.contracts.errors import DensityRequired, IncompatibleUnits
from quookly.contracts.measure import Dimension, Quantity, Unit

# How many base units one of each unit is worth. Base units are the gram, the millilitre,
# and the piece. Exact where the definition is exact.
_IN_BASE_UNITS: dict[Unit, Decimal] = {
    # Mass, base gram
    Unit.MILLIGRAM: Decimal("0.001"),
    Unit.GRAM: Decimal("1"),
    Unit.KILOGRAM: Decimal("1000"),
    Unit.OUNCE: Decimal("28.349523125"),  # exact, by international definition
    Unit.POUND: Decimal("453.59237"),  # exact
    # Volume, base millilitre
    Unit.MILLILITRE: Decimal("1"),
    Unit.CENTILITRE: Decimal("10"),
    Unit.DECILITRE: Decimal("100"),
    Unit.LITRE: Decimal("1000"),
    Unit.TEASPOON_METRIC: Decimal("5"),
    Unit.TABLESPOON_METRIC: Decimal("15"),
    Unit.CUP_METRIC: Decimal("250"),
    Unit.TEASPOON_US: Decimal("4.92892159375"),
    Unit.TABLESPOON_US: Decimal("14.78676478125"),
    Unit.CUP_US: Decimal("236.5882365"),
    Unit.FLUID_OUNCE_US: Decimal("29.5735295625"),
    Unit.FLUID_OUNCE_IMPERIAL: Decimal("28.4130625"),
    # Count, base piece
    Unit.PIECE: Decimal("1"),
}

_BRIDGEABLE = frozenset({Dimension.MASS, Dimension.VOLUME})


def convert(quantity: Quantity, target: Unit, density: Decimal | None = None) -> Quantity:
    """Express `quantity` in `target`.

    Within a dimension this is arithmetic. Between mass and volume it needs the
    ingredient's `density` in grams per millilitre, and refuses without one rather than
    assuming water — an assumption that would misweigh every dry ingredient.

    A count converts to nothing: three eggs weigh something, but not something this
    engine can know.
    """
    if quantity.unit is target:
        return quantity

    source_dimension = quantity.unit.dimension
    target_dimension = target.dimension

    if source_dimension is target_dimension:
        in_base = quantity.magnitude * _IN_BASE_UNITS[quantity.unit]
        return Quantity(in_base / _IN_BASE_UNITS[target], target)

    if {source_dimension, target_dimension} != _BRIDGEABLE:
        raise IncompatibleUnits(
            f"cannot convert {quantity.unit.symbol} to {target.symbol}: "
            f"{source_dimension.value} and {target_dimension.value} do not correspond"
        )

    if density is None or density <= 0:
        raise DensityRequired(
            f"converting {quantity.unit.symbol} to {target.symbol} needs a density; "
            f"got {density!r}"
        )

    millilitres_or_grams = quantity.magnitude * _IN_BASE_UNITS[quantity.unit]
    if source_dimension is Dimension.VOLUME:
        in_grams = millilitres_or_grams * density
        return Quantity(in_grams / _IN_BASE_UNITS[target], target)
    in_millilitres = millilitres_or_grams / density
    return Quantity(in_millilitres / _IN_BASE_UNITS[target], target)


def scale(quantity: Quantity, factor: Decimal) -> Quantity:
    """Multiply a quantity, keeping its unit.

    The factor is a ratio — a doubled recipe, or the summed appetite multipliers of the
    people eating it.
    """
    if factor < 0:
        raise ValueError(f"cannot scale by a negative factor: {factor}")
    return Quantity(quantity.magnitude * factor, quantity.unit)
