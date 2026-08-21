"""A plan: what is being eaten, when, and by whom.

A plan is a period and a set of slots. A slot is one meal on one day, optionally carrying
a recipe and the people who will be at it. Optional on purpose: a week gets planned in
passes, and a slot that cannot exist until it has a recipe cannot hold "Thursday, the four
of us, something quick".
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


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
