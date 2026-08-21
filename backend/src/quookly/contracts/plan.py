"""A plan: what is being eaten, when, and by whom.

A plan is a period and a set of slots. A slot is one meal on one day, optionally carrying
a recipe and the people who will be at it. Optional on purpose: a week gets planned in
passes, and a slot that cannot exist until it has a recipe cannot hold "Thursday, the four
of us, something quick".
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quookly.contracts.planning import Sizing
from quookly.contracts.suitability import VerdictView


class Meal(Enum):
    """Which meal of the day a slot is.

    Four coarse ones rather than free text or a clock time. A plan is read as a grid, and
    a grid needs a fixed number of rows; "18:30" would sort correctly and group not at all.
    """

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


@dataclass(frozen=True, slots=True)
class PlanSlot:
    """One meal on one day.

    `recipe_id` is absent for a slot that has been made but not filled — which is most of
    a week, most of the time. `attendee_ids` is who will be there; an empty list means
    nobody has said, which is a different thing from nobody coming.
    """

    id: int
    plan_id: int
    on_date: date
    meal: Meal
    recipe_id: int | None = None
    attendee_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MealPlan:
    """A period, and the meals planned inside it.

    `starts_on` and `ends_on` are both inclusive. A plan for one day starts and ends on
    that day, which is the reading that does not need a comment at every call site.
    """

    id: int
    cook_id: int
    starts_on: date
    ends_on: date
    slots: list[PlanSlot] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.ends_on < self.starts_on:
            raise ValueError("a plan does not end before it begins")


# What crosses the API.


class SlotView(BaseModel):
    """One meal on one day, as a client reads it.

    Carries three things a plan screen cannot work out for itself: how the meal was sized
    and how sure that is, whether the people coming can eat it, and the names rather than
    the ids of both.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    on_date: date
    meal: Meal
    recipe_id: int | None
    recipe_title: str | None
    attendee_ids: list[int]
    attendees: list[str]
    #: How much of the recipe this meal makes: "1" is one batch, "1.5" is half again.
    #: Absent for a slot with no recipe in it.
    factor: str | None
    #: Absent for a slot with no recipe in it. Anything other than `to_the_table` means
    #: the shopping list for this meal is for one batch, and the cook needs to see that.
    sizing: Sizing | None
    #: Absent when nobody has said who is coming, which is not the same as suitable.
    suitability: VerdictView | None


class ShoppingLineView(BaseModel):
    """One thing to buy. Named and rendered as this cook reads quantities."""

    model_config = ConfigDict(frozen=True)

    ingredient_id: int
    name: str
    quantity: str


class PlanView(BaseModel):
    """A plan whole: the week, and what it means the cook has to buy.

    The list travels with the plan rather than behind its own request. It is derived from
    what the plan managed to reserve, so fetching the two separately would let a screen
    show a week and a list that disagree about the same butter.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    starts_on: date
    ends_on: date
    slots: list[SlotView]
    shopping: list[ShoppingLineView]


class PlanSummaryView(BaseModel):
    """Enough to list a plan without working out what it takes."""

    model_config = ConfigDict(frozen=True)

    id: int
    starts_on: date
    ends_on: date
    planned: int


class PlanInput(BaseModel):
    """A period to plan (UC-4.1). Both dates inclusive."""

    model_config = ConfigDict(frozen=True)

    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def ends_after_it_begins(self) -> "PlanInput":
        if self.ends_on < self.starts_on:
            raise ValueError("a plan does not end before it begins")
        return self


class SlotInput(BaseModel):
    """One meal, stated whole (UC-4.1, UC-4.2).

    A statement rather than a patch, for the same reason an eater is: a partial update
    would need a way to say "and nobody is coming after all", and the version that
    forgets to is the one that quietly keeps somebody at the table — with their
    constraints still being checked against a meal they are not at.
    """

    model_config = ConfigDict(frozen=True)

    on_date: date
    meal: Meal
    recipe_id: int | None = None
    attendee_ids: list[int] = Field(default_factory=list, max_length=50)
