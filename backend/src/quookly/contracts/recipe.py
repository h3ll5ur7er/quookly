"""The canonical recipe, as it travels between layers.

A recipe is a yield, an ordered set of ingredient lines, and an ordered set of steps.
Prose is a rendering of that, never the source of truth — which is what makes scaling,
converting, adapting and planning operations on structure rather than rewrites of text.

Drafts are what a caller submits; the persisted types carry identity and resolved
ingredients.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from quookly.contracts.ingredient import Ingredient, Origin
from quookly.contracts.measure import Quantity


class Visibility(Enum):
    """Private by default; publishing is explicit (FR-5)."""

    PRIVATE = "private"
    PUBLIC = "public"


class Provenance(Enum):
    """How a recipe came to exist (V1).

    Recorded because it is worth knowing, but a recipe's usefulness never depends on it —
    every path ends in the same canonical structure.
    """

    AUTHORED = "authored"
    IMPORTED_JSON = "imported_json"
    IMPORTED_URL = "imported_url"
    GENERATED = "generated"


@dataclass(frozen=True, slots=True)
class IngredientLineDraft:
    """A use of a registry entry inside a recipe.

    `preparation` describes this use — "softened" is about this butter, not about butter.
    """

    ingredient_id: int
    quantity: Quantity
    preparation: str | None = None
    optional: bool = False


@dataclass(frozen=True, slots=True)
class StepDraft:
    """One action.

    Duration and temperature are fields rather than numbers buried in the instruction, so
    a timer can be offered without parsing prose (V15).
    """

    instruction: str
    duration_seconds: int | None = None
    temperature_celsius: int | None = None

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("a step needs an instruction")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError(f"a duration must be positive: {self.duration_seconds}")


@dataclass(frozen=True, slots=True)
class RecipeDraft:
    """A recipe as submitted, before it has identity."""

    title: str
    yield_quantity: Quantity
    provenance: Provenance
    lines: list[IngredientLineDraft]
    steps: list[StepDraft]
    summary: str | None = None
    origin: Origin = Origin.USER

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("a recipe needs a title")
        if not self.lines:
            raise ValueError("a recipe needs at least one ingredient")
        if not self.steps:
            raise ValueError("a recipe needs at least one step")


@dataclass(frozen=True, slots=True)
class IngredientLine:
    """A stored line, with its registry entry resolved for one locale."""

    id: int
    ingredient: Ingredient
    quantity: Quantity
    preparation: str | None
    optional: bool


@dataclass(frozen=True, slots=True)
class Step:
    id: int
    instruction: str
    duration_seconds: int | None
    temperature_celsius: int | None


@dataclass(frozen=True, slots=True)
class Recipe:
    """A stored recipe, whole."""

    id: int
    cook_id: int
    title: str
    summary: str | None
    yield_quantity: Quantity
    provenance: Provenance
    visibility: Visibility
    origin: Origin
    created_at: datetime
    lines: list[IngredientLine] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RecipeSummary:
    """Enough to list a recipe without loading its contents."""

    id: int
    title: str
    summary: str | None
    yield_quantity: Quantity
    visibility: Visibility
