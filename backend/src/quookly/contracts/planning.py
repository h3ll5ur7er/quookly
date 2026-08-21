"""What a plan needs, and how confidently it knows (V7).

The stable part of planning is that a plan assigns recipes to slots over a period, with
attending eaters per slot. What varies is how a slot's requirement is worked out from
that — per head, per appetite, with leftovers, with a margin for a hungry Sunday — and
that is what `PlanningEngine` encapsulates.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from quookly.contracts.eater import Eater
from quookly.contracts.provisioning import Requirement
from quookly.contracts.recipe import Recipe


class Sizing(Enum):
    """How confidently a meal was sized, which the cook has to be able to see.

    Only the first is the product working as intended. The other two produce a shopping
    list for one batch, which is right often enough to be worth doing and wrong often
    enough that saying nothing would be the failure — somebody shops for one tray and
    feeds four of the six people they invited.
    """

    #: Scaled to the appetites of the people attending (FR-18).
    TO_THE_TABLE = "to_the_table"
    #: Nobody has said who is coming yet, so one batch as the recipe writes it.
    AS_WRITTEN = "as_written"
    #: The recipe does not say how many it feeds, so one batch — see ADR-030.
    UNSCALABLE = "unscalable"


@dataclass(frozen=True, slots=True)
class PlannedMeal:
    """One filled slot, with everything needed to work out what it takes."""

    plan_slot_id: int
    recipe: Recipe
    eaters: list[Eater] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SizedMeal:
    """What one meal came to, and how sure the plan is about it."""

    plan_slot_id: int
    factor: Decimal
    sizing: Sizing


@dataclass(frozen=True, slots=True)
class PlanRequirements:
    """Everything a plan needs, meal by meal and ingredient by ingredient."""

    meals: list[SizedMeal] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
