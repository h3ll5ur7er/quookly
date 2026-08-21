"""What is in the kitchen, as stored (UC-5.1 to UC-5.4).

Stock is the one part of the system a cook will notice is wrong within a day, because
they can see the fridge. The tests below are mostly about the ways a pantry starts
lying: a lot losing its date, quantities going somewhere without a record, one cook's
shelf showing up on another's, and waste that cannot be told from food that was eaten.
"""

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.access import plan as plan_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.pantry import WasteReason
from quookly.contracts.plan import Meal
from quookly.utilities.configuration import get_settings


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
async def butter() -> int:
    entry = await registry.register(
        slug="unsalted-butter",
        kind=IngredientKind.SOLID,
        density=None,
        names={"en-GB": ["unsalted butter"]},
    )
    return entry.id


@pytest.fixture
async def flour() -> int:
    entry = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=None,
        names={"en-GB": ["plain flour"]},
    )
    return entry.id


def grams(amount: str) -> Quantity:
    return Quantity(magnitude=Decimal(amount), unit=Unit.GRAM)


async def test_received_stock_reads_back_whole(cook_id: int, butter: int) -> None:
    lot = await pantry_access.receive(
        cook_id=cook_id,
        ingredient_id=butter,
        quantity=grams("250"),
        expires_on=date(2026, 9, 30),
        note="Coop",
    )

    stored = await pantry_access.fetch(lot.id)

    assert stored is not None
    assert stored.quantity == grams("250")
    assert stored.expires_on == date(2026, 9, 30)
    assert stored.note == "Coop"


async def test_two_receipts_are_two_lots(cook_id: int, butter: int) -> None:
    """Not merged into a total. One packet expires before the other."""
    await pantry_access.receive(
        cook_id=cook_id, ingredient_id=butter, quantity=grams("250"), expires_on=date(2026, 9, 30)
    )
    await pantry_access.receive(
        cook_id=cook_id, ingredient_id=butter, quantity=grams("250"), expires_on=date(2026, 12, 1)
    )

    held = await pantry_access.list_for_cook(cook_id)

    assert [lot.expires_on for lot in held] == [date(2026, 9, 30), date(2026, 12, 1)]


async def test_another_cooks_shelf_is_not_yours(
    cook_id: int, other_cook_id: int, butter: int
) -> None:
    await pantry_access.receive(cook_id=other_cook_id, ingredient_id=butter, quantity=grams("250"))

    assert await pantry_access.list_for_cook(cook_id) == []


async def test_adjusting_restates_rather_than_subtracts(cook_id: int, flour: int) -> None:
    """Sent twice, it says the same thing twice. A delta sent twice subtracts twice."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("1000"))

    await pantry_access.adjust(lot.id, Decimal("700"))
    await pantry_access.adjust(lot.id, Decimal("700"))

    stored = await pantry_access.fetch(lot.id)
    assert stored is not None
    assert stored.quantity == grams("700")


async def test_an_emptied_lot_leaves_the_shelf(cook_id: int, flour: int) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("1000"))

    await pantry_access.adjust(lot.id, Decimal("0"))

    assert await pantry_access.list_for_cook(cook_id) == []
    # The row survives, because waste records point at it.
    assert await pantry_access.fetch(lot.id) is not None


async def test_stock_cannot_go_negative(cook_id: int, flour: int) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("1000"))

    with pytest.raises(ValueError, match="negative"):
        await pantry_access.adjust(lot.id, Decimal("-1"))


async def test_waste_is_recorded_as_its_own_fact(cook_id: int, flour: int) -> None:
    """Not inferred from stock falling. A subtraction cannot say why."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("1000"))

    await pantry_access.record_waste(
        lot.id, quantity=grams("300"), reason=WasteReason.SPOILED, note="weevils"
    )

    remaining = await pantry_access.fetch(lot.id)
    assert remaining is not None
    assert remaining.quantity == grams("700")

    thrown = await pantry_access.waste_for_cook(cook_id)
    assert len(thrown) == 1
    assert thrown[0].reason is WasteReason.SPOILED
    assert thrown[0].quantity == grams("300")
    assert thrown[0].ingredient_id == flour
    assert thrown[0].note == "weevils"


async def test_waste_outlives_the_lot_it_came_from(cook_id: int, flour: int) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("1000"))
    await pantry_access.record_waste(lot.id, quantity=grams("1000"), reason=WasteReason.EXPIRED)

    thrown = await pantry_access.waste_for_cook(cook_id)

    assert await pantry_access.list_for_cook(cook_id) == []
    assert [record.quantity for record in thrown] == [grams("1000")]


