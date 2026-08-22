"""Working out what a planned week takes (V7, UC-4.1).

A rule engine: recipes and eaters arrive as arguments, so the sizing rule is a table of
cases rather than a fixture.

The interesting cases are the two where a meal cannot be sized to its table. Both produce
a shopping list for one batch, which is right often enough to be worth doing — and both
say so, because the silent version is somebody shopping for one tray and feeding four of
the six people they invited.
"""

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from quookly.contracts.eater import AgeBand, Eater
from quookly.contracts.ingredient import Ingredient, IngredientKind, Origin
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.plan import Meal, MealPlan
from quookly.contracts.planning import PlannedMeal, Sizing
from quookly.contracts.recipe import IngredientLine, Provenance, Recipe, Visibility
from quookly.engines import planning

FLOUR = 1
SALT = 2


def ingredient(ingredient_id: int, slug: str) -> Ingredient:
    return Ingredient(
        id=ingredient_id,
        slug=slug,
        kind=IngredientKind.POWDER,
        name=slug,
        density=None,
        origin=Origin.USER,
    )


def recipe(
    *,
    makes: str = "4",
    unit: Unit = Unit.SERVING,
    serves: str | None = None,
    lines: list[IngredientLine] | None = None,
) -> Recipe:
    return Recipe(
        id=1,
        cook_id=1,
        title="Pancakes",
        summary=None,
        yield_quantity=Quantity(Decimal(makes), unit),
        serves=None if serves is None else Decimal(serves),
        provenance=Provenance.AUTHORED,
        visibility=Visibility.PRIVATE,
        origin=Origin.USER,
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        lines=lines
        if lines is not None
        else [
            IngredientLine(
                id=1,
                ingredient=ingredient(FLOUR, "plain-flour"),
                quantity=Quantity(Decimal("200"), Unit.GRAM),
                preparation=None,
                optional=False,
            )
        ],
    )


def person(name: str, appetite: str) -> Eater:
    return Eater(
        id=hash(name) % 1000,
        cook_id=1,
        name=name,
        age_band=AgeBand.ADULT,
        appetite=Decimal(appetite),
    )


def test_a_week_with_nothing_in_it_needs_nothing() -> None:
    needed = planning.requirements_for([])

    assert needed.meals == []
    assert needed.requirements == []


def test_a_meal_is_sized_to_the_appetites_at_it() -> None:
    """Not to a head count. Three people at 0.3, 1.4 and 0.6 want 2.3 servings of a
    recipe that makes four, which is a bit over half of it (FR-18)."""
    table = [person("Toddler", "0.3"), person("Teen", "1.4"), person("Nonna", "0.6")]

    needed = planning.requirements_for(
        [PlannedMeal(plan_slot_id=10, recipe=recipe(), eaters=table)]
    )

    assert needed.meals[0].sizing is Sizing.TO_THE_TABLE
    assert needed.meals[0].factor == Decimal("0.575")
    assert needed.requirements[0].quantity == Quantity(Decimal("115.000"), Unit.GRAM)


def test_a_recipe_that_only_counts_things_is_sized_by_how_many_it_feeds() -> None:
    """Makes 12, serves 4. Six people want one and a half times the recipe, and twelve
    pancakes never had to become a unit of appetite."""
    table = [person(f"Guest {n}", "1") for n in range(6)]
    meal = PlannedMeal(
        plan_slot_id=10, recipe=recipe(makes="12", unit=Unit.PIECE, serves="4"), eaters=table
    )

    needed = planning.requirements_for([meal])

    assert needed.meals[0].sizing is Sizing.TO_THE_TABLE
    assert needed.meals[0].factor == Decimal("1.5")


def test_a_meal_nobody_has_been_invited_to_is_still_shopped_for() -> None:
    """Most of a week is slots with no guest list yet. A plan that needed one before it
    would buy anything would produce an empty list for a full week."""
    needed = planning.requirements_for([PlannedMeal(plan_slot_id=10, recipe=recipe())])

    assert needed.meals[0].sizing is Sizing.AS_WRITTEN
    assert needed.meals[0].factor == 1
    assert needed.requirements[0].quantity == Quantity(Decimal("200"), Unit.GRAM)


def test_a_recipe_that_will_not_say_how_many_it_feeds_is_flagged() -> None:
    """One batch, and said out loud. Guessing a pieces-per-serving figure would misportion
    the meal silently, which is the refusal ADR-030 recorded."""
    table = [person(f"Guest {n}", "1") for n in range(6)]
    meal = PlannedMeal(plan_slot_id=10, recipe=recipe(makes="12", unit=Unit.PIECE), eaters=table)

    needed = planning.requirements_for([meal])

    assert needed.meals[0].sizing is Sizing.UNSCALABLE
    assert needed.meals[0].factor == 1


def test_a_line_with_no_quantity_stays_without_one() -> None:
    """Salt to taste. Twice as much to taste is still to taste, and a scaled zero would
    put a number on a shopping list that nobody wrote."""
    lines = [
        IngredientLine(
            id=2,
            ingredient=ingredient(SALT, "fine-salt"),
            quantity=None,
            preparation="to taste",
            optional=False,
        )
    ]
    meal = PlannedMeal(plan_slot_id=10, recipe=recipe(lines=lines), eaters=[person("A", "2")])

    needed = planning.requirements_for([meal])

    assert needed.requirements[0].quantity is None


