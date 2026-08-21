"""The pantry as a cook reads it (UC-5.1 to UC-5.4).

Access holds lots. This is where lots become a shelf: grouped by ingredient, named in the
cook's own language, totalled where a total is honest, and marked with how soon each
packet wants using.

Most of what is tested here is the arithmetic of not lying — a total that quietly adds
grams to pieces, or a warning about a packet that is already empty, are both worse than
showing nothing.
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
from quookly.contracts.pantry import (
    AdjustInput,
    Freshness,
    ReceiveInput,
    WasteInput,
    WasteReason,
)
from quookly.contracts.plan import Meal
from quookly.managers import pantry as pantry_manager
from quookly.utilities.configuration import get_settings

TODAY = date(2026, 8, 21)


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


@pytest.fixture(autouse=True)
def a_fixed_today(monkeypatch: MonkeyPatch) -> None:
    """Freshness is a statement about now, so the tests need a now that does not move."""
    monkeypatch.setattr(pantry_manager, "_today", lambda: TODAY)


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
        names={"en-GB": ["plain flour"], "de-CH": ["Mehl"]},
    )
    return entry.id


@pytest.fixture
async def egg() -> int:
    entry = await registry.register(
        slug="egg",
        kind=IngredientKind.COUNTABLE,
        density=None,
        names={"en-GB": ["egg"]},
    )
    return entry.id


async def stock(
    cook_id: int, ingredient_id: int, magnitude: str, unit: Unit, expires_on: date | None = None
) -> int:
    lot = await pantry_access.receive(
        cook_id=cook_id,
        ingredient_id=ingredient_id,
        quantity=Quantity(magnitude=Decimal(magnitude), unit=unit),
        expires_on=expires_on,
    )
    return lot.id


async def test_lots_of_one_ingredient_become_one_entry(cook_id: int, flour: int) -> None:
    await stock(cook_id, flour, "500", Unit.GRAM)
    await stock(cook_id, flour, "1", Unit.KILOGRAM)

    shelf = await pantry_manager.present(cook_id)

    assert len(shelf) == 1
    assert shelf[0].name == "plain flour"
    assert len(shelf[0].lots) == 2


async def test_a_total_converts_and_reads_the_way_it_is_written(cook_id: int, flour: int) -> None:
    """500 g and a kilo is a kilo and a half, not 1500 g and not two numbers."""
    await stock(cook_id, flour, "500", Unit.GRAM)
    await stock(cook_id, flour, "1", Unit.KILOGRAM)

    shelf = await pantry_manager.present(cook_id)

    assert shelf[0].total == "1.5 kg"


async def test_a_total_is_absent_rather_than_invented(cook_id: int, egg: int) -> None:
    """Six eggs and 200 g of egg have no sum. Nothing is hidden by declining to add
    them: both lots are listed underneath."""
    await stock(cook_id, egg, "6", Unit.PIECE)
    await stock(cook_id, egg, "200", Unit.GRAM)

    shelf = await pantry_manager.present(cook_id)

    assert shelf[0].total is None
    assert len(shelf[0].lots) == 2


async def test_a_lot_is_shown_in_the_unit_it_arrived_in(cook_id: int, flour: int) -> None:
    """The packet says one kilo. Rewriting it as 1000 g because this cook prefers grams
    would make the shelf disagree with the shelf."""
    await stock(cook_id, flour, "1", Unit.KILOGRAM)

    shelf = await pantry_manager.present(cook_id)

    assert shelf[0].lots[0].quantity == "1 kg"
    assert shelf[0].lots[0].unit == "kg"


@pytest.mark.parametrize(
    ("expires_on", "expected", "days"),
    [
        (None, Freshness.UNDATED, None),
        (date(2026, 8, 19), Freshness.PAST, -2),
        (date(2026, 8, 21), Freshness.SOON, 0),
        (date(2026, 8, 24), Freshness.SOON, 3),
        (date(2026, 8, 25), Freshness.FRESH, 4),
    ],
)
async def test_how_soon_a_lot_wants_using(
    cook_id: int, flour: int, expires_on: date | None, expected: Freshness, days: int | None
) -> None:
    await stock(cook_id, flour, "500", Unit.GRAM, expires_on)

    shelf = await pantry_manager.present(cook_id)

    assert shelf[0].lots[0].freshness is expected
    assert shelf[0].lots[0].days_remaining == days


async def test_an_entry_takes_the_urgency_of_its_worst_lot(cook_id: int, flour: int) -> None:
    """A card marked by its healthiest packet is a card that hides the one going off."""
    await stock(cook_id, flour, "500", Unit.GRAM, date(2026, 12, 1))
    await stock(cook_id, flour, "500", Unit.GRAM, date(2026, 8, 19))

    shelf = await pantry_manager.present(cook_id)

    assert shelf[0].freshness is Freshness.PAST


async def test_lots_within_an_entry_lead_with_the_one_to_use_first(
    cook_id: int, flour: int
) -> None:
    await stock(cook_id, flour, "500", Unit.GRAM, None)
    await stock(cook_id, flour, "500", Unit.GRAM, date(2026, 12, 1))
    await stock(cook_id, flour, "500", Unit.GRAM, date(2026, 8, 19))

    shelf = await pantry_manager.present(cook_id)

    assert [lot.expires_on for lot in shelf[0].lots] == [
        date(2026, 8, 19),
        date(2026, 12, 1),
        None,
    ]


async def test_the_shelf_is_read_in_the_cooks_language(cook_id: int, flour: int) -> None:
    await cook_access.choose_locale(cook_id, "de-CH")
    await stock(cook_id, flour, "500", Unit.GRAM)

    shelf = await pantry_manager.present(cook_id)

    assert shelf[0].name == "Mehl"


async def test_receiving_returns_the_whole_entry(cook_id: int, flour: int) -> None:
    """So the card the cook is looking at updates as a whole, rather than the client
    guessing what the new total became."""
    await stock(cook_id, flour, "500", Unit.GRAM)

    entry = await pantry_manager.receive(
        ReceiveInput(ingredient_id=flour, magnitude=Decimal("500"), unit="g"), cook_id
    )

    assert entry is not None
    assert entry.total == "1 kg"


async def test_stock_of_an_ingredient_nobody_has_heard_of_is_refused(cook_id: int) -> None:
    assert (
        await pantry_manager.receive(
            ReceiveInput(ingredient_id=9999, magnitude=Decimal("1"), unit="g"), cook_id
        )
        is None
    )


async def test_another_cooks_lot_cannot_be_touched(
    cook_id: int, other_cook_id: int, flour: int
) -> None:
    theirs = await stock(other_cook_id, flour, "500", Unit.GRAM)

    assert await pantry_manager.adjust(theirs, AdjustInput(magnitude=Decimal("1")), cook_id) is None
    assert (
        await pantry_manager.waste(
            theirs, WasteInput(magnitude=Decimal("1"), reason=WasteReason.SPOILED), cook_id
        )
        is None
    )
    assert await pantry_manager.discard(theirs, cook_id) is False

    still_theirs = await pantry_access.fetch(theirs)
    assert still_theirs is not None
    assert still_theirs.quantity.magnitude == Decimal("500")


async def test_wasting_the_last_of_something_leaves_the_shelf_empty(
    cook_id: int, flour: int
) -> None:
    lot = await stock(cook_id, flour, "500", Unit.GRAM)

    entry = await pantry_manager.waste(
        lot, WasteInput(magnitude=Decimal("500"), reason=WasteReason.SPOILED), cook_id
    )

    assert entry is not None
    assert entry.lots == []
    assert entry.total is None
    assert await pantry_manager.present(cook_id) == []


async def test_using_soon_names_only_what_is_actually_pressing(
    cook_id: int, flour: int, egg: int
) -> None:
    await stock(cook_id, flour, "500", Unit.GRAM, date(2026, 8, 22))
    await stock(cook_id, flour, "500", Unit.GRAM, date(2026, 12, 1))
    await stock(cook_id, egg, "6", Unit.PIECE)

    pressing = await pantry_manager.using_soon(cook_id)

    assert [entry.slug for entry in pressing] == ["plain-flour"]
    assert [lot.expires_on for lot in pressing[0].lots] == [date(2026, 8, 22)]


async def test_using_soon_includes_what_is_already_past(cook_id: int, flour: int) -> None:
    """Past its date is the most urgent case there is, not a case that has stopped
    mattering."""
    await stock(cook_id, flour, "500", Unit.GRAM, date(2026, 8, 1))

    pressing = await pantry_manager.using_soon(cook_id)

    assert pressing[0].freshness is Freshness.PAST


class TestWhatAPlanHasClaimed:
    """The total stays what is in the cupboard — planning reserves rather than deducts
    (ADR-004). But "how much can I use today" is a different question from "how much is
    there", and a cook who cooks the lot because the screen said 800 g leaves Thursday
    short with nothing having warned them."""

    async def test_a_card_says_how_much_is_spoken_for(self, cook_id: int, flour: int) -> None:
        lot = await stock(cook_id, flour, "500", Unit.GRAM)
        plan = await plan_access.create(cook_id=cook_id, starts_on=TODAY, ends_on=date(2026, 8, 30))
        slot = await plan_access.open_slot(plan.id, on_date=TODAY, meal=Meal.DINNER)
        await pantry_access.reserve_against(
            lot, plan_slot_id=slot.id, quantity=Quantity(Decimal("200"), Unit.GRAM)
        )

        shelf = await pantry_manager.present(cook_id)

        assert shelf[0].total == "500 g"
        assert shelf[0].spoken_for == "200 g"

    async def test_a_card_nothing_has_claimed_says_nothing(self, cook_id: int, flour: int) -> None:
        """Rather than "0 g", which reads as a fact worth noticing."""
        await stock(cook_id, flour, "500", Unit.GRAM)

        shelf = await pantry_manager.present(cook_id)

        assert shelf[0].spoken_for is None
