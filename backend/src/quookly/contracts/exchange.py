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

from quookly.contracts.execution import Attention
from quookly.contracts.ingredient import Allergen, IngredientKind
from quookly.contracts.recipe import Provenance


class ExchangeIngredient(BaseModel):
    """Enough to recreate a registry entry on an instance that lacks it."""

    model_config = ConfigDict(frozen=True)

    slug: str
    kind: IngredientKind
    density: Decimal | None = None
    #: What it is called in the document's own locale. Kept as it was so a build that
    #: reads format 4 still reads a format 5 document's ingredients.
    names: list[str] = Field(min_length=1)
    #: And in every language the exporting registry knew. Added in format 5: without it a
    #: German import arrived named only in German, which made a foreign entry less readable
    #: than a seeded one for no reason — the names existed and were being dropped.
    #: Empty in every earlier document, where `names` and the document's `locale` say it.
    names_by_locale: dict[str, list[str]] = Field(default_factory=dict)
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
    # How much of the cook the step asks for. Added in format 3; a format 1 or 2 document
    # has no opinion, and every step in it takes the hands-on default — which over-reports
    # the work rather than under-reporting it.
    attention: Attention = Attention.HANDS_ON


class ExchangeTranslation(BaseModel):
    """A recipe's prose in one other language, as somebody here wrote it.

    Only a person's. A model's translation is nobody's work: the receiving instance can
    derive one in a round trip with its own model, and shipping one would spread this
    instance's model quality to everywhere that ever imported from it (ADR-064).
    """

    model_config = ConfigDict(frozen=True)

    locale: str
    title: str
    summary: str | None = None
    #: Paired to the recipe by position, the same as in storage. A translation with a
    #: different number of steps is refused rather than repaired.
    steps: list[str] = Field(default_factory=list)


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
    #: What the prose is written in, as a bare code. Added in format 5. Absent where
    #: nobody knows, which is a real answer — and without it a German recipe arrived on a
    #: fresh instance with nothing to say it was German, so nothing could translate it.
    language: str | None = None
    #: Translations somebody here wrote. Added in format 5, and a person's only.
    translations: list[ExchangeTranslation] = Field(default_factory=list)


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
