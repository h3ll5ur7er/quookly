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
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.pantry import WasteReason
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
