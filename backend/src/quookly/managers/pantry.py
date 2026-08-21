"""The pantry: what is in the kitchen, and what left it without being eaten.

Resource access holds lots. This is where lots become a shelf — grouped by ingredient,
named in the cook's own language, totalled where a total is honest, and marked with how
soon each packet wants using.

Separate from planning because stock is true whether or not anyone is planning: a cook
adjusts the pantry constantly outside any plan, and expiry advances whether or not the
app is opened (V9).
"""

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.contracts.errors import DensityRequired, IncompatibleUnits
from quookly.contracts.events import MealCooked
from quookly.contracts.ingredient import Ingredient
from quookly.contracts.measure import Quantity
from quookly.contracts.pantry import (
    AdjustInput,
    Freshness,
    PantryEntry,
    ReceiveInput,
    StockItem,
    StockLotView,
    WasteInput,
)
from quookly.engines import measure
from quookly.utilities.diagnostics import get_logger

_log = get_logger("pantry")

#: How near a date has to be before a packet is worth pointing at. Three days is roughly
#: a shopping trip away: long enough to plan a meal around it, short enough that the
#: warning is still about this week. Deliberately one number rather than a setting —
#: another dial on the settings screen would cost more attention than it saves.
EXPIRING_SOON_DAYS = 3

#: Worst first. A card takes the urgency of its most pressing lot, so a bag going off is
#: never hidden behind a fresh one bought yesterday.
_URGENCY = {Freshness.PAST: 0, Freshness.SOON: 1, Freshness.FRESH: 2, Freshness.UNDATED: 3}


def _today() -> date:
    """Today, as a value the tests can hold still. Freshness is a claim about now."""
    return date.today()


def _freshness(expires_on: date | None, today: date) -> tuple[Freshness, int | None]:
    if expires_on is None:
        return Freshness.UNDATED, None
    remaining = (expires_on - today).days
    if remaining < 0:
        return Freshness.PAST, remaining
    if remaining <= EXPIRING_SOON_DAYS:
        return Freshness.SOON, remaining
    return Freshness.FRESH, remaining


def _tidy(magnitude: Decimal) -> str:
    """Render a stored magnitude the way it was meant, not the way the column keeps it.

    500.0000 is how a fixed-scale decimal column stores 500. Showing the zeros invites a
    cook to believe the precision means something.
    """
    text = f"{magnitude:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _lot_view(lot: StockItem, today: date) -> StockLotView:
    freshness, remaining = _freshness(lot.expires_on, today)
    # In the unit it arrived in. A packet says one kilo, and rewriting that as 1000 g
    # because this cook prefers grams would make the shelf disagree with the shelf.
    written = Quantity(Decimal(_tidy(lot.quantity.magnitude)), lot.quantity.unit)
    return StockLotView(
        id=lot.id,
        magnitude=_tidy(lot.quantity.magnitude),
        unit=lot.quantity.unit.symbol,
        quantity=str(written),
        expires_on=lot.expires_on,
        days_remaining=remaining,
        freshness=freshness,
        note=lot.note,
    )


def _added_up(amounts: list[Quantity], density: Decimal | None) -> str | None:
    """These quantities as one, or nothing where they do not add up.

    Absent rather than approximated — six eggs and 200 g of egg have no sum. Nothing is
    hidden by declining: every lot is listed underneath.
    """
    if not amounts:
        return None
    target = amounts[0].unit
    running = Decimal(0)
    for amount in amounts:
        try:
            running += measure.convert(amount, target, density).magnitude
        except (IncompatibleUnits, DensityRequired):
            return None
    return str(measure.round_for_display(measure.humanise(Quantity(running, target))))


def _entry(
    entry: Ingredient,
    lots: list[StockItem],
    today: date,
    free: Mapping[int, Quantity],
) -> PantryEntry:
    ordered = sorted(lots, key=lambda lot: (lot.expires_on is None, lot.expires_on, lot.id))
    views = [_lot_view(lot, today) for lot in ordered]
    # Only the lots something has actually claimed. A card where nothing is spoken for
    # says nothing, rather than saying "0 g" — which reads as a fact worth noticing.
    claimed = [
        Quantity(lot.quantity.magnitude - free[lot.id].magnitude, lot.quantity.unit)
        for lot in ordered
        if lot.id in free and lot.quantity.magnitude > free[lot.id].magnitude
    ]
    return PantryEntry(
        ingredient_id=entry.id,
        slug=entry.slug,
        name=entry.name,
        kind=entry.kind,
        total=_added_up([lot.quantity for lot in ordered], entry.density),
        spoken_for=_added_up(claimed, entry.density) if claimed else None,
        freshness=min(
            (view.freshness for view in views), key=lambda f: _URGENCY[f], default=Freshness.UNDATED
        ),
        lots=views,
    )


async def _shelf(cook_id: int, lots: list[StockItem], locale: str | None) -> list[PantryEntry]:
    """Turn a set of lots into entries, named and ordered for reading."""
    if not lots:
        return []
    reading = locale or await cook_access.locale_for(cook_id)
    entries = await registry.for_ids(sorted({lot.ingredient_id for lot in lots}), reading)
    today = _today()
    # What nothing has claimed, so a card can say how much of its total is spoken for.
    free = {one.lot.id: one.free for one in await pantry_access.available(cook_id)}

    grouped: dict[int, list[StockItem]] = {}
    for lot in lots:
        grouped.setdefault(lot.ingredient_id, []).append(lot)

    shelf = [
        _entry(entries[ingredient_id], held, today, free)
        for ingredient_id, held in grouped.items()
        if ingredient_id in entries
    ]
    # Alphabetically, not by urgency. A shelf that reorders itself as things age is a
    # shelf a cook cannot learn the shape of; urgency is carried by `using_soon` and by
    # the mark on each card.
    return sorted(shelf, key=lambda entry: entry.name.casefold())


