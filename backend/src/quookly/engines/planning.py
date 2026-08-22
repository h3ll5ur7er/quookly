"""Working out what a planned week takes (V7, UC-4.1).

A rule engine: recipes and eaters arrive as arguments and nothing is fetched, which is
what makes the sizing rule a table of cases rather than a fixture.

What is stable is that a plan assigns recipes to slots with eaters attending. What varies
— and lives here — is how a slot's requirement follows from that: per appetite today, and
one day with leftovers, a margin for a hungry Sunday, or a household that always cooks
double on a Monday.
"""

from collections.abc import Sequence
from datetime import date, time
from decimal import Decimal

from quookly.contracts.errors import PortionsUnknown
from quookly.contracts.plan import Meal, MealPlan
from quookly.contracts.planning import PlannedMeal, PlanRequirements, SizedMeal, Sizing
from quookly.contracts.provisioning import Requirement
from quookly.engines import measure

#: One batch, as the recipe writes it.
AS_WRITTEN = Decimal(1)

#: When each meal is taken to begin. The hours a Swiss household keeps, roughly, and the
#: only evidence available when a cook starts cooking something that was never planned.
MEAL_BEGINS: tuple[tuple[time, Meal], ...] = (
    (time(4, 0), Meal.BREAKFAST),
    (time(11, 0), Meal.LUNCH),
    (time(16, 0), Meal.DINNER),
)


def covering(plans: Sequence[MealPlan], today: date) -> MealPlan | None:
    """The plan today falls inside, if any. Both ends are inclusive.

    The strict question, and the one to ask before *writing*: a meal cooked today can only
    go on a plan whose period contains today. Putting it on last month's week would make
    the plan say something untrue.
    """
    return next((plan for plan in plans if plan.starts_on <= today <= plan.ends_on), None)


def running(plans: Sequence[MealPlan], today: date) -> MealPlan | None:
    """The plan a cook means by "now".

    The one covering today if there is one; otherwise the most recent, because the
    shopping for a week that ended yesterday is still shopping that was not done and an
    empty screen is a worse answer than a stale one.

    The loose question, and the one to ask before *reading*. Reading a stale plan shows a
    cook something true about a week that has passed; writing to one would not.
    """
    if not plans:
        return None
    return covering(plans, today) or max(plans, key=lambda plan: plan.ends_on)


def meal_at(clock: time) -> Meal:
    """Which meal it is at this hour.

    Before the first boundary is the evening before, not the morning after: 01:00 is the
    end of a long dinner. Wrong sometimes and editable when it is, which is a better trade
    than stopping a cook holding a pan to ask which meal this is.
    """
    for begins, meal in reversed(MEAL_BEGINS):
        if clock >= begins:
            return meal
    return Meal.DINNER


def _size(meal: PlannedMeal) -> SizedMeal:
    """How much of this recipe the meal needs, and how sure we are.

    Both fallbacks come to one batch and both say so. Refusing instead would drop the
    meal's ingredients out of the shopping list entirely, which is a worse answer than a
    flagged one — and staying quiet would be the worst of the three: somebody shops for
    one tray and feeds four of the six people they invited.
    """
    if not meal.eaters:
        # Most of a week, most of the time. A plan that needed a guest list before it
        # would buy anything would produce an empty list for a full week.
        return SizedMeal(meal.plan_slot_id, AS_WRITTEN, Sizing.AS_WRITTEN)
    try:
        factor = measure.scaling_for(meal.recipe.yield_quantity, meal.eaters, meal.recipe.serves)
    except PortionsUnknown:
        # "Makes 12 pancakes" and nothing about how many pancakes feed one person
        # (ADR-030). Inventing that figure would misportion the meal silently.
        return SizedMeal(meal.plan_slot_id, AS_WRITTEN, Sizing.UNSCALABLE)
    return SizedMeal(meal.plan_slot_id, factor, Sizing.TO_THE_TABLE)


def requirements_for(meals: Sequence[PlannedMeal]) -> PlanRequirements:
    """Everything a plan needs, meal by meal and ingredient by ingredient.

    One line per meal per ingredient, deliberately unaggregated. Adding the week up is
    the shopping list's job and happens *after* stock has been drawn from — folding two
    meals together here would let a meal that is already covered swell another's line.
    """
    sized: list[SizedMeal] = []
    requirements: list[Requirement] = []

    for meal in meals:
        size = _size(meal)
        sized.append(size)
        for line in meal.recipe.lines:
            if line.optional:
                # A recipe that works without it. Buying it anyway is how a shopping list
                # stops being trusted; a cook who wants it adds it.
                continue
            requirements.append(
                Requirement(
                    plan_slot_id=meal.plan_slot_id,
                    ingredient_id=line.ingredient.id,
                    # Absent stays absent. Twice as much "to taste" is still to taste, and
                    # a scaled zero would put a number on a list nobody wrote.
                    quantity=(
                        None if line.quantity is None else measure.scale(line.quantity, size.factor)
                    ),
                )
            )

    return PlanRequirements(meals=sized, requirements=requirements)
