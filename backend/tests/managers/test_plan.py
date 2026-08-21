"""Planning a week, end to end through the manager (UC-4.1 to UC-4.4).

The engines decide what a meal takes and which packet to draw from; this is the part that
sequences them — resolving who is coming, sizing to that table, checking suitability,
reserving, and reporting what could not be reserved as the shopping list.

Most of what is tested here is that the plan and the pantry never come to disagree: that
editing a plan re-provisions it rather than accumulating claims, that reading it changes
nothing, and that taking a meal off gives back what it was holding.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import date
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import eater as eater_access
from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.access import preferences as preference_access
from quookly.access import recipe as recipe_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.eater import AgeBand, Constraint, Severity
from quookly.contracts.events import MealCooked
from quookly.contracts.ingredient import Allergen, IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.plan import Meal, PlanInput, SlotInput
from quookly.contracts.planning import Sizing
from quookly.contracts.recipe import IngredientLineDraft, Provenance, RecipeDraft, StepDraft
from quookly.contracts.suitability import Outcome
from quookly.managers import pantry as pantry_manager
from quookly.managers import plan as plan_manager
from quookly.utilities import events
from quookly.utilities.configuration import get_settings

MONDAY = date(2026, 8, 24)
SUNDAY = date(2026, 8, 30)
ENGLISH = "en-GB"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def cook_id() -> int:
    cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
    return cook.id


@pytest.fixture
async def other_cook_id() -> int:
    cook = await cook_access.register("neighbour@example.com", "Someone", "hash")
    return cook.id


@pytest.fixture
async def flour() -> int:
    entry = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=Decimal("0.53"),
        names={ENGLISH: ["plain flour"]},
        allergens=frozenset({Allergen.GLUTEN}),
    )
    return entry.id


@pytest.fixture
async def pancakes(cook_id: int, flour: int) -> int:
    """Serves four, and every quantity follows from that."""
    stored = await recipe_access.store(
        RecipeDraft(
            title="Pancakes",
            yield_quantity=Quantity(Decimal("4"), Unit.SERVING),
            provenance=Provenance.AUTHORED,
            lines=[
                IngredientLineDraft(
                    ingredient_id=flour, quantity=Quantity(Decimal("200"), Unit.GRAM)
                )
            ],
            steps=[StepDraft(instruction="Whisk.")],
        ),
        cook_id,
    )
    return stored.id


@pytest.fixture
async def ana(cook_id: int) -> int:
    eater = await eater_access.add(cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT)
    return eater.id


@pytest.fixture
async def mira(cook_id: int) -> int:
    """Cannot eat gluten, which is what the flour carries."""
    eater = await eater_access.add(
        cook_id=cook_id,
        name="Mira",
        age_band=AgeBand.CHILD,
        appetite=Decimal("0.6"),
        constraints=[
            Constraint(allergen=Allergen.GLUTEN, ingredient_slug=None, severity=Severity.MEDICAL)
        ],
    )
    return eater.id


async def a_week(cook_id: int) -> int:
    plan = await plan_manager.open_plan(
        PlanInput(starts_on=MONDAY, ends_on=SUNDAY), cook_id, ENGLISH
    )
    return plan.id


async def stock(cook_id: int, ingredient_id: int, amount: str) -> int:
    lot = await pantry_access.receive(
        cook_id=cook_id,
        ingredient_id=ingredient_id,
        quantity=Quantity(Decimal(amount), Unit.GRAM),
    )
    return lot.id


class TestBuildingAWeek:
    async def test_a_new_plan_is_an_empty_period(self, cook_id: int) -> None:
        plan = await plan_manager.open_plan(
            PlanInput(starts_on=MONDAY, ends_on=SUNDAY), cook_id, ENGLISH
        )

        assert (plan.starts_on, plan.ends_on) == (MONDAY, SUNDAY)
        assert plan.slots == []
        assert plan.shopping == []

    async def test_a_meal_can_be_put_down_before_anybody_is_invited(
        self, cook_id: int, pancakes: int
    ) -> None:
        """Most of a week. A plan that needed a guest list first would be unusable."""
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        assert plan is not None
        assert plan.slots[0].recipe_title == "Pancakes"
        assert plan.slots[0].sizing is Sizing.AS_WRITTEN
        assert plan.slots[0].suitability is None

    async def test_saying_who_is_coming_sizes_the_meal_to_them(
        self, cook_id: int, pancakes: int, ana: int, mira: int
    ) -> None:
        """Two people at 1 and 0.6 want 1.6 of the four servings, which is 0.4 of it."""
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id,
            SlotInput(
                on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[ana, mira]
            ),
            cook_id,
        )

        assert plan is not None
        assert plan.slots[0].sizing is Sizing.TO_THE_TABLE
        assert plan.slots[0].factor == "0.4"
        assert plan.slots[0].attendees == ["Ana", "Mira"]

    async def test_stating_a_meal_twice_states_it_rather_than_repeating_it(
        self, cook_id: int, pancakes: int, ana: int
    ) -> None:
        """A statement, not a patch. Sending it again says the same thing again."""
        plan_id = await a_week(cook_id)
        slot = SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[ana])

        await plan_manager.place(plan_id, slot, cook_id)
        plan = await plan_manager.place(plan_id, slot, cook_id)

        assert plan is not None
        assert len(plan.slots) == 1
        assert plan.slots[0].attendee_ids == [ana]

    async def test_taking_somebody_off_a_meal_really_takes_them_off(
        self, cook_id: int, pancakes: int, ana: int, mira: int
    ) -> None:
        """Left seated, their constraints would go on being checked against a meal they
        are not at — a verdict about a table nobody is sitting at."""
        plan_id = await a_week(cook_id)
        await plan_manager.place(
            plan_id,
            SlotInput(
                on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[ana, mira]
            ),
            cook_id,
        )

        plan = await plan_manager.place(
            plan_id,
            SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[ana]),
            cook_id,
        )

        assert plan is not None
        assert plan.slots[0].attendees == ["Ana"]
        assert plan.slots[0].suitability is not None
        assert plan.slots[0].suitability.outcome is Outcome.SUITABLE


class TestWhetherTheyCanEatIt:
    async def test_a_meal_somebody_cannot_eat_is_flagged_rather_than_refused(
        self, cook_id: int, pancakes: int, mira: int
    ) -> None:
        """Flagged (UC-4.3). Refusing would make the cook fight the interface to plan a
        meal they were going to make something else for anyway."""
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id,
            SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[mira]),
            cook_id,
        )

        assert plan is not None
        assert plan.slots[0].suitability is not None
        assert plan.slots[0].suitability.outcome is Outcome.UNSUITABLE
        assert plan.slots[0].suitability.findings[0].eater == "Mira"

    async def test_nobody_at_the_table_gets_no_verdict(self, cook_id: int, pancakes: int) -> None:
        """Not `suitable`. An empty table satisfies every constraint there is, and saying
        so would be a reassurance about a question nobody asked."""
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        assert plan is not None
        assert plan.slots[0].suitability is None


class TestWhatHasToBeBought:
    async def test_an_empty_pantry_puts_the_whole_meal_on_the_list(
        self, cook_id: int, pancakes: int
    ) -> None:
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        assert plan is not None
        assert [(line.name, line.quantity) for line in plan.shopping] == [("plain flour", "200 g")]

    async def test_what_is_already_in_the_kitchen_is_not_bought_again(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        assert plan is not None
        assert plan.shopping == []

    async def test_only_the_shortfall_is_bought(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        await stock(cook_id, flour, "150")
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        assert plan is not None
        assert [line.quantity for line in plan.shopping] == ["50 g"]

    async def test_planning_holds_the_stock_rather_than_removing_it(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        """The flour is still in the cupboard. That is the whole of ADR-004."""
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        held = await pantry_access.fetch(lot_id)
        assert held is not None
        assert held.quantity == Quantity(Decimal("500.0000"), Unit.GRAM)
        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("300.0000"), Unit.GRAM)

    async def test_the_list_is_added_up_across_the_week(self, cook_id: int, pancakes: int) -> None:
        """One line for flour, not one per meal. A cook in a shop wants to know how much
        to buy, not how the week decomposes (FR-7)."""
        plan_id = await a_week(cook_id)
        await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=SUNDAY, meal=Meal.LUNCH, recipe_id=pancakes), cook_id
        )

        assert plan is not None
        assert [line.quantity for line in plan.shopping] == ["400 g"]

    async def test_the_list_is_read_in_the_cooks_own_units(
        self, cook_id: int, pancakes: int
    ) -> None:
        """`MeasureEngine` renders it the way the recipe screen does, so a cook is not
        reading two vocabularies for the same flour (UC-6.2)."""
        await preference_access.choose(cook_id, IngredientKind.POWDER, Unit.OUNCE)
        plan_id = await a_week(cook_id)
        for meal in (Meal.BREAKFAST, Meal.LUNCH, Meal.DINNER):
            plan = await plan_manager.place(
                plan_id, SlotInput(on_date=MONDAY, meal=meal, recipe_id=pancakes), cook_id
            )

        assert plan is not None
        # 600 g is 21.16 oz, which is a pound and a bit — and a pound is how somebody who
        # reads ounces would write it down.
        assert [line.quantity for line in plan.shopping] == ["1.32 lb"]


class TestKeepingThePlanAndThePantryInStep:
    async def test_editing_a_plan_does_not_accumulate_claims(
        self, cook_id: int, pancakes: int, flour: int, ana: int
    ) -> None:
        """Every change releases and re-reserves, so five edits leave one claim rather
        than five. Stock spoken for by an edit nobody made is invisible forever."""
        lot_id = await stock(cook_id, flour, "1000")
        plan_id = await a_week(cook_id)

        for _ in range(5):
            await plan_manager.place(
                plan_id,
                SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[ana]),
                cook_id,
            )

        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("950.0000"), Unit.GRAM)

    async def test_reading_a_plan_changes_nothing(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        """A GET that reserved would mean opening a plan on two devices reserved twice."""
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        before = await pantry_access.held_for_slot(
            (await plan_manager.present(plan_id, cook_id, ENGLISH)).slots[0].id  # type: ignore[union-attr]
        )
        for _ in range(3):
            await plan_manager.present(plan_id, cook_id, ENGLISH)

        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("300.0000"), Unit.GRAM)
        assert len(before) == 1

    async def test_taking_a_meal_off_gives_back_what_it_was_holding(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        assert placed is not None

        cleared = await plan_manager.clear(plan_id, placed.slots[0].id, cook_id)

        assert cleared is not None
        assert cleared.slots == []
        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("500.0000"), Unit.GRAM)

    async def test_taking_the_recipe_out_of_a_meal_gives_back_its_stock(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        """Undecided again is a state a cook returns to, and the flour should be free
        while they are deciding."""
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER), cook_id
        )

        assert plan is not None
        assert plan.slots[0].recipe_id is None
        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("500.0000"), Unit.GRAM)

    async def test_forgetting_a_plan_gives_everything_back(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )

        assert await plan_manager.discard(plan_id, cook_id) is True

        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("500.0000"), Unit.GRAM)

    async def test_two_meals_do_not_both_get_the_same_flour(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        await stock(cook_id, flour, "300")
        plan_id = await a_week(cook_id)
        await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=SUNDAY, meal=Meal.LUNCH, recipe_id=pancakes), cook_id
        )

        assert plan is not None
        # 400 g wanted, 300 g on the shelf.
        assert [line.quantity for line in plan.shopping] == ["100 g"]


class TestWhoseWeekItIs:
    async def test_another_cooks_plan_is_not_yours(self, cook_id: int, other_cook_id: int) -> None:
        theirs = await a_week(other_cook_id)

        assert await plan_manager.present(theirs, cook_id, ENGLISH) is None
        assert (
            await plan_manager.place(theirs, SlotInput(on_date=MONDAY, meal=Meal.DINNER), cook_id)
            is None
        )
        assert await plan_manager.discard(theirs, cook_id) is False
        assert await plan_manager.list_for(cook_id) == []

    async def test_another_cooks_recipe_cannot_be_planned(
        self, cook_id: int, other_cook_id: int, flour: int
    ) -> None:
        """It reads as no recipe rather than as a refusal: an id belonging to somebody
        else is not theirs to be told about."""
        theirs = await recipe_access.store(
            RecipeDraft(
                title="Secret",
                yield_quantity=Quantity(Decimal("4"), Unit.SERVING),
                provenance=Provenance.AUTHORED,
                lines=[IngredientLineDraft(ingredient_id=flour)],
                steps=[StepDraft(instruction="Hush.")],
            ),
            other_cook_id,
        )
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=theirs.id), cook_id
        )

        assert plan is not None
        assert plan.slots[0].recipe_id is None

    async def test_another_households_eater_cannot_be_seated(
        self, cook_id: int, other_cook_id: int, pancakes: int
    ) -> None:
        """Seating them would run their allergies against somebody else's dinner."""
        theirs = await eater_access.add(
            cook_id=other_cook_id, name="Stranger", age_band=AgeBand.ADULT
        )
        plan_id = await a_week(cook_id)

        plan = await plan_manager.place(
            plan_id,
            SlotInput(
                on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[theirs.id]
            ),
            cook_id,
        )

        assert plan is not None
        assert plan.slots[0].attendee_ids == []


