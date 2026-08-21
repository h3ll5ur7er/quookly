"""What food contains, and who measured it (V6).

Composition data is not a fact about an ingredient; it is a **measurement of a particular
food supply**. Swiss flour is not fortified, American flour is fortified with folic acid
and iron by law. Swiss milk is not vitamin-D fortified, American milk is. Reading one
country's table for another country's kitchen is not a rounding error, it is the wrong
number ([ADR-045](../../../doc/07-decisions.md)).

So every profile carries its source, sources are tried in a configured order, and nothing
is ever merged: a value with its protein from Bern and its iron from Beltsville is a number
nobody measured.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Nutrient(Enum):
    """What Quookly tracks, which is what a European label declares.

    The set is EU Regulation 1169/2011's mandatory declaration — energy, fat, saturates,
    carbohydrate, sugars, protein, salt — plus fibre, which is optional there and given by
    every table worth using. It is also, not coincidentally, the set the Swiss and French
    databases publish, so nothing here is derived from a table that did not measure it.

    Salt rather than sodium, for the same reason: it is what a label in this part of the
    world says, and multiplying one into the other is arithmetic on somebody else's
    convention.
    """

    ENERGY_KJ = "energy_kj"
    ENERGY_KCAL = "energy_kcal"
    FAT = "fat"
    SATURATES = "saturates"
    CARBOHYDRATE = "carbohydrate"
    SUGARS = "sugars"
    FIBRE = "fibre"
    PROTEIN = "protein"
    SALT = "salt"

    @property
    def unit(self) -> str:
        """What the amount is in. Energy is the odd one; everything else is grams."""
        if self is Nutrient.ENERGY_KJ:
            return "kJ"
        if self is Nutrient.ENERGY_KCAL:
            return "kcal"
        return "g"


class NutritionSource(Enum):
    """A published food composition table.

    Ordered preference lives in configuration, not here: which table answers first is an
    instance's business, and a Swiss kitchen and a Canadian one want different answers to
    the same question.
    """

    SWISS = "swiss"
    CIQUAL = "ciqual"
    COFID = "cofid"
    USDA = "usda"


@dataclass(frozen=True, slots=True)
class SourceCredit:
    """Who to credit, and under what terms (FR-20).

    Carried per source rather than as one blanket line at the bottom of the application,
    because a recipe can draw on two tables and both licences are then owed. The Swiss
    grant makes attribution *mandatory*, which is why this is a requirement rather than a
    courtesy.
    """

    source: NutritionSource
    name: str
    publisher: str
    licence: str
    url: str


#: What each table is called and what using it obliges. Verified against the publishers'
#: own pages rather than against summaries of them (ADR-007).
CREDITS: dict[NutritionSource, SourceCredit] = {
    NutritionSource.SWISS: SourceCredit(
        source=NutritionSource.SWISS,
        name="Swiss Food Composition Database",
        publisher="Federal Food Safety and Veterinary Office (FSVO)",
        licence="Open use. Must provide the source.",
        url="https://naehrwertdaten.ch/",
    ),
    NutritionSource.CIQUAL: SourceCredit(
        source=NutritionSource.CIQUAL,
        name="Ciqual French food composition table",
        publisher="ANSES",
        licence="Licence Ouverte (Etalab)",
        url="https://ciqual.anses.fr/",
    ),
    NutritionSource.COFID: SourceCredit(
        source=NutritionSource.COFID,
        name="Composition of Foods Integrated Dataset (CoFID)",
        publisher="Public Health England",
        licence="Open Government Licence v3.0",
        url="https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid",
    ),
    NutritionSource.USDA: SourceCredit(
        source=NutritionSource.USDA,
        name="FoodData Central",
        publisher="U.S. Department of Agriculture",
        licence="CC0 1.0 (public domain)",
        url="https://fdc.nal.usda.gov/",
    ),
}


@dataclass(frozen=True, slots=True)
class NutrientProfile:
    """What 100 g of one ingredient contains, according to one table.

    Per 100 g of the *edible portion*, which is how every composition table publishes and
    what makes them comparable. A nutrient the table did not measure is absent from
    `amounts` rather than zero — the distinction this codebase makes everywhere, and one
    that matters especially here: a missing fibre figure is not a food without fibre.
    """

    ingredient_id: int
    source: NutritionSource
    #: The entry this came from, kept so a number can be traced back to a published row.
    reference: str
    amounts: dict[Nutrient, Decimal]


@dataclass(frozen=True, slots=True)
class Counted:
    """What a set of ingredient lines comes to.

    `at_least` is the familiar mark: a line nobody could weigh — salt to taste, an
    ingredient no table answers for — contributes nothing, so the totals are floors. Left
    unmarked they would read as the whole of a dish, and a number that quietly leaves out
    the butter is worse than no number.
    """

    amounts: dict[Nutrient, Decimal]
    at_least: bool
    #: The ingredients that could not be counted, by name, so a cook can see the gap.
    uncounted: list[str]
    #: Every table that answered, so each can be credited (FR-20).
    sources: list[NutritionSource]


# What leaves the API.


class NutrientView(BaseModel):
    model_config = ConfigDict(frozen=True)

    nutrient: Nutrient
    #: A string for the same reason every quantity is: a browser's JSON numbers are binary
    #: floats, and 0.3 g of salt is not worth losing to that.
    amount: str
    unit: str


class CreditView(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    publisher: str
    licence: str
    url: str


class NutritionView(BaseModel):
    """What a recipe contains, as a client reads it."""

    model_config = ConfigDict(frozen=True)

    #: Absent where the recipe does not say how many it serves (ADR-030). Per-recipe still
    #: stands: how much is in the tray is knowable even when how many it feeds is not.
    per_serving: list[NutrientView] | None
    per_recipe: list[NutrientView]
    at_least: bool
    uncounted: list[str]
    credits: list[CreditView]
