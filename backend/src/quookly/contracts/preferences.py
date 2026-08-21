"""How a cook wants to read quantities.

Preferences run along *ingredient kind*, not along a global unit system (UC-6.2). A cook
may want powders in grams and liquids in decilitres; "metric" is not a fine enough answer
to be useful in a kitchen.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Unit

# What a cook gets before they choose anything. An empty preference set would show a
# scraped American recipe in cups to a Swiss cook forever, so the defaults are metric and
# per kind rather than absent.
DEFAULT_UNITS: Mapping[IngredientKind, Unit] = {
    IngredientKind.POWDER: Unit.GRAM,
    IngredientKind.LIQUID: Unit.MILLILITRE,
    IngredientKind.SOLID: Unit.GRAM,
    IngredientKind.COUNTABLE: Unit.PIECE,
}


@dataclass(frozen=True, slots=True)
class UnitPreferences:
    """A preferred unit per ingredient kind. A kind with no entry keeps what was written."""

    by_kind: Mapping[IngredientKind, Unit]

    def for_kind(self, kind: IngredientKind) -> Unit | None:
        return self.by_kind.get(kind)


class UnitPreferenceView(BaseModel):
    """One kind of ingredient and the unit this cook reads it in.

    `chosen` separates a preference from a default. Everybody has defaults, and having
    them is not an answer — which is what lets guided setup tell the two apart (FR-15).
    """

    model_config = ConfigDict(frozen=True)

    kind: IngredientKind
    unit: str
    chosen: bool


class UnitChoice(BaseModel):
    """The unit a cook wants this kind of ingredient shown in."""

    model_config = ConfigDict(frozen=True)

    unit: str
