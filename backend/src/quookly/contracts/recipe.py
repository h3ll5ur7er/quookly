"""The canonical recipe, as it travels between layers.

A recipe is a yield, an ordered set of ingredient lines, and an ordered set of steps.
Prose is a rendering of that, never the source of truth — which is what makes scaling,
converting, adapting and planning operations on structure rather than rewrites of text.

Drafts are what a caller submits; the persisted types carry identity and resolved
ingredients.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quookly.contracts.execution import Attention, TimingView
from quookly.contracts.ingredient import Ingredient, IngredientKind, Origin
from quookly.contracts.interpretation import Source
from quookly.contracts.matching import MentionView
from quookly.contracts.measure import DecimalString, Quantity, Unit
from quookly.contracts.nutrition import NutritionView
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
    #: A version of another recipe: made dairy-free, or with the butter swapped out. Kept
    #: apart from `GENERATED` because the histories differ — one was invented from nothing
    #: and this one started from something the cook already had.
    DERIVED = "derived"


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
    #: Hands-on unless said otherwise. The default over-reports the work rather than
    #: under-reporting it, which fails in the direction that does not make anybody late.
    attention: Attention = Attention.HANDS_ON

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("a step needs an instruction")
        if self.duration_seconds is not None and self.duration_seconds <= 0:
            raise ValueError(f"a duration must be positive: {self.duration_seconds}")


#: How many standard portions a recipe makes, where its yield does not already say.
#:
#: "Makes 12 pancakes" states a count of pancakes and nothing about how many pancakes feed
#: one person, so such a recipe cannot be scaled to a table without this. Where the yield
#: *is* in servings, this stays absent and the yield answers — one number, one place, and
#: no way for the two to disagree.
_SERVES_FROM_YIELD = "a recipe whose yield is in servings serves exactly that many"


def _servings_of(yield_quantity: Quantity, serves: Decimal | None) -> Decimal | None:
    """How many portions this makes, or nothing if the recipe does not say."""
    if yield_quantity.unit is Unit.SERVING:
        return yield_quantity.magnitude
    return serves


def _check_serves(yield_quantity: Quantity, serves: Decimal | None) -> None:
    if serves is not None and serves <= 0:
        raise ValueError("a recipe that serves nobody is not a recipe")
    if (
        yield_quantity.unit is Unit.SERVING
        and serves is not None
        and serves != yield_quantity.magnitude
    ):
        raise ValueError(_SERVES_FROM_YIELD)


@dataclass(frozen=True, slots=True)
class Picture:
    """A photograph, and what it shows.

    The description travels with the id rather than beside it, so there is no shape in
    which a picture exists without its alt text.
    """

    media_id: str
    description: str


class PictureView(BaseModel):
    """A recipe's picture as a client reads it."""

    model_config = ConfigDict(frozen=True)

    media_id: str
    description: str


@dataclass(frozen=True, slots=True)
class RecipeDraft:
    """A recipe as submitted, before it has identity."""

    title: str
    yield_quantity: Quantity
    provenance: Provenance
    lines: list[IngredientLineDraft]
    steps: list[StepDraft]
    summary: str | None = None
    #: The recipe this one was made from, for a version of something.
    derived_from: int | None = None
    origin: Origin = Origin.USER
    #: Absent where the yield already says. See `_servings_of`.
    serves: Decimal | None = None
    #: What the prose is written in, as a bare code — `de`, not `de-CH`. Absent where
    #: nobody knows: an import from a page that did not say (ADR-032).
    language: str | None = None

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("a recipe needs a title")
        if not self.lines:
            raise ValueError("a recipe needs at least one ingredient")
        if not self.steps:
            raise ValueError("a recipe needs at least one step")
        _check_serves(self.yield_quantity, self.serves)

    @property
    def servings(self) -> Decimal | None:
        """How many standard portions this makes, or nothing if it does not say."""
        return _servings_of(self.yield_quantity, self.serves)


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
    attention: Attention = Attention.HANDS_ON


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
    #: The recipe this one was made from, for a version of something (UC-1.7).
    derived_from: int | None = None
    lines: list[IngredientLine] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    #: Absent where the yield already says. See `_servings_of`.
    serves: Decimal | None = None
    #: What the prose is written in, as a bare code. Absent where nobody knows (ADR-032).
    language: str | None = None
    #: When this recipe was put away, if it was. An archived recipe is out of the cook's
    #: list and out of the search index, and still reachable by the plans and cooked meals
    #: that point at it (ADR-059).
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        _check_serves(self.yield_quantity, self.serves)

    @property
    def servings(self) -> Decimal | None:
        """How many standard portions this makes, or nothing if it does not say.

        The one thing that lets a recipe be scaled to a table rather than to a number of
        pancakes. Absent is a real answer: nothing invents a pieces-per-serving figure.
        """
        return _servings_of(self.yield_quantity, self.serves)

    #: A photograph of the dish, where the cook has taken one.
    picture: Picture | None = None


