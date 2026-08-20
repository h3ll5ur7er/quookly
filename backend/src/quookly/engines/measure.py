"""Conversion and scaling of quantities (V4).

A rule engine: pure functions of their arguments. Density and unit preferences arrive as
parameters rather than being fetched, which is what keeps this exhaustively testable and
usable identically by recipes, planning, shopping, and cooking.
"""

from decimal import ROUND_HALF_UP, Decimal

from quookly.contracts.errors import DensityRequired, IncompatibleUnits
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Dimension, Quantity, Unit
from quookly.contracts.preferences import UnitPreferences

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
    Unit.SERVING: Decimal("1"),
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
            f"converting {quantity.unit.symbol} to {target.symbol} needs a density; got {density!r}"
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


# Units that scale into one another when a magnitude gets awkward, smallest first. Units
# absent from every ladder — decilitres, cups, spoons — are left alone: a cook who asked
# for decilitres means decilitres, and 2000 of them is their business.
_LADDERS: tuple[tuple[tuple[Unit, Decimal], ...], ...] = (
    (
        (Unit.MILLIGRAM, Decimal("0.001")),
        (Unit.GRAM, Decimal("1")),
        (Unit.KILOGRAM, Decimal("1000")),
    ),
    ((Unit.MILLILITRE, Decimal("1")), (Unit.LITRE, Decimal("1000"))),
    ((Unit.OUNCE, Decimal("1")), (Unit.POUND, Decimal("16"))),
)


def _tidy(value: Decimal) -> Decimal:
    """Drop trailing zeros without letting the result become scientific notation.

    `Decimal.normalize()` turns 2000 into 2E+3, which is a correct number and an
    unreadable quantity.
    """
    tidied = value.normalize()
    _, _, exponent = tidied.as_tuple()
    return tidied.quantize(Decimal(1)) if isinstance(exponent, int) and exponent > 0 else tidied


def _ladder_for(unit: Unit) -> tuple[tuple[Unit, Decimal], ...] | None:
    return next((ladder for ladder in _LADDERS if any(u is unit for u, _ in ladder)), None)


def humanise(quantity: Quantity) -> Quantity:
    """Move a quantity to the unit a person would write it in.

    1500 g becomes 1.5 kg; half a gram becomes 500 mg. Only units on a ladder move, so a
    deliberate choice of decilitres or cups is never overridden.
    """
    ladder = _ladder_for(quantity.unit)
    if ladder is None or quantity.magnitude == 0:
        return quantity

    in_base = quantity.magnitude * next(size for unit, size in ladder if unit is quantity.unit)
    chosen_unit, chosen_size = ladder[0]
    for unit, size in ladder:
        if in_base >= size:
            chosen_unit, chosen_size = unit, size
    return Quantity(_tidy(in_base / chosen_size), chosen_unit)


def round_for_display(quantity: Quantity) -> Quantity:
    """Round to a precision a cook can act on.

    Nobody weighs 125.39 grams. Precision falls as the magnitude rises, and a real amount
    never rounds to nothing — an ingredient silently reduced to zero is worse than an
    awkward number.
    """
    magnitude = quantity.magnitude
    if magnitude == 0:
        return quantity

    places = 0 if magnitude >= 100 else 1 if magnitude >= 10 else 2
    rounded = magnitude.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if rounded == 0:
        # Too small to show at this precision, but present: keep the smallest step.
        rounded = Decimal(1).scaleb(-places)
    return Quantity(_tidy(rounded), quantity.unit)


def render(
    quantity: Quantity,
    kind: IngredientKind,
    density: Decimal | None,
    preferences: UnitPreferences,
) -> Quantity:
    """The quantity as a particular cook wants to read it (UC-2.2).

    Converts to their preferred unit for this kind of ingredient, tidies the unit, and
    rounds for display. This is presentation: the stored quantity stays exact, because
    rounding on the way in would compound every time the recipe was scaled.

    Nothing here raises. A quantity that cannot be converted — no density, or a count,
    which converts to nothing — is shown as it was written. A page that cannot render one
    line should not fail entirely.
    """
    target = preferences.for_kind(kind)
    converted = quantity
    if target is not None and target is not quantity.unit:
        try:
            converted = convert(quantity, target, density)
        except (IncompatibleUnits, DensityRequired):
            converted = quantity
    return round_for_display(humanise(converted))