def test_an_optional_line_is_not_shopped_for() -> None:
    """A recipe that works without it. Buying it anyway is how a shopping list stops
    being trusted — and an optional ingredient the cook does want is one they add."""
    lines = [
        IngredientLine(
            id=1,
            ingredient=ingredient(FLOUR, "plain-flour"),
            quantity=Quantity(Decimal("200"), Unit.GRAM),
            preparation=None,
            optional=False,
        ),
        IngredientLine(
            id=2,
            ingredient=ingredient(SALT, "fine-salt"),
            quantity=Quantity(Decimal("5"), Unit.GRAM),
            preparation=None,
            optional=True,
        ),
    ]
    meal = PlannedMeal(plan_slot_id=10, recipe=recipe(lines=lines))

    needed = planning.requirements_for([meal])

    assert [one.ingredient_id for one in needed.requirements] == [FLOUR]


def test_every_meal_keeps_its_own_line() -> None:
    """Aggregating across the week is the shopping list's job, and it happens after stock
    has been drawn from — a meal that is covered must not swell somebody else's line."""
    meals = [
        PlannedMeal(plan_slot_id=10, recipe=recipe()),
        PlannedMeal(plan_slot_id=11, recipe=recipe()),
    ]

    needed = planning.requirements_for(meals)

    assert [one.plan_slot_id for one in needed.requirements] == [10, 11]


@pytest.mark.parametrize("appetite", ["0.01", "10"])
def test_an_unusual_table_is_still_a_table(appetite: str) -> None:
    needed = planning.requirements_for(
        [PlannedMeal(plan_slot_id=10, recipe=recipe(), eaters=[person("A", appetite)])]
    )

    assert needed.meals[0].sizing is Sizing.TO_THE_TABLE
    assert needed.meals[0].factor == Decimal(appetite) / 4


class TestWhichPlanIsRunning:
    """The rule two managers need: which of a cook's plans is the one they mean by "now".

    Extracted here when cooking a recipe outright wanted the same answer the plan screen
    already had. A rule with two callers is a rule, not a line inside one of them.
    """

    def a_plan(self, starts: str, ends: str) -> MealPlan:
        return MealPlan(
            id=hash((starts, ends)) % 1000,
            cook_id=1,
            starts_on=date.fromisoformat(starts),
            ends_on=date.fromisoformat(ends),
            slots=[],
        )

    def test_nothing_planned_is_nothing_running(self) -> None:
        assert planning.running([], date(2026, 8, 21)) is None

    def test_the_week_today_falls_in(self) -> None:
        last = self.a_plan("2026-08-10", "2026-08-16")
        this = self.a_plan("2026-08-17", "2026-08-23")
        assert planning.running([this, last], date(2026, 8, 21)) is this

    def test_the_first_day_and_the_last_day_are_both_in_it(self) -> None:
        """A plan that does not cover its own last day would drop a cook on a Sunday."""
        week = self.a_plan("2026-08-17", "2026-08-23")
        assert planning.running([week], date(2026, 8, 17)) is week
        assert planning.running([week], date(2026, 8, 23)) is week

    def test_between_weeks_the_most_recent_is_what_is_meant(self) -> None:
        """Not None. The shopping for a week that ended yesterday is still shopping that
        was not done, and an empty screen is a worse answer than a stale one."""
        last = self.a_plan("2026-08-10", "2026-08-16")
        older = self.a_plan("2026-08-03", "2026-08-09")
        assert planning.running([last, older], date(2026, 8, 21)) is last

    def test_writing_asks_the_stricter_question(self) -> None:
        """`covering` is what a meal being placed on today must ask. Last week is a fine
        answer to "what am I looking at" and a wrong one to "where does this go"."""
        last = self.a_plan("2026-08-10", "2026-08-16")
        assert planning.covering([last], date(2026, 8, 21)) is None
        assert planning.running([last], date(2026, 8, 21)) is last

    def test_the_most_recent_is_found_however_they_arrive(self) -> None:
        """Callers hand over whatever order the store gave them; the rule does not depend
        on it."""
        last = self.a_plan("2026-08-10", "2026-08-16")
        older = self.a_plan("2026-08-03", "2026-08-09")
        assert planning.running([older, last], date(2026, 8, 21)) is last


class TestWhichMealItIs:
    """Cooking something outright has to record *a* meal, and the clock is the only
    evidence available. A guess that is right most of the time and editable when it is
    wrong beats asking a cook holding a pan which meal this is."""

    @pytest.mark.parametrize(
        ("hour", "expected"),
        [
            (6, Meal.BREAKFAST),
            (9, Meal.BREAKFAST),
            (11, Meal.LUNCH),
            (14, Meal.LUNCH),
            (17, Meal.DINNER),
            (21, Meal.DINNER),
        ],
    )
    def test_the_hour_says_which_meal(self, hour: int, expected: Meal) -> None:
        assert planning.meal_at(time(hour, 0)) is expected

    def test_cooking_after_midnight_is_still_the_evening(self) -> None:
        """01:00 is the end of a long dinner, not the beginning of breakfast. A snack at
        that hour lands on the day the cook thinks they are still in."""
        assert planning.meal_at(time(1, 30)) is Meal.DINNER