async def present(cook_id: int, locale: str | None = None) -> list[PantryEntry]:
    """The whole shelf (UC-5.2)."""
    return await _shelf(cook_id, await pantry_access.list_for_cook(cook_id), locale)


async def using_soon(cook_id: int, locale: str | None = None) -> list[PantryEntry]:
    """What wants eating, soonest first (UC-5.2).

    Includes what is already past its date. Past is the most urgent case there is, not a
    case that has stopped mattering — it is the food most likely to be thrown away.
    """
    cutoff = _today() + timedelta(days=EXPIRING_SOON_DAYS)
    pressing = await pantry_access.expiring_before(cook_id, cutoff)
    shelf = await _shelf(cook_id, pressing, locale)
    return sorted(shelf, key=lambda entry: (_URGENCY[entry.freshness], entry.name.casefold()))


async def _entry_for(cook_id: int, ingredient_id: int, locale: str | None) -> PantryEntry | None:
    """One card, rebuilt. What every change returns, so the client is never left
    inferring what a total became."""
    reading = locale or await cook_access.locale_for(cook_id)
    entries = await registry.for_ids([ingredient_id], reading)
    if ingredient_id not in entries:
        return None
    held = await pantry_access.for_ingredients(cook_id, [ingredient_id])
    free = {one.lot.id: one.free for one in await pantry_access.available(cook_id)}
    return _entry(entries[ingredient_id], held, _today(), free)


async def receive(
    submitted: ReceiveInput, cook_id: int, locale: str | None = None
) -> PantryEntry | None:
    """Record stock arriving (UC-5.1). Absent when the ingredient is not in the registry.

    Checked first rather than left to the foreign key, so an unknown ingredient reads as
    "no such thing" and not as a database error. A unit nobody has heard of raises
    `UnknownUnit`, which the client layer turns into a refusal naming the symbol.
    """
    reading = locale or await cook_access.locale_for(cook_id)
    if submitted.ingredient_id not in await registry.for_ids([submitted.ingredient_id], reading):
        return None
    await pantry_access.receive(
        cook_id=cook_id,
        ingredient_id=submitted.ingredient_id,
        quantity=Quantity(submitted.magnitude, measure.unit_for(submitted.unit)),
        expires_on=submitted.expires_on,
        note=submitted.note,
    )
    return await _entry_for(cook_id, submitted.ingredient_id, reading)


async def _owned(stock_item_id: int, cook_id: int) -> StockItem | None:
    """The lot, if it is this cook's. Another cook's reads as absent rather than as
    forbidden, for the same reason another household's eater does."""
    lot = await pantry_access.fetch(stock_item_id)
    return None if lot is None or lot.cook_id != cook_id else lot


async def adjust(
    stock_item_id: int, submitted: AdjustInput, cook_id: int, locale: str | None = None
) -> PantryEntry | None:
    """Say how much is actually there (UC-5.3).

    Restating downward can cost a planned meal its claim on this stock, and access
    reports what it had to let go. Nothing is done with it here on purpose: the place a
    cook should learn that Thursday dinner is short is the plan, where it is derived from
    the reservations and is therefore always right — not a passing message on this screen,
    which would be a second and weaker channel for the same fact.
    """
    lot = await _owned(stock_item_id, cook_id)
    if lot is None:
        return None
    await pantry_access.adjust(stock_item_id, submitted.magnitude)
    return await _entry_for(cook_id, lot.ingredient_id, locale)


async def waste(
    stock_item_id: int, submitted: WasteInput, cook_id: int, locale: str | None = None
) -> PantryEntry | None:
    """Throw some of a lot away, and say why (UC-5.4).

    Separate from `adjust` on purpose. Adjusting says the number was wrong; wasting says
    food left the kitchen. Only one of those is the number this product exists to reduce,
    and a single "the amount changed" verb could never tell them apart.
    """
    lot = await _owned(stock_item_id, cook_id)
    if lot is None:
        return None
    await pantry_access.record_waste(
        stock_item_id,
        quantity=Quantity(submitted.magnitude, lot.quantity.unit),
        reason=submitted.reason,
        note=submitted.note,
    )
    return await _entry_for(cook_id, lot.ingredient_id, locale)


async def discard(stock_item_id: int, cook_id: int) -> bool:
    """Delete a lot entered by mistake. Not the same as wasting it: food that was never
    in the house must not land in the waste the cook is trying to bring down."""
    lot = await _owned(stock_item_id, cook_id)
    if lot is None:
        return False
    return await pantry_access.remove(stock_item_id)


async def on_meal_cooked(fact: MealCooked) -> None:
    """Turn what a meal was holding into stock that has gone (UC-4.5, FR-19).

    Subscribed rather than called. `PlanningManager` states that a meal was cooked and
    does not know that stock accounting exists; this manager owns inventory truth (V9)
    and does not know where the meal came from. That is the Manager-must-not-call-Manager
    rule doing useful work rather than merely being obeyed — and it is what will let a
    cooking session publish the same fact without either of them learning about the other.

    Idempotent by construction: a meal whose claims are already consumed holds none, and
    consuming none consumes nothing. That is what makes it safe for a publisher to
    re-state the fact after a failure part-way through.
    """
    taken = await pantry_access.consume_for_slot(fact.plan_slot_id)
    _log.info(
        "meal %s cooked: %d %s consumed",
        fact.plan_slot_id,
        len(taken),
        "reservation" if len(taken) == 1 else "reservations",
    )
