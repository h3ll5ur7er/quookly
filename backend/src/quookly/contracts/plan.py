"""A plan: what is being eaten, when, and by whom.

A plan is a period and a set of slots. A slot is one meal on one day, optionally carrying
a recipe and the people who will be at it. Optional on purpose: a week gets planned in
passes, and a slot that cannot exist until it has a recipe cannot hold "Thursday, the four
of us, something quick".
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
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
    #: How much of the recipe to make, in the recipe's own yield unit — 8 of a recipe that
    #: makes 4 is twice it. Absent where the cook has not said, which is most slots.
    servings: Decimal | None = None
    #: When it was cooked, if it was. A cooked meal is a record rather than a plan: it
    #: holds no stock, needs no shopping, and is not edited.
    cooked_at: datetime | None = None


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
    #: Whether it has been cooked. The instant is kept; a screen needs the fact.
    cooked: bool
    #: How much of the recipe this meal makes: "1" is one batch, "1.5" is half again.
    #: Absent for a slot with no recipe in it.
    factor: str | None
    #: Absent for a slot with no recipe in it. Anything other than `to_the_table` means
    #: the shopping list for this meal is for one batch, and the cook needs to see that.
    sizing: Sizing | None
    #: Absent when nobody has said who is coming, which is not the same as suitable.
    suitability: VerdictView | None
    #: The yield the cook asked for, if they asked for one. Carried back so that editing
    #: a meal restates it rather than silently dropping it — `SlotInput` is a statement
    #: about the whole meal, and a field left out of one is a field set to nothing.
    servings: str | None


class ShoppingLineView(BaseModel):
    """One thing to buy. Named and rendered as this cook reads quantities."""

    model_config = ConfigDict(frozen=True)

    ingredient_id: int
    name: str
    quantity: str
    #: The same amount, in the two halves a shelf is stocked with. `quantity` is for
    #: reading; this is for acting on, so that putting what was bought into the pantry
    #: does not mean parsing a rendered string back apart — which is where a comma and a
    #: full stop start meaning different things in different languages (S3).
    magnitude: str
    unit: str
    #: Which aisle, as a slug into the registry's food tree. A forty-item list with no
    #: headings is read line by line; a cook in a shop walks aisles. Absent where nobody
    #: has placed the food — a bucket called "other" would be a claim about it (ADR-067).
    category_slug: str | None = None
    # Whether it is already in the basket. A tick made at a different quantity does not
    # count, so this is false again the moment the plan asks for more (ADR-048).
    bought: bool = False


class BoughtInput(BaseModel):
    """Whether one line of the shopping list is in the basket (UC-4.4)."""

    model_config = ConfigDict(frozen=True)

    bought: bool


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


#: The longest period that is still a plan. Beyond about a month it is a calendar, and
#: nobody knows who is coming to dinner in November. It is also what stops a screen laying
#: out a row per day for a period somebody typed by accident.
LONGEST_PLAN_DAYS = 31


class PlanInput(BaseModel):
    """A period to plan (UC-4.1). Both dates inclusive."""

    model_config = ConfigDict(frozen=True)

    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def is_a_period_somebody_could_plan(self) -> "PlanInput":
        if self.ends_on < self.starts_on:
            raise ValueError("a plan does not end before it begins")
        if (self.ends_on - self.starts_on).days >= LONGEST_PLAN_DAYS:
            raise ValueError(f"a plan covers at most {LONGEST_PLAN_DAYS} days")
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
    #: How much of the recipe to make, stated the way the recipe states its own yield.
    #: Absent means "as the recipe writes it, or as the table wants it" — the two rules
    #: that applied before anybody could say otherwise.
    servings: Decimal | None = Field(default=None, gt=0)