async def test_you_cannot_throw_away_what_you_do_not_have(cook_id: int, flour: int) -> None:
    """Otherwise the pantry goes negative and the waste report reads as fiction."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("200"))

    with pytest.raises(ValueError, match="more than"):
        await pantry_access.record_waste(lot.id, quantity=grams("300"), reason=WasteReason.SPOILED)

    stored = await pantry_access.fetch(lot.id)
    assert stored is not None
    assert stored.quantity == grams("200")


async def test_a_quantity_in_the_wrong_unit_is_refused(cook_id: int, flour: int) -> None:
    """Access does not convert — that is `MeasureEngine`, which sits above it. A unit that
    does not match is a caller's mistake, and silently reading 300 kg as 300 g is the
    kind of mistake that empties a pantry."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("200"))

    with pytest.raises(ValueError, match="held in"):
        await pantry_access.record_waste(
            lot.id,
            quantity=Quantity(magnitude=Decimal("1"), unit=Unit.KILOGRAM),
            reason=WasteReason.SPOILED,
        )


async def test_expiring_lots_come_back_soonest_first(cook_id: int, butter: int, flour: int) -> None:
    await pantry_access.receive(
        cook_id=cook_id, ingredient_id=flour, quantity=grams("500"), expires_on=date(2026, 12, 1)
    )
    await pantry_access.receive(
        cook_id=cook_id, ingredient_id=butter, quantity=grams("250"), expires_on=date(2026, 9, 3)
    )
    # Undated stock never expires and must never be reported as if it might.
    await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))

    soon = await pantry_access.expiring_before(cook_id, date(2026, 12, 31))

    assert [lot.expires_on for lot in soon] == [date(2026, 9, 3), date(2026, 12, 1)]


async def test_expiring_before_ignores_an_emptied_lot(cook_id: int, butter: int) -> None:
    """An empty packet cannot go off, and warning about one is how a cook learns to
    ignore the warnings."""
    lot = await pantry_access.receive(
        cook_id=cook_id, ingredient_id=butter, quantity=grams("250"), expires_on=date(2026, 9, 3)
    )
    await pantry_access.adjust(lot.id, Decimal("0"))

    assert await pantry_access.expiring_before(cook_id, date(2026, 12, 31)) == []


async def test_discarding_a_lot_removes_it_without_calling_it_waste(
    cook_id: int, flour: int
) -> None:
    """A lot entered by mistake never existed. Recording it as waste would put food that
    was never bought into the number the cook is trying to bring down."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("200"))

    assert await pantry_access.remove(lot.id) is True
    assert await pantry_access.fetch(lot.id) is None
    assert await pantry_access.waste_for_cook(cook_id) == []


async def test_a_lot_with_waste_against_it_cannot_be_deleted(cook_id: int, flour: int) -> None:
    """Deleting it would leave the waste record pointing at nothing, and quietly shrink
    the history the cook is trying to learn from."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("200"))
    await pantry_access.record_waste(lot.id, quantity=grams("50"), reason=WasteReason.SPOILED)

    with pytest.raises(ValueError, match="adjust it to zero"):
        await pantry_access.remove(lot.id)

    assert await pantry_access.fetch(lot.id) is not None


async def test_only_the_named_ingredients_come_back(cook_id: int, butter: int, flour: int) -> None:
    """What the shopping list asks: not the whole shelf, only the recipe's ingredients."""
    await pantry_access.receive(cook_id=cook_id, ingredient_id=butter, quantity=grams("250"))
    await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))

    held = await pantry_access.for_ingredients(cook_id, [flour])

    assert [lot.ingredient_id for lot in held] == [flour]
    assert await pantry_access.for_ingredients(cook_id, []) == []


# Reservations (ADR-004). A plan holds stock aside; cooking takes it; cancelling gives it
# back. Release is the path most likely to be got wrong and the most expensive when it is,
# because stock that is neither free nor gone is invisible forever — which is precisely
# the waste this product exists to reduce.


@pytest.fixture
async def slot_id(cook_id: int) -> int:
    plan = await plan_access.create(
        cook_id=cook_id, starts_on=date(2026, 8, 24), ends_on=date(2026, 8, 30)
    )
    slot = await plan_access.open_slot(plan.id, on_date=date(2026, 8, 26), meal=Meal.DINNER)
    return slot.id


