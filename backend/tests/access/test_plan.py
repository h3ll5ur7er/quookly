"""The week, as stored (UC-4.1, UC-4.2).

A plan is a period and a set of slots, and most of a week is slots that exist without a
recipe in them yet. The tests here are mostly about that: that a half-planned week is a
storable state, that saying who is coming replaces rather than accumulates, and that a
slot holding stock aside cannot be quietly deleted out from under it.
"""

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import eater as eater_access
from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.access import plan as plan_access
from quookly.access import recipe as recipe_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.eater import AgeBand
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.plan import Meal
from quookly.contracts.recipe import IngredientLineDraft, Provenance, RecipeDraft, StepDraft
from quookly.utilities.configuration import get_settings

MONDAY = date(2026, 8, 24)
SUNDAY = date(2026, 8, 30)


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
        density=None,
        names={"en-GB": ["plain flour"]},
    )
    return entry.id


@pytest.fixture
async def recipe_id(cook_id: int, flour: int) -> int:
    stored = await recipe_access.store(
        RecipeDraft(
            title="Pancakes",
            yield_quantity=Quantity(Decimal("12"), Unit.PIECE),
            provenance=Provenance.AUTHORED,
            lines=[
                IngredientLineDraft(
                    ingredient_id=flour, quantity=Quantity(Decimal("250"), Unit.GRAM)
                )
            ],
            steps=[StepDraft(instruction="Whisk it.")],
        ),
        cook_id,
    )
    return stored.id


@pytest.fixture
async def eater_ids(cook_id: int) -> list[int]:
    mira = await eater_access.add(cook_id=cook_id, name="Mira", age_band=AgeBand.CHILD)
    ana = await eater_access.add(cook_id=cook_id, name="Ana", age_band=AgeBand.ADULT)
    return [mira.id, ana.id]


async def test_a_plan_is_a_period(cook_id: int) -> None:
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)

    stored = await plan_access.fetch(plan.id)

    assert stored is not None
    assert (stored.starts_on, stored.ends_on) == (MONDAY, SUNDAY)
    assert stored.slots == []


async def test_a_plan_for_one_day_starts_and_ends_on_it(cook_id: int) -> None:
    """Both dates inclusive, which is the reading that needs no comment at a call site."""
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=MONDAY)

    assert plan.starts_on == plan.ends_on == MONDAY


async def test_a_plan_cannot_end_before_it_begins(cook_id: int) -> None:
    with pytest.raises(ValueError, match="before it begins"):
        await plan_access.create(cook_id=cook_id, starts_on=SUNDAY, ends_on=MONDAY)


async def test_a_slot_can_exist_before_it_has_a_recipe(cook_id: int) -> None:
    """Which is most of a week, most of the time. A slot that needs a recipe to exist
    cannot hold "Thursday, the four of us, something quick"."""
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)

    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)

    assert slot.recipe_id is None
    assert slot.attendee_ids == []


async def test_opening_the_same_slot_twice_is_the_same_slot(cook_id: int) -> None:
    """A cook tapping Monday dinner twice has not asked for two Monday dinners."""
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)

    first = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    again = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)

    assert first.id == again.id
    stored = await plan_access.fetch(plan.id)
    assert stored is not None
    assert len(stored.slots) == 1


async def test_slots_read_back_in_the_order_the_week_runs(cook_id: int) -> None:
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    await plan_access.open_slot(plan.id, on_date=SUNDAY, meal=Meal.LUNCH)
    await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.BREAKFAST)

    stored = await plan_access.fetch(plan.id)

    assert stored is not None
    assert [(slot.on_date, slot.meal) for slot in stored.slots] == [
        (MONDAY, Meal.BREAKFAST),
        (MONDAY, Meal.DINNER),
        (SUNDAY, Meal.LUNCH),
    ]


async def test_a_recipe_can_be_assigned_and_taken_back_off(cook_id: int, recipe_id: int) -> None:
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)

    assigned = await plan_access.assign(slot.id, recipe_id)
    assert assigned is not None
    assert assigned.recipe_id == recipe_id

    cleared = await plan_access.assign(slot.id, None)
    assert cleared is not None
    assert cleared.recipe_id is None


