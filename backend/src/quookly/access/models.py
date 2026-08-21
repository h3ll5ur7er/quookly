"""SQLModel table definitions.

These types never leave the access layer — an import-linter contract enforces it
(ADR-008, ADR-018). Resource access services translate them into `quookly.contracts`.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from quookly.contracts.eater import AgeBand, Severity
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.measure import Unit
from quookly.contracts.onboarding import SetupStep
from quookly.contracts.pantry import WasteReason
from quookly.contracts.recipe import Provenance, Visibility


def _now() -> datetime:
    return datetime.now(UTC)


class CookRow(SQLModel, table=True):
    """A cook account as stored."""

    __tablename__ = "cook"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    display_name: str
    password_hash: str
    is_admin: bool = Field(default=False)
    registered_at: datetime = Field(default_factory=_now)
    # The language this cook chose, as opposed to the one their browser happens to ask
    # for. Absent until they choose, which is what the locale setup step is asking.
    locale: str | None = Field(default=None)


class IngredientRow(SQLModel, table=True):
    """A registry entry. Identity is the slug; names live in `IngredientNameRow`."""

    __tablename__ = "ingredient"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    kind: IngredientKind
    # Grams per millilitre. Absent where converting mass to volume is meaningless.
    density: Decimal | None = Field(default=None, max_digits=8, decimal_places=4)
    origin: Origin = Field(default=Origin.USER)
    # Whether anybody has classified this ingredient's allergens. Absent rows in
    # `ingredient_allergen` mean "contains none" only when this is true.
    allergens_classified: bool = Field(default=False)


class IngredientNameRow(SQLModel, table=True):
    """What an ingredient is called, in one locale.

    Several rows per ingredient per locale: recipes say cornflour or cornstarch and mean
    one thing, and an import has to resolve either. `normalised` is what lookups match
    on, so a cook typing into a form is not typing a database key.
    """

    __tablename__ = "ingredient_name"
    __table_args__ = (UniqueConstraint("locale", "normalised", name="uq_ingredient_name"),)

    id: int | None = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    locale: str = Field(index=True)
    name: str
    normalised: str = Field(index=True)
    is_canonical: bool = Field(default=False)


class RecipeRow(SQLModel, table=True):
    """A recipe's identity and yield. Its contents are lines and steps."""

    __tablename__ = "recipe"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    title: str
    summary: str | None = Field(default=None)
    yield_magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    yield_unit: Unit
    provenance: Provenance
    visibility: Visibility = Field(default=Visibility.PRIVATE)
    origin: Origin = Field(default=Origin.USER)
    created_at: datetime = Field(default_factory=_now)


class IngredientLineRow(SQLModel, table=True):
    """One ingredient as used in one recipe. `position` is the order it is written in."""

    __tablename__ = "ingredient_line"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    position: int
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    # Absent together for a line the cook judges themselves — salt to taste, oil for
    # frying. Absent is not zero: a stored zero would scale, render and shop as nothing.
    magnitude: Decimal | None = Field(default=None, max_digits=12, decimal_places=4)
    unit: Unit | None = Field(default=None)
    preparation: str | None = Field(default=None)
    optional: bool = Field(default=False)


class StepRow(SQLModel, table=True):
    """One action, in order.

    Duration and temperature are columns rather than numbers inside the instruction, so a
    timer can be offered without parsing prose.
    """

    __tablename__ = "step"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    position: int
    instruction: str
    duration_seconds: int | None = Field(default=None)
    temperature_celsius: int | None = Field(default=None)


class UnitPreferenceRow(SQLModel, table=True):
    """One cook's preferred unit for one kind of ingredient (UC-6.2)."""

    __tablename__ = "unit_preference"
    __table_args__ = (UniqueConstraint("cook_id", "kind", name="uq_unit_preference"),)

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    kind: IngredientKind
    unit: Unit


class IngredientAllergenRow(SQLModel, table=True):
    """One allergen an ingredient contains."""

    __tablename__ = "ingredient_allergen"
    __table_args__ = (UniqueConstraint("ingredient_id", "allergen", name="uq_ingredient_allergen"),)

    id: int | None = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    allergen: Allergen


class EaterRow(SQLModel, table=True):
    """One of the people a cook cooks for.

    Hangs off a cook rather than off an account: most people cooked for never sign in, and
    requiring a login to record a guest's allergy would make the feature useless (ADR-005).
    """

    __tablename__ = "eater"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    name: str
    age_band: AgeBand
    # A multiplier against a standard portion. Decimal, because these are summed and then
    # applied to every quantity in a recipe (FR-18).
    appetite: Decimal = Field(default=Decimal("1"), max_digits=4, decimal_places=2)
    created_at: datetime = Field(default_factory=_now)


class EaterConstraintRow(SQLModel, table=True):
    """One thing an eater avoids, and how seriously.

    `ingredient_slug` is text rather than a foreign key on purpose: somebody avoids
    coriander whether or not the registry has heard of it, and a constraint that waits on
    a registry entry is a constraint that is silently not applied.
    """

    __tablename__ = "eater_constraint"

    id: int | None = Field(default=None, primary_key=True)
    eater_id: int = Field(foreign_key="eater.id", index=True)
    allergen: Allergen | None = Field(default=None)
    ingredient_slug: str | None = Field(default=None)
    severity: Severity


class SetupDeclarationRow(SQLModel, table=True):
    """One setup question this cook has answered with "none" or "the defaults are fine".

    The only stored part of onboarding (ADR-014). Everything else is derived from the
    profile; this exists because no amount of derivation can tell a household where
    nobody has a dietary restriction from one nobody has been asked about (FR-15).
    """

    __tablename__ = "setup_declaration"
    __table_args__ = (UniqueConstraint("cook_id", "step", name="uq_setup_declaration"),)

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    step: SetupStep


class StockItemRow(SQLModel, table=True):
    """One lot in the pantry: some of an ingredient, arrived at one time.

    Lots rather than a running total per ingredient, because expiry belongs to a packet
    and not to an ingredient. Depleted lots keep their row with a magnitude of zero:
    deleting them would break the waste records that point at them, and those are the
    history the product is trying to help a cook shrink.
    """

    __tablename__ = "stock_item"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    unit: Unit
    # A day, not an instant. Nothing in a kitchen goes off at 14:32, and a timestamp
    # would raise a timezone question with no correct answer for a carton of milk.
    expires_on: date | None = Field(default=None, index=True)
    note: str | None = Field(default=None)
    received_at: datetime = Field(default_factory=_now)


class WasteRow(SQLModel, table=True):
    """Something that left the kitchen without being eaten (UC-5.4).

    Its own fact rather than a subtraction from stock. Waste inferred from a falling
    number cannot be told apart from waste that was eaten, and "what did we throw away,
    and why" is a question this product exists to answer.

    The ingredient, magnitude and unit are held here as well as on the lot, so the record
    still reads once the lot behind it is empty — or, later, when waste is recorded for
    something cooked rather than something stocked.
    """

    __tablename__ = "waste"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    stock_item_id: int | None = Field(default=None, foreign_key="stock_item.id", index=True)
    magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    unit: Unit
    reason: WasteReason
    note: str | None = Field(default=None)
    recorded_at: datetime = Field(default_factory=_now)
