"""Quantities and the units they are expressed in.

A quantity is a magnitude and a unit. It says nothing about *what* is being measured —
that is the ingredient line's business — so the same types serve recipes, stock, and
shopping lists.

Magnitudes are `Decimal`. Appetite multipliers sum to values like 3.5 and recipes are
scaled repeatedly; binary floats drift, and a drifting quantity is a wrong recipe.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Dimension(Enum):
    """What kind of thing a unit measures. Conversion within one is always possible."""

    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"


class Unit(Enum):
    """A unit of measure.

    Units that are commonly conflated are kept separate on purpose. A US cup is 236.6 ml
    and a metric cup is 250 ml; treating them as one unit is a 6% error on every
    ingredient measured that way, which is the difference between a cake and a brick.
    """

    # Mass
    MILLIGRAM = ("mg", Dimension.MASS)
    GRAM = ("g", Dimension.MASS)
    KILOGRAM = ("kg", Dimension.MASS)
    OUNCE = ("oz", Dimension.MASS)
    POUND = ("lb", Dimension.MASS)

    # Volume, metric. Decilitres are how Swiss and German recipes are written.
    MILLILITRE = ("ml", Dimension.VOLUME)
    CENTILITRE = ("cl", Dimension.VOLUME)
    DECILITRE = ("dl", Dimension.VOLUME)
    LITRE = ("l", Dimension.VOLUME)
    TEASPOON_METRIC = ("tsp", Dimension.VOLUME)
    TABLESPOON_METRIC = ("tbsp", Dimension.VOLUME)
    CUP_METRIC = ("cup", Dimension.VOLUME)

    # Volume, the ones that disagree by region
    TEASPOON_US = ("tsp (US)", Dimension.VOLUME)
    TABLESPOON_US = ("tbsp (US)", Dimension.VOLUME)
    CUP_US = ("cup (US)", Dimension.VOLUME)
    FLUID_OUNCE_US = ("fl oz (US)", Dimension.VOLUME)
    FLUID_OUNCE_IMPERIAL = ("fl oz (imp)", Dimension.VOLUME)

    # Count
    PIECE = ("piece", Dimension.COUNT)

    def __init__(self, symbol: str, dimension: Dimension) -> None:
        self.symbol = symbol
        self.dimension = dimension

    def __str__(self) -> str:
        return self.symbol


@dataclass(frozen=True, slots=True)
class Quantity:
    """An amount of something, in a unit. Immutable: operations return a new quantity."""

    magnitude: Decimal
    unit: Unit

    def __post_init__(self) -> None:
        if self.magnitude < 0:
            raise ValueError(f"a quantity cannot be negative: {self.magnitude} {self.unit}")

    def __str__(self) -> str:
        return f"{self.magnitude} {self.unit.symbol}"