async def test_attendance_is_restated_rather_than_added_to(
    cook_id: int, eater_ids: list[int]
) -> None:
    """The interface edits the whole guest list. Merging would leave somebody at a meal
    the cook took them off — and their allergies would go on being checked against it."""
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)

    await plan_access.attend(slot.id, eater_ids)
    trimmed = await plan_access.attend(slot.id, [eater_ids[0]])

    assert trimmed is not None
    assert trimmed.attendee_ids == [eater_ids[0]]


async def test_naming_the_same_person_twice_seats_them_once(
    cook_id: int, eater_ids: list[int]
) -> None:
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)

    seated = await plan_access.attend(slot.id, [eater_ids[0], eater_ids[0]])

    assert seated is not None
    assert seated.attendee_ids == [eater_ids[0]]


async def test_nobody_named_is_not_the_same_as_nobody_coming(
    cook_id: int, eater_ids: list[int]
) -> None:
    """An empty guest list means nobody has said yet. Judging a meal as suitable for the
    nobody who is attending would be a clean bill of health on a question nobody asked."""
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)

    assert slot.attendee_ids == []


async def test_another_cooks_week_is_not_in_your_list(cook_id: int, other_cook_id: int) -> None:
    await plan_access.create(cook_id=other_cook_id, starts_on=MONDAY, ends_on=SUNDAY)

    assert await plan_access.list_for_cook(cook_id) == []


async def test_closing_a_slot_takes_its_guest_list_with_it(
    cook_id: int, eater_ids: list[int]
) -> None:
    """Left behind, they would seat themselves at whoever next took that id."""
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    await plan_access.attend(slot.id, eater_ids)

    assert await plan_access.close_slot(slot.id) is True

    assert await plan_access.fetch_slot(slot.id) is None
    reopened = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    assert reopened.attendee_ids == []


async def test_a_slot_holding_stock_aside_cannot_be_quietly_closed(
    cook_id: int, flour: int
) -> None:
    """A reservation left pointing at nothing is stock that is neither free nor gone,
    which is the invisible-forever failure ADR-004 exists to prevent. The caller releases
    first; making that an error rather than a cascade is what makes the order impossible
    to get wrong."""
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    lot = await pantry_access.receive(
        cook_id=cook_id, ingredient_id=flour, quantity=Quantity(Decimal("500"), Unit.GRAM)
    )
    await pantry_access.reserve_against(
        lot.id, plan_slot_id=slot.id, quantity=Quantity(Decimal("250"), Unit.GRAM)
    )

    with pytest.raises(ValueError, match="release"):
        await plan_access.close_slot(slot.id)

    assert await plan_access.fetch_slot(slot.id) is not None


async def test_removing_a_plan_takes_its_slots_with_it(cook_id: int, eater_ids: list[int]) -> None:
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    await plan_access.attend(slot.id, eater_ids)

    assert await plan_access.remove(plan.id) is True

    assert await plan_access.fetch(plan.id) is None
    assert await plan_access.fetch_slot(slot.id) is None


async def test_removing_a_plan_that_holds_stock_aside_is_refused(cook_id: int, flour: int) -> None:
    """The counterpart to taking a plan's sessions with it, and the reason the two differ.

    A reservation is a claim on real stock, which lives outside the plan and is the cook's
    to release; cascading it would make stock vanish as a side effect of tidying up a week.
    A cooking session is only the plan's own transcript, so it goes.
    """
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=SUNDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    lot = await pantry_access.receive(
        cook_id=cook_id, ingredient_id=flour, quantity=Quantity(Decimal("500"), Unit.GRAM)
    )
    await pantry_access.reserve_against(
        lot.id, plan_slot_id=slot.id, quantity=Quantity(Decimal("250"), Unit.GRAM)
    )

    with pytest.raises(ValueError, match="release"):
        await plan_access.remove(plan.id)

    assert await plan_access.fetch(plan.id) is not None