@dataclass(frozen=True, slots=True)
class RecipeSummary:
    """Enough to list a recipe without loading its contents."""

    id: int
    title: str
    summary: str | None
    yield_quantity: Quantity
    visibility: Visibility
    serves: Decimal | None = None

    @property
    def servings(self) -> Decimal | None:
        return _servings_of(self.yield_quantity, self.serves)

    #: A photograph of the dish, where the cook has taken one.
    picture: Picture | None = None


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
    #: The registry entry this line points at, and what sort of thing it is.
    #:
    #: The name alone is enough to *read* a recipe and not enough to *correct* one: a form
    #: that only knew what a line was called would have to resolve the name back to an
    #: entry, which is guessing at something the server already knew. The kind comes with
    #: it because which units to offer is decided by kind (ADR-059).
    ingredient_id: int
    ingredient_kind: IngredientKind
    # Absent for a line the cook judges themselves. A client shows the ingredient and its
    # note, and nothing where a number would go.
    quantity: QuantityView | None = None
    preparation: str | None = None
    optional: bool = False


class PresentedStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    position: int
    #: What a cook reads: any link markup resolved, because the brackets are not on screen.
    instruction: str
    #: What is stored, for a form that has to send it back. Filling an editor from the
    #: rendered text would drop the link the moment somebody corrected a typo (ADR-059).
    written: str
    duration_seconds: int | None = None
    temperature_celsius: int | None = None
    # Not defaulted, unlike the input. What a client is *shown* always says what the step
    # asks of the cook — a field a reader has to supply a default for is a field that
    # reads as absent, and absence is what this codebase refuses to let mean a value.
    attention: Attention
    #: Words in this instruction a cook can look up, as offsets into it.
    #:
    #: Positions rather than content, the same rule the ingredient lines follow (ADR-040):
    #: what is stored is the instruction, and the marks are read out of its own words when
    #: it is shown. A recipe imported before a page existed gains the link the day somebody
    #: writes it, and nothing has to be migrated for that to happen.
    mentions: list[MentionView] = []


class PresentedRecipe(BaseModel):
    """A recipe scaled and rendered for one cook, ready to display."""

    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    summary: str | None
    yield_quantity: QuantityView
    # How many this feeds, where the yield does not already say it. "Makes 12" and
    # "serves 4" are two different facts, and a recipe that states only the first cannot
    # be scaled to a table. Absent where the yield is already in servings: saying it
    # twice invites a reader to wonder which one is right.
    serves: str | None
    visibility: Visibility
    provenance: Provenance
    #: What the prose is written in, as a bare code — `de`, not `de-CH`. Absent where
    #: nobody knows: an import from a page that did not say (ADR-032).
    language: str | None = None
    #: Whether the words on this page were translated rather than written by their author.
    #:
    #: Said out loud, because prose a model produced and shown as somebody's own words is
    #: the failure ADR-056 exists to prevent — and here the author may be somebody the
    #: reader knows. False where the reader is reading the original, *and* where no
    #: translation could be made and the original is being shown instead.
    translated: bool = False
    #: And by whom. A machine's words and a person's are both translations and only one of
    #: them is somebody's work — saying "a machine wrote this" over a correction a cook
    #: made is as wrong as the other way round (ADR-064). Meaningless where `translated`
    #: is false.
    translated_by_hand: bool = False
    # The recipe this one is a version of, where it is a version of one. A cook looking at
    # a dairy-free shortbread should be one tap from the shortbread.
    derived_from: int | None = None
    derived_from_title: str | None = None
    lines: list[PresentedLine]
    steps: list[PresentedStep]
    # Absent when there is nobody to judge against, which is not the same as suitable.
    suitability: VerdictView | None = None
    # Derived from the steps every time, never stored. A recipe whose steps say nothing
    # about time reports nothing, rather than an hour of nothing (ADR-037).
    timing: TimingView | None = None
    # What it contains, from whichever published table this instance believes first
    # (ADR-045). Absent where nothing in the recipe could be weighed against one.
    nutrition: NutritionView | None = None
    #: A photograph of the dish, where the cook has taken one.
    picture: PictureView | None = None