@pytest.fixture
async def other_slot_id(cook_id: int) -> int:
    plan = await plan_access.create(
        cook_id=cook_id, starts_on=date(2026, 8, 24), ends_on=date(2026, 8, 30)
    )
    slot = await plan_access.open_slot(plan.id, on_date=date(2026, 8, 27), meal=Meal.DINNER)
    return slot.id


async def free_of(cook_id: int, lot_id: int) -> Quantity:
    """How much of one lot nothing has claimed."""
    found = next(one for one in await pantry_access.available(cook_id) if one.lot.id == lot_id)
    return found.free


async def test_reserving_holds_stock_without_removing_it(
    cook_id: int, flour: int, slot_id: int
) -> None:
    """The butter is still in the fridge. That is the whole of ADR-004."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))

    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("300"))

    stored = await pantry_access.fetch(lot.id)
    assert stored is not None
    assert stored.quantity == grams("500")
    assert await free_of(cook_id, lot.id) == grams("200")


async def test_two_meals_cannot_claim_the_same_butter(
    cook_id: int, flour: int, slot_id: int, other_slot_id: int
) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("300"))

    with pytest.raises(ValueError, match="only 200"):
        await pantry_access.reserve_against(
            lot.id, plan_slot_id=other_slot_id, quantity=grams("300")
        )

    assert await free_of(cook_id, lot.id) == grams("200")


async def test_the_last_of_a_lot_can_be_claimed(cook_id: int, flour: int, slot_id: int) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))

    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("500"))

    assert await free_of(cook_id, lot.id) == grams("0")


async def test_a_fully_claimed_lot_is_still_on_the_shelf(
    cook_id: int, flour: int, slot_id: int
) -> None:
    """It is there, only spoken for. Hiding it would read as "you have no flour", which is
    not what a cook standing in front of the cupboard would say."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("500"))

    assert [one.lot.id for one in await pantry_access.available(cook_id)] == [lot.id]
    assert await pantry_access.list_for_cook(cook_id) != []


async def test_a_claim_in_the_wrong_unit_is_refused(cook_id: int, flour: int, slot_id: int) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))

    with pytest.raises(ValueError, match="held in"):
        await pantry_access.reserve_against(
            lot.id,
            plan_slot_id=slot_id,
            quantity=Quantity(magnitude=Decimal("1"), unit=Unit.KILOGRAM),
        )


async def test_releasing_gives_it_back_and_leaves_the_stock_alone(
    cook_id: int, butter: int, flour: int, slot_id: int
) -> None:
    """A cook changes their mind and cooks something else. The ingredients are simply
    still there — nothing has to be re-added, which is the case that decided ADR-004."""
    one = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    two = await pantry_access.receive(cook_id=cook_id, ingredient_id=butter, quantity=grams("250"))
    await pantry_access.reserve_against(one.id, plan_slot_id=slot_id, quantity=grams("300"))
    await pantry_access.reserve_against(two.id, plan_slot_id=slot_id, quantity=grams("100"))

    let_go = await pantry_access.release_for_slot(slot_id)

    assert sorted(record.quantity.magnitude for record in let_go) == [
        Decimal("100"),
        Decimal("300"),
    ]
    assert await free_of(cook_id, one.id) == grams("500")
    assert await free_of(cook_id, two.id) == grams("250")
    assert (await pantry_access.fetch(one.id)).quantity == grams("500")  # type: ignore[union-attr]


async def test_releasing_a_meal_that_holds_nothing_is_not_an_error(slot_id: int) -> None:
    """Cancelling a plan releases every slot, and most slots hold nothing."""
    assert await pantry_access.release_for_slot(slot_id) == []


async def test_releasing_leaves_other_meals_alone(
    cook_id: int, flour: int, slot_id: int, other_slot_id: int
) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("200"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=other_slot_id, quantity=grams("200"))

    await pantry_access.release_for_slot(slot_id)

    assert await free_of(cook_id, lot.id) == grams("300")
    assert [record.plan_slot_id for record in await pantry_access.held_for_slot(other_slot_id)] == [
        other_slot_id
    ]


async def test_cooking_takes_what_was_held(cook_id: int, flour: int, slot_id: int) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("300"))

    taken = await pantry_access.consume_for_slot(slot_id)

    assert [record.quantity for record in taken] == [grams("300")]
    stored = await pantry_access.fetch(lot.id)
    assert stored is not None
    assert stored.quantity == grams("200")
    assert await pantry_access.held_for_slot(slot_id) == []


