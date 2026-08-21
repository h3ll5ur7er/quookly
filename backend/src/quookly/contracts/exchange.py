"""The interchange format.

One format serves export and import (ADR-012), so every round trip exercises the promise
that a self-hoster is not trapped. Two properties make it portable:

- **Lines refer to ingredients by slug.** Database ids belong to the instance that issued
  them; a slug means the same thing everywhere.
- **The ingredients used travel with the recipes.** Without them, importing into a fresh
  instance would resolve nothing.

Identity and ownership are deliberately absent: recipe ids and accounts belong to the
instance that held them, not to the recipe.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from quookly.contracts.ingredient import Allergen, IngredientKind
from quookly.contracts.recipe import Provenance


class ExchangeIngredient(BaseModel):
    """Enough to recreate a registry entry on an instance that lacks it."""

    model_config = ConfigDict(frozen=True)

    slug: str
    kind: IngredientKind
    density: Decimal | None = None
    names: list[str] = Field(min_length=1)
    # Absent means nobody classified it; an empty list means somebody did and it contains
    # none. The distinction is the basis of ADR-006 and survives the journey intact.
    allergens: list[Allergen] | None = None


class ExchangeLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingredient: str
    # Absent together for a line the cook judges themselves — salt to taste, oil for
    # frying. A recipe must not gain a quantity by crossing between instances.
    magnitude: Decimal | None = None
    unit: str | None = None
    preparation: str | None = None
    optional: bool = False


class ExchangeStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    instruction: str
    duration_seconds: int | None = None
    temperature_celsius: int | None = None


class ExchangeRecipe(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    summary: str | None = None
    yield_magnitude: Decimal
    yield_unit: str
    # How many people it feeds, where the yield does not already say. Added in format 2;
    # absent in every format 1 document, and absent is a real answer.
    serves: Decimal | None = None
    provenance: Provenance
    lines: list[ExchangeLine] = Field(min_length=1)
    steps: list[ExchangeStep] = Field(min_length=1)


class ExchangeDocument(BaseModel):
    """A portable set of recipes and the registry entries they use."""

    model_config = ConfigDict(frozen=True)

    quookly: int
    exported_at: datetime
    # The locale the ingredient names are written in. Names are exported in one locale;
    # a fuller export would carry every translation the instance holds.
    locale: str
    ingredients: list[ExchangeIngredient]
    recipes: list[ExchangeRecipe]
