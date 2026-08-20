"""The ingredient registry, as it travels between layers.

An ingredient is a registry entry — "unsalted butter", with a density and names per
locale. An *ingredient line* is a use of one inside a recipe. Keeping them separate is
what makes quantities convertible and stock matchable.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Origin(Enum):
    """Where a record came from.

    Upgrades may replace seeded records and must never touch a cook's own (ADR-016).
    """

    SEED = "seed"
    USER = "user"


class IngredientKind(Enum):
    """What sort of thing this is, for the purpose of measuring it.

    This is the axis a cook's unit preferences run along: powders in grams, liquids in
    millilitres (UC-6.2). It is deliberately coarse — it exists to choose a unit, not to
    classify food.
    """

    LIQUID = "liquid"
    POWDER = "powder"
    SOLID = "solid"
    COUNTABLE = "countable"


@dataclass(frozen=True, slots=True)
class Ingredient:
    """A registry entry, with its name already resolved for one locale."""

    id: int
    slug: str
    kind: IngredientKind
    name: str
    density: Decimal | None
    origin: Origin
