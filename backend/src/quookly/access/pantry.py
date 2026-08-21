"""Access to what is in the kitchen, in domain verbs.

Stock is held as lots. A lot is some of an ingredient that arrived at one time with one
date on it, and it stays a lot rather than being folded into a per-ingredient total,
because expiry belongs to a packet and a warning about "flour" helps nobody find the bag
that is about to go off.

Nothing here converts between units. Conversion is `MeasureEngine`, which sits above the
access layer, so a quantity arriving in a unit other than the lot's own is refused rather
than guessed at — reading 300 kg as 300 g would empty a pantry silently.
"""

from datetime import date
from decimal import Decimal

from sqlmodel import col, select

from quookly.access.database import session
from quookly.access.models import StockItemRow, WasteRow
from quookly.contracts.measure import Quantity
from quookly.contracts.pantry import StockItem, WasteReason, WasteRecord

#: A lot at zero is spent. Its row stays — waste records point at it — but it is off the
#: shelf, out of the expiry warnings, and out of everything that asks what is available.
SPENT = Decimal("0")


def _to_contract(row: StockItemRow) -> StockItem:
    assert row.id is not None, "a persisted lot always has an id"
    return StockItem(
        id=row.id,
        cook_id=row.cook_id,
        ingredient_id=row.ingredient_id,
        quantity=Quantity(magnitude=row.magnitude, unit=row.unit),
        expires_on=row.expires_on,
        note=row.note,
        received_at=row.received_at,
    )


def _waste_to_contract(row: WasteRow) -> WasteRecord:
    assert row.id is not None, "a persisted waste record always has an id"
    return WasteRecord(
        id=row.id,
        cook_id=row.cook_id,
        ingredient_id=row.ingredient_id,
        quantity=Quantity(magnitude=row.magnitude, unit=row.unit),
        reason=row.reason,
        note=row.note,
        recorded_at=row.recorded_at,
    )


def _in_the_lots_own_unit(row: StockItemRow, quantity: Quantity) -> Decimal:
    if quantity.unit is not row.unit:
        raise ValueError(
            f"this lot is held in {row.unit.symbol}, not {quantity.unit.symbol}; "
            "convert before recording against it"
        )
    return quantity.magnitude


async def receive(
    *,
    cook_id: int,
    ingredient_id: int,
    quantity: Quantity,
    expires_on: date | None = None,
    note: str | None = None,
) -> StockItem:
    """Record stock arriving (UC-5.1).

    Always a new lot, never added to an existing one. Two identical bags bought a week
    apart are two bags, and merging them would give the older one the younger one's date.
    """
    if quantity.magnitude <= SPENT:
        raise ValueError("stock arrives in some amount greater than nothing")
    row = StockItemRow(
        cook_id=cook_id,
        ingredient_id=ingredient_id,
        magnitude=quantity.magnitude,
        unit=quantity.unit,
        expires_on=expires_on,
        note=note,
    )
    async with session() as active:
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return _to_contract(row)


async def fetch(stock_item_id: int) -> StockItem | None:
    """One lot, spent or not. Spent lots are still fetchable: something points at them."""
    async with session() as active:
        row = await active.get(StockItemRow, stock_item_id)
        return None if row is None else _to_contract(row)


