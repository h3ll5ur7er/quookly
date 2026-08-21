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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quookly.contracts.ingredient import Ingredient, Origin
from quookly.contracts.measure import DecimalString, Quantity
from quookly.contracts.suitability import Outcome, VerdictView


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
    #: Absent for a line the cook judges themselves — salt to taste, oil for frying.
    quantity: Quantity | None = None
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
    """A stored line, with its registry entry resolved for one locale.

    `quantity` is absent for a line the cook judges themselves — salt to taste, oil for
    frying. Absent is not zero and not one: inventing either would misweigh the recipe or
    mislead about it, and dropping the line would lose an ingredient.
    """

    id: int
    ingredient: Ingredient
    quantity: Quantity | None
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


# What leaves the API. These are pydantic rather than dataclasses because they are the
# client boundary: they are validated on the way in and serialised on the way out.


class QuantityView(BaseModel):
    """A quantity as a client reads it.

    `magnitude` is a string. JSON numbers are binary floats in a browser, and 0.1 of a
    gram is not worth losing to that; `display` is what a screen actually shows.
    """

    model_config = ConfigDict(frozen=True)

    magnitude: str
    unit: str
    display: str


class PresentedLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    ingredient: str
    # Absent for a line the cook judges themselves. A client shows the ingredient and its
    # note, and nothing where a number would go.
    quantity: QuantityView | None = None
    preparation: str | None = None
    optional: bool = False


class PresentedStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    position: int
    instruction: str
    duration_seconds: int | None = None
    temperature_celsius: int | None = None


class PresentedRecipe(BaseModel):
    """A recipe scaled and rendered for one cook, ready to display."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    summary: str | None
    yield_quantity: QuantityView
    visibility: Visibility
    provenance: Provenance
    lines: list[PresentedLine]
    steps: list[PresentedStep]
    # Absent when there is nobody to judge against, which is not the same as suitable.
    suitability: VerdictView | None = None


class RecipeSummaryView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    summary: str | None
    yield_quantity: QuantityView
    visibility: Visibility
    # The outcome only. A list is a place to scan; the reasons are one tap away on a page
    # with room to name them. Absent when there is nobody to judge against.
    suitability: Outcome | None = None


class IngredientLineInput(BaseModel):
    """One line of a recipe being authored."""

    model_config = ConfigDict(frozen=True)

    ingredient_id: int
    # Both or neither. Half a *what* is not less information than "half a cup", it is
    # wrong information, so a magnitude without a unit is refused.
    magnitude: DecimalString | None = Field(default=None, gt=0)
    unit: str | None = None
    preparation: str | None = Field(default=None, max_length=200)
    optional: bool = False

    @model_validator(mode="after")
    def measured_or_not_at_all(self) -> "IngredientLineInput":
        if (self.magnitude is None) != (self.unit is None):
            raise ValueError("a line carries a magnitude and a unit, or neither")
        return self


class StepInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    instruction: str = Field(min_length=1, max_length=2000)
    duration_seconds: int | None = Field(default=None, gt=0)
    temperature_celsius: int | None = Field(default=None, ge=0, le=500)


class RecipeInput(BaseModel):
    """A recipe being authored (UC-1.1)."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=1000)
    yield_magnitude: DecimalString = Field(gt=0)
    yield_unit: str
    lines: list[IngredientLineInput] = Field(min_length=1)
    steps: list[StepInput] = Field(min_length=1)