class TestCookingAPlannedMeal:
    """UC-4.5 and FR-19, and the first thing the event bus carries.

    `PlanningManager` states that a meal was cooked; `PantryManager` listens and turns
    that meal's claims into consumption. Neither knows the other exists — which is the
    Manager-must-not-call-Manager rule doing useful work rather than merely being obeyed.
    """

    @pytest.fixture(autouse=True)
    def listening(self) -> Iterator[None]:
        events.forget_everything()
        events.subscribe(MealCooked, pantry_manager.on_meal_cooked)
        yield
        events.forget_everything()

    async def test_cooking_takes_what_the_meal_was_holding(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        assert placed is not None

        plan = await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id)

        assert plan is not None
        assert plan.slots[0].cooked is True
        remaining = await pantry_access.fetch(lot_id)
        assert remaining is not None
        assert remaining.quantity == Quantity(Decimal("300.0000"), Unit.GRAM)

    async def test_a_cooked_meal_needs_no_shopping(self, cook_id: int, pancakes: int) -> None:
        """It is a record rather than a plan. The food is eaten."""
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        assert placed is not None
        assert placed.shopping != []

        plan = await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id)

        assert plan is not None
        assert plan.shopping == []

    async def test_a_cooked_meal_still_says_what_it_was(
        self, cook_id: int, pancakes: int, ana: int
    ) -> None:
        """Out of the sizing, but not out of the week. A record with the dish missing
        would be no record at all."""
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id,
            SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes, attendee_ids=[ana]),
            cook_id,
        )
        assert placed is not None

        plan = await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id)

        assert plan is not None
        assert plan.slots[0].recipe_title == "Pancakes"
        assert plan.slots[0].attendees == ["Ana"]

    async def test_cooking_it_twice_does_not_take_it_twice(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        """Idempotent by construction: a meal whose claims are consumed holds none, and
        consuming none consumes nothing. That is what makes it safe to state the fact
        again after a failure part-way through."""
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        assert placed is not None

        await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id)
        await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id)

        remaining = await pantry_access.fetch(lot_id)
        assert remaining is not None
        assert remaining.quantity == Quantity(Decimal("300.0000"), Unit.GRAM)

    async def test_a_cooked_meal_is_not_edited(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        """Editing one would re-reserve stock for food that has been eaten, and there is
        no honest way to un-cook it."""
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        assert placed is not None
        await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id)

        assert (
            await plan_manager.place(plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER), cook_id)
            is None
        )
        assert await plan_manager.clear(plan_id, placed.slots[0].id, cook_id) is None

        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("300.0000"), Unit.GRAM)

    async def test_editing_another_meal_leaves_the_cooked_one_alone(
        self, cook_id: int, pancakes: int, flour: int
    ) -> None:
        """Every change restates the plan's reservations (ADR-038). A cooked meal must
        not be handed its stock back by somebody planning Thursday."""
        lot_id = await stock(cook_id, flour, "500")
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER, recipe_id=pancakes), cook_id
        )
        assert placed is not None
        await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id)

        await plan_manager.place(
            plan_id, SlotInput(on_date=SUNDAY, meal=Meal.LUNCH, recipe_id=pancakes), cook_id
        )

        remaining = await pantry_access.fetch(lot_id)
        assert remaining is not None
        assert remaining.quantity == Quantity(Decimal("300.0000"), Unit.GRAM)
        spare = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
        assert spare.free == Quantity(Decimal("100.0000"), Unit.GRAM)

    async def test_a_meal_with_no_dish_was_not_cooked(self, cook_id: int) -> None:
        """It was skipped. Marking it would put a meal in the record nobody ate."""
        plan_id = await a_week(cook_id)
        placed = await plan_manager.place(
            plan_id, SlotInput(on_date=MONDAY, meal=Meal.DINNER), cook_id
        )
        assert placed is not None

        assert await plan_manager.mark_cooked(plan_id, placed.slots[0].id, cook_id) is None

    async def test_another_cooks_meal_cannot_be_cooked(
        self, cook_id: int, other_cook_id: int
    ) -> None:
        theirs = await a_week(other_cook_id)

        assert await plan_manager.mark_cooked(theirs, 1, cook_id) is None