async def list_for_cook(cook_id: int) -> list[StockItem]:
    """Everything this cook actually has, oldest arrival first.

    Arrival order rather than expiry order, because this is the shelf as it stands and
    the caller decides how to sort it. `expiring_before` is the one that ranks by urgency.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(StockItemRow)
                .where(
                    col(StockItemRow.cook_id) == cook_id,
                    col(StockItemRow.magnitude) > SPENT,
                )
                .order_by(col(StockItemRow.id))
            )
        ).all()
        return [_to_contract(row) for row in rows]


async def for_ingredients(cook_id: int, ingredient_ids: list[int]) -> list[StockItem]:
    """What this cook has of these particular ingredients.

    For the shopping list and the pantry-coverage question, which ask about a recipe's
    ingredients rather than about the whole shelf.
    """
    if not ingredient_ids:
        return []
    async with session() as active:
        rows = (
            await active.exec(
                select(StockItemRow)
                .where(
                    col(StockItemRow.cook_id) == cook_id,
                    col(StockItemRow.magnitude) > SPENT,
                    col(StockItemRow.ingredient_id).in_(ingredient_ids),
                )
                .order_by(col(StockItemRow.id))
            )
        ).all()
        return [_to_contract(row) for row in rows]


async def expiring_before(cook_id: int, cutoff: date) -> list[StockItem]:
    """Dated stock due on or before `cutoff`, soonest first (UC-5.2).

    Undated stock never appears. "Expires: unknown" is not "expires soon", and a warning
    list padded with things that cannot go off is a warning list nobody reads.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(StockItemRow)
                .where(
                    col(StockItemRow.cook_id) == cook_id,
                    col(StockItemRow.magnitude) > SPENT,
                    col(StockItemRow.expires_on).is_not(None),
                    col(StockItemRow.expires_on) <= cutoff,
                )
                .order_by(col(StockItemRow.expires_on), col(StockItemRow.id))
            )
        ).all()
        return [_to_contract(row) for row in rows]


async def adjust(stock_item_id: int, magnitude: Decimal) -> StockItem | None:
    """Say how much is actually there now (UC-5.3).

    A restatement, not a difference: a cook looking into a jar knows how much is in it,
    and the same statement sent twice by a flaky connection says the same thing twice.
    """
    if magnitude < SPENT:
        raise ValueError("a pantry cannot hold a negative amount of anything")
    async with session() as active:
        row = await active.get(StockItemRow, stock_item_id)
        if row is None:
            return None
        row.magnitude = magnitude
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return _to_contract(row)


async def record_waste(
    stock_item_id: int,
    *,
    quantity: Quantity,
    reason: WasteReason,
    note: str | None = None,
) -> WasteRecord | None:
    """Take some of a lot out of the kitchen, and say why (UC-5.4).

    Both halves in one transaction. Stock going down without a record is indistinguishable
    from food that was eaten, and that difference is most of the point of asking.
    """
    if quantity.magnitude <= SPENT:
        raise ValueError("waste is some amount greater than nothing")
    async with session() as active:
        row = await active.get(StockItemRow, stock_item_id)
        if row is None:
            return None
        amount = _in_the_lots_own_unit(row, quantity)
        if amount > row.magnitude:
            raise ValueError(
                f"cannot throw away more than is there: {amount} of {row.magnitude} "
                f"{row.unit.symbol}"
            )
        row.magnitude -= amount
        record = WasteRow(
            cook_id=row.cook_id,
            ingredient_id=row.ingredient_id,
            stock_item_id=row.id,
            magnitude=amount,
            unit=row.unit,
            reason=reason,
            note=note,
        )
        active.add(row)
        active.add(record)
        await active.commit()
        await active.refresh(record)
        return _waste_to_contract(record)


async def waste_for_cook(cook_id: int, since: date | None = None) -> list[WasteRecord]:
    """What this cook has thrown away, most recent first."""
    async with session() as active:
        statement = select(WasteRow).where(col(WasteRow.cook_id) == cook_id)
        if since is not None:
            statement = statement.where(col(WasteRow.recorded_at) >= since)
        rows = (await active.exec(statement.order_by(col(WasteRow.id).desc()))).all()
        return [_waste_to_contract(row) for row in rows]


async def remove(stock_item_id: int) -> bool:
    """Delete a lot outright — it was entered by mistake and never existed.

    Not the same as wasting it. A mistyped entry that never came into the house must not
    land in the number the cook is trying to bring down. Refused once anything has been
    thrown away from it, because that record would be left pointing at nothing.
    """
    async with session() as active:
        row = await active.get(StockItemRow, stock_item_id)
        if row is None:
            return False
        thrown = (
            await active.exec(select(WasteRow).where(col(WasteRow.stock_item_id) == stock_item_id))
        ).first()
        if thrown is not None:
            raise ValueError("this lot has waste recorded against it; adjust it to zero instead")
        await active.delete(row)
        await active.commit()
        return True