class RecipeSummaryView(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    summary: str | None
    yield_quantity: QuantityView
    serves: str | None
    visibility: Visibility
    # The outcome only. A list is a place to scan; the reasons are one tap away on a page
    # with room to name them. Absent when there is nobody to judge against.
    suitability: Outcome | None = None
    # On the list too, not only the page. "How long does this take" is one of the two
    # questions asked before a recipe is opened, and answering it after the tap is
    # answering it too late.
    timing: TimingView | None = None
    #: A photograph of the dish, where the cook has taken one.
    picture: PictureView | None = None


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
    # Defaulted, because most authors will leave it alone and the default has to be the
    # one that does not make anybody late (ADR-037).
    attention: Attention = Attention.HANDS_ON


class RecipeInput(BaseModel):
    """A recipe being authored (UC-1.1)."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=1000)
    yield_magnitude: DecimalString = Field(gt=0)
    yield_unit: str
    # How many people it feeds. Worth asking for only where the yield does not already
    # say — and asking anyway, because "makes 12, serves 4" is how a cook says it and a
    # recipe missing this cannot be planned around.
    serves: DecimalString | None = Field(default=None, gt=0, le=1000)
    lines: list[IngredientLineInput] = Field(min_length=1)
    steps: list[StepInput] = Field(min_length=1)


class VariantInput(BaseModel):
    """What to change about a recipe (UC-1.7).

    One field, because the change is a sentence: "make it dairy-free", "without the eggs",
    "swap the butter for olive oil". Offering a menu of adaptations would be guessing at the
    list before anybody has asked for one.
    """

    model_config = ConfigDict(frozen=True)

    change: str = Field(min_length=1, max_length=300)


class GenerationInput(BaseModel):
    """A request for a recipe that does not exist yet (UC-1.4, UC-1.5).

    Everything is optional except that there has to be *something*: a description, some
    ingredients to use up, or both. "Write me a recipe" with no constraints at all is a
    question with too many answers to be useful.
    """

    model_config = ConfigDict(frozen=True)

    description: str | None = Field(default=None, max_length=500)
    #: Registry ids rather than names — the cook picked these from their own pantry, and a
    #: name would have to be resolved back again.
    ingredient_ids: list[int] = Field(default_factory=list, max_length=25)
    serves: int | None = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def something_to_go_on(self) -> "GenerationInput":
        if not (self.description and self.description.strip()) and not self.ingredient_ids:
            raise ValueError("say what to cook, or what to use up")
        return self


class UrlImport(BaseModel):
    """A page to read a recipe out of (UC-1.3)."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(min_length=1, max_length=2000)


class ImportedRecipe(BaseModel):
    """What importing a page did, as well as what it produced.

    `ingredients_added` is the part a cook has to act on: names the registry had never
    seen are recorded so the recipe can exist, and nothing is known about their allergens
    until somebody looks. Reporting them is what stops that being a silent addition.
    """

    model_config = ConfigDict(frozen=True)

    recipe: PresentedRecipe
    read_from: Source
    source_url: str
    ingredients_added: list[str] = Field(default_factory=list)
