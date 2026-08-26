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
    #: Whether anybody has reviewed this entry. Distinct from `classified`, which is about
    #: what is *in* the ingredient: an entry an import invented is usable straight away but
    #: nobody has looked at what it claims to be (ADR-051).
    approved: bool = False
    #: What one of them weighs, for the countable ones. An egg has no grams until somebody
    #: says so, and composition tables publish per 100 g — so without this a recipe's eggs
    #: cannot be counted towards its nutrition. Absent rather than assumed: eggs come in
    #: four sizes and inventing one puts a number on a label that nobody measured.
    piece_grams: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RegistryPage:
    """One screen of the registry, and how much of it there is.

    The count is separate from the page because it answers a different question: the page
    says what to draw, the total says whether there is more. Nine hundred entries do not
    fit on a phone, and a list that cannot say how long it is cannot be paged through.
    """

    entries: list[Ingredient]
    total: int


class IngredientView(BaseModel):
    """A registry entry as a client reads it."""

    model_config = ConfigDict(frozen=True)

    id: int
    slug: str
    name: str
    kind: IngredientKind


class RegistryEntryView(BaseModel):
    """A registry entry as the registry screen reads it.

    Wider than `IngredientView`, which exists to point a recipe line at something and so
    carries only enough to recognise one. This carries what is needed to *judge* an
    entry: the three fields an import guesses at — kind, density, origin — and whether
    anybody has classified its allergens.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    slug: str
    name: str
    kind: IngredientKind
    density: Decimal | None
    piece_grams: Decimal | None
    origin: Origin
    allergens: list[Allergen]
    #: Whether anybody has looked. An empty `allergens` with this false means "unknown",
    #: not "contains none" — a client that reads the list alone reads unknown as safe,
    #: which is the failure ADR-006 exists to prevent.
    classified: bool
    #: Whether anybody has reviewed the entry itself (ADR-051).
    approved: bool


class RegistryPageView(BaseModel):
    """A page of the registry, with the size of the whole."""

    model_config = ConfigDict(frozen=True)

    entries: list[RegistryEntryView]
    total: int