async def test_cooking_the_last_of_something_empties_the_lot(
    cook_id: int, flour: int, slot_id: int
) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("500"))

    await pantry_access.consume_for_slot(slot_id)

    assert await pantry_access.list_for_cook(cook_id) == []


async def test_a_meal_that_held_nothing_consumes_nothing(cook_id: int, slot_id: int) -> None:
    assert await pantry_access.consume_for_slot(slot_id) == []


async def test_the_fridge_wins_over_the_plan(cook_id: int, flour: int, slot_id: int) -> None:
    """A cook reporting less than a plan claimed is telling the truth about their own
    kitchen. The claim gives way, and is named so the plan can be told it needs shopping
    for — silently keeping it would leave stock that is neither free nor there."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("400"))

    adjusted = await pantry_access.adjust(lot.id, Decimal("100"))

    assert adjusted is not None
    # The claim is cut down to what survives, not dropped: the meal is still going to use
    # what is left. What it lost is named, so the plan can be told it needs shopping for.
    assert [record.quantity for record in adjusted.released] == [grams("300")]
    assert [record.quantity for record in await pantry_access.held_for_slot(slot_id)] == [
        grams("100")
    ]
    assert await free_of(cook_id, lot.id) == grams("0")


async def test_only_the_excess_claim_gives_way(
    cook_id: int, flour: int, slot_id: int, other_slot_id: int
) -> None:
    """The most recent claim yields first. Somebody has to, and "last to ask, first to go"
    is a rule a person accepts without needing it explained."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("200"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=other_slot_id, quantity=grams("200"))

    adjusted = await pantry_access.adjust(lot.id, Decimal("200"))

    assert adjusted is not None
    assert [record.plan_slot_id for record in adjusted.released] == [other_slot_id]
    assert await pantry_access.held_for_slot(slot_id) != []
    assert await pantry_access.held_for_slot(other_slot_id) == []


async def test_a_claim_larger_than_what_is_left_is_cut_down_rather_than_dropped(
    cook_id: int, flour: int, slot_id: int
) -> None:
    """300 g claimed and 100 g left is a claim on 100 g, not on nothing. Dropping it
    whole would free stock the meal is still going to use."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("300"))

    adjusted = await pantry_access.adjust(lot.id, Decimal("100"))

    assert adjusted is not None
    assert [record.quantity for record in adjusted.released] == [grams("200")]
    assert [record.quantity for record in await pantry_access.held_for_slot(slot_id)] == [
        grams("100")
    ]


async def test_restating_upward_disturbs_nothing(cook_id: int, flour: int, slot_id: int) -> None:
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("400"))

    adjusted = await pantry_access.adjust(lot.id, Decimal("900"))

    assert adjusted is not None
    assert adjusted.released == []
    assert await free_of(cook_id, lot.id) == grams("500")


async def test_throwing_away_claimed_stock_gives_the_claim_up_too(
    cook_id: int, flour: int, slot_id: int
) -> None:
    """Waste is a fall in what is there, so it faces the same question as a correction:
    a claim on food that has gone in the bin cannot stand."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("400"))

    await pantry_access.record_waste(lot.id, quantity=grams("450"), reason=WasteReason.SPOILED)

    assert [record.quantity for record in await pantry_access.held_for_slot(slot_id)] == [
        grams("50")
    ]


async def test_a_claimed_lot_cannot_be_taken_back_as_a_mistake(
    cook_id: int, flour: int, slot_id: int
) -> None:
    """A plan is counting on it. Deleting it silently would break the plan without
    telling anybody; refusing sends the cook to the meal that needs replanning."""
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("100"))

    with pytest.raises(ValueError, match="planned meal"):
        await pantry_access.remove(lot.id)

    assert await pantry_access.fetch(lot.id) is not None


async def test_availability_can_be_asked_about_particular_ingredients(
    cook_id: int, butter: int, flour: int, slot_id: int
) -> None:
    """What a shopping list asks: these ingredients, and how much of each is going spare."""
    await pantry_access.receive(cook_id=cook_id, ingredient_id=butter, quantity=grams("250"))
    lot = await pantry_access.receive(cook_id=cook_id, ingredient_id=flour, quantity=grams("500"))
    await pantry_access.reserve_against(lot.id, plan_slot_id=slot_id, quantity=grams("200"))

    spare = await pantry_access.available(cook_id, [flour])

    assert [(one.lot.ingredient_id, one.free) for one in spare] == [(flour, grams("300"))]
