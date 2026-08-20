"""SQLModel table definitions.

These types never leave the access layer — an import-linter contract enforces it
(ADR-008, ADR-018). Resource access services translate them into `quookly.contracts`.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from quookly.contracts.ingredient import IngredientKind, Origin


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
