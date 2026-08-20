"""SQLModel table definitions.

These types never leave the access layer — an import-linter contract enforces it
(ADR-008, ADR-018). Resource access services translate them into `quookly.contracts`.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.measure import Unit
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
    magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    unit: Unit
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
