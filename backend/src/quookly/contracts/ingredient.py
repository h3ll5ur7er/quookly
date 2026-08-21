"""The ingredient registry, as it travels between layers.

An ingredient is a registry entry — "unsalted butter", with a density and names per
locale. An *ingredient line* is a use of one inside a recipe. Keeping them separate is
what makes quantities convertible and stock matchable.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Origin(Enum):
    """Where a record came from.

    Upgrades may replace seeded records and must never touch a cook's own (ADR-016).
    """

    SEED = "seed"
    USER = "user"


class Allergen(Enum):
    """The allergen classes that must be declared on food sold in the EU and Switzerland.

    A fixed, externally defined list rather than free text: a constraint and an ingredient
    have to mean the same thing by "nuts" for a verdict to be worth anything. Anything
    outside these fourteen is avoided by ingredient instead.
    """

    GLUTEN = "gluten"
    CRUSTACEANS = "crustaceans"
    EGGS = "eggs"
    FISH = "fish"
    PEANUTS = "peanuts"
    SOYBEANS = "soybeans"
    MILK = "milk"
    TREE_NUTS = "tree_nuts"
    CELERY = "celery"
    MUSTARD = "mustard"
    SESAME = "sesame"
    SULPHITES = "sulphites"
    LUPIN = "lupin"
    MOLLUSCS = "molluscs"


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
    allergens: frozenset[Allergen] = frozenset()
    # Whether anybody has ever classified this ingredient's allergens. An empty set with
    # `classified=False` means "nobody has looked", which is a different fact from
    # "contains none" — and treating them alike is how unknown becomes safe (ADR-006).
    classified: bool = False
    #: What one of them weighs, for the countable ones. An egg has no grams until somebody
    #: says so, and composition tables publish per 100 g — so without this a recipe's eggs
    #: cannot be counted towards its nutrition. Absent rather than assumed: eggs come in
    #: four sizes and inventing one puts a number on a label that nobody measured.
    piece_grams: Decimal | None = None


class IngredientView(BaseModel):
    """A registry entry as a client reads it."""

    model_config = ConfigDict(frozen=True)

    id: int
    slug: str
    name: str
    kind: IngredientKind
