"""The ingredient registry, as it travels between layers.

An ingredient is a registry entry — "unsalted butter", with a density and names per
locale. An *ingredient line* is a use of one inside a recipe. Keeping them separate is
what makes quantities convertible and stock matchable.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Final

from pydantic import BaseModel, ConfigDict

from quookly.contracts.matching import Resemblance


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
    #: Where this food sits — an aisle in a shop, a heading in a list of nine hundred.
    #: Absent for everything a cook adds themselves, and for every entry that predates
    #: the taxonomy. Absent rather than a bucket called "other": a bucket is a claim
    #: about the food, and "nobody has said" is not one.
    category_id: int | None = None
    category_slug: str | None = None


@dataclass(frozen=True, slots=True)
class Category:
    """Where a food sits, named in one locale.

    A tree: `parent_slug` is absent for a section and names one for a group inside it. The
    Swiss table publishes two levels — *Vegetables/Fresh vegetables* — and nothing here
    says two, because a household that stocks something it never listed should be able to
    add a category rather than a migration.

    Deliberately not `IngredientKind`, which is `liquid / powder / solid / countable` and
    exists to choose a unit. Grouping a shopping list by that produced "Solid: apples,
    cheese, bread", which is where this came from.
    """

    id: int
    slug: str
    name: str
    parent_slug: str | None = None


class Unset(Enum):
    """A field a correction did not mention.

    Needed because `None` is a real answer for a density and a piece weight: *absent* is
    the honest state for an ingredient nobody has weighed, and a correction must be able
    to say that as well as to leave the field alone. A plain `None` default would make
    those two indistinguishable and silently wipe a figure every time somebody fixed the
    kind beside it.
    """

    TOKEN = "unset"


#: The sentinel itself, so callers write `UNSET` rather than `Unset.TOKEN`.
UNSET: Final = Unset.TOKEN


@dataclass(frozen=True, slots=True)
class RegistryEntryDetail:
    """One entry, whole, with what it is called in every locale that knows it.

    Names are ordered canonical-first within each locale: the first is what that language
    calls the thing, the rest are spellings a recipe might use.
    """

    entry: "Ingredient"
    names: dict[str, list[str]]


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
    #: Where this food sits, as a slug into the tree `GET /registry/categories` returns.
    #: Absent for everything a cook adds themselves. The slug rather than the name: a
    #: client that has the tree can name it, and a page of fifty entries would otherwise
    #: repeat a handful of strings fifty times.
    category_slug: str | None = None


class CategoryView(BaseModel):
    """One node of the food tree, named as this cook reads it."""

    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    #: Absent for a section, and the section's slug for a group inside it. Flat on the
    #: wire rather than nested: a client that wants a tree builds one, and a client that
    #: wants to look a slug up should not have to walk one.
    parent_slug: str | None


class RegistryPageView(BaseModel):
    """A page of the registry, with the size of the whole."""

    model_config = ConfigDict(frozen=True)

    entries: list[RegistryEntryView]
    total: int


class RegistryEntryDetailView(BaseModel):
    """One entry and every name it answers to, as the correction screen reads it."""

    model_config = ConfigDict(frozen=True)

    entry: RegistryEntryView
    #: Whether any published figures are held for this entry, from any source. Not which
    #: — that is decided at read time against the configured order (ADR-045).
    has_nutrition: bool
    #: Locale to spellings, canonical first. An entry an import created carries one
    #: locale — the language of the page it came from — and that is the gap to fill.
    names: dict[str, list[str]]


class ResemblingView(BaseModel):
    """One entry a name might mean, as a client reads it.

    A suggestion. Nothing here resolves anything: an import that acted on a resemblance
    would attach one food's allergens to another food's recipe (ADR-006).
    """

    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    confidence: Decimal
    reason: Resemblance
    #: Whether this one carries published figures. Shown because it is what leaving the
    #: pair unmerged costs: an entry an import invented has none, and merging is what
    #: brings them across (ADR-052). Copying them instead would leave two entries claiming
    #: to be one food, which is the split merging exists to undo.
    carries_nutrition: bool


class DuplicateView(BaseModel):
    """Two entries that might be one ingredient."""

    model_config = ConfigDict(frozen=True)

    slug: str
    other: str
    name: str
    other_name: str
    confidence: Decimal
    reason: Resemblance
