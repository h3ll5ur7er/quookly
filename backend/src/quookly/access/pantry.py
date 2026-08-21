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

from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import ReservationRow, StockItemRow, WasteRow
from quookly.contracts.measure import Quantity
from quookly.contracts.pantry import (
    Adjusted,
    Availability,
    Released,
    Reservation,
    StockItem,
    WasteReason,
    WasteRecord,
)

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


def _reservation_to_contract(row: ReservationRow) -> Reservation:
    assert row.id is not None, "a persisted reservation always has an id"
    return Reservation(
        id=row.id,
        stock_item_id=row.stock_item_id,
        plan_slot_id=row.plan_slot_id,
        quantity=Quantity(magnitude=row.magnitude, unit=row.unit),
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


async def _claims_on(active: AsyncSession, stock_item_id: int) -> list[ReservationRow]:
    """Every claim against this lot, newest first — the order they give way in."""
    return list(
        (
            await active.exec(
                select(ReservationRow)
                .where(col(ReservationRow.stock_item_id) == stock_item_id)
                .order_by(col(ReservationRow.id).desc())
            )
        ).all()
    )


async def _keep_claims_honest(active: AsyncSession, row: StockItemRow) -> list[Released]:
    """Let go of any claim on this lot beyond what is really there.

    Called wherever a lot's quantity falls. The fridge is the authority: a cook reporting
    less than a plan claimed is telling the truth about their own kitchen, so the claim
    yields rather than the report. What yielded is returned, so the caller can say which
    meal now needs shopping for — a claim quietly kept would be stock that is neither
    free nor there, which is the invisible-forever failure ADR-004 exists to prevent.

    The newest claim yields first. Something has to, and "last to ask, first to go" is a
    rule a person accepts without needing it explained.
    """
    claims = await _claims_on(active, row.id) if row.id is not None else []
    room = row.magnitude - sum((claim.magnitude for claim in claims), Decimal(0))
    let_go: list[Released] = []
    for claim in claims:
        if room >= SPENT:
            break
        # Cut this claim down rather than dropping it whole: 300 g claimed against 100 g
        # left is a claim on 100 g, and freeing all of it would give away stock the meal
        # is still going to use.
        given = min(claim.magnitude, -room)
        room += given
        let_go.append(
            Released(
                plan_slot_id=claim.plan_slot_id,
                quantity=Quantity(magnitude=given, unit=claim.unit),
            )
        )
        if given == claim.magnitude:
            await active.delete(claim)
        else:
            claim.magnitude -= given
            active.add(claim)
    return let_go


async def adjust(stock_item_id: int, magnitude: Decimal) -> Adjusted | None:
    """Say how much is actually there now (UC-5.3).

    A restatement, not a difference: a cook looking into a jar knows how much is in it,
    and the same statement sent twice by a flaky connection says the same thing twice.

    Reports any claim it had to let go of, because a meal that was counting on stock the
    cook has just said is not there needs shopping for.
    """
    if magnitude < SPENT:
        raise ValueError("a pantry cannot hold a negative amount of anything")
    async with session() as active:
        row = await active.get(StockItemRow, stock_item_id)
        if row is None:
            return None
        row.magnitude = magnitude
        active.add(row)
        released = await _keep_claims_honest(active, row)
        await active.commit()
        await active.refresh(row)
        return Adjusted(lot=_to_contract(row), released=released)


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
        await _keep_claims_honest(active, row)
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
    thrown away from it, because that record would be left pointing at nothing — and
    refused while a planned meal is counting on it, because deleting it silently would
    break the plan without telling anybody.
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
        claimed = (
            await active.exec(
                select(ReservationRow).where(col(ReservationRow.stock_item_id) == stock_item_id)
            )
        ).first()
        if claimed is not None:
            raise ValueError("a planned meal is counting on this stock; release it first")
        await active.delete(row)
        await active.commit()
        return True


# Reservations (ADR-004). A plan holds stock aside, cooking takes it, cancelling gives it
# back. A reservation row exists exactly while the claim is held: there is no status to
# read, and so no way for a stale one to keep stock invisible.


async def reserve_against(
    stock_item_id: int, *, plan_slot_id: int, quantity: Quantity
) -> Reservation | None:
    """Hold some of this lot aside for a planned meal (UC-4.1).

    The lot is not touched. The butter is still in the fridge — which is the whole of
    ADR-004, and the reason a cancelled plan needs nothing re-added.

    Refused when more is asked for than is going spare, so two meals cannot claim the
    same butter and then both find it gone.
    """
    if quantity.magnitude <= SPENT:
        raise ValueError("a claim is for some amount greater than nothing")
    async with session() as active:
        row = await active.get(StockItemRow, stock_item_id)
        if row is None:
            return None
        wanted = _in_the_lots_own_unit(row, quantity)
        claims = await _claims_on(active, stock_item_id)
        free = row.magnitude - sum((claim.magnitude for claim in claims), Decimal(0))
        if wanted > free:
            raise ValueError(f"only {free} {row.unit.symbol} of that is going spare, not {wanted}")
        claim = ReservationRow(
            stock_item_id=stock_item_id,
            plan_slot_id=plan_slot_id,
            magnitude=wanted,
            unit=row.unit,
        )
        active.add(claim)
        await active.commit()
        await active.refresh(claim)
        return _reservation_to_contract(claim)


async def held_for_slot(plan_slot_id: int) -> list[Reservation]:
    """What this meal is holding aside."""
    async with session() as active:
        rows = (
            await active.exec(
                select(ReservationRow)
                .where(col(ReservationRow.plan_slot_id) == plan_slot_id)
                .order_by(col(ReservationRow.id))
            )
        ).all()
        return [_reservation_to_contract(row) for row in rows]


async def release_for_slot(plan_slot_id: int) -> list[Reservation]:
    """Give back everything this meal was holding, and say what it was.

    A first-class path, not an error path. Three ordinary things release: cancelling a
    plan, moving a slot to another recipe, and abandoning a cooking session. The stock is
    simply still there — nothing is re-added, because nothing left. A missed release is
    stock that is invisible forever, which is exactly the waste this product exists to
    reduce.

    Holding nothing is not a failure. Cancelling a plan releases every slot, and most
    slots hold nothing.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(ReservationRow)
                .where(col(ReservationRow.plan_slot_id) == plan_slot_id)
                .order_by(col(ReservationRow.id))
            )
        ).all()
        let_go = [_reservation_to_contract(row) for row in rows]
        if rows:
            await active.exec(
                delete(ReservationRow).where(col(ReservationRow.plan_slot_id) == plan_slot_id)
            )
            await active.commit()
        return let_go


async def consume_for_slot(plan_slot_id: int) -> list[Reservation]:
    """Take what this meal was holding, because it has been cooked (UC-4.5, FR-19).

    The claims become a fall in stock and then stop existing. Both halves in one
    transaction: a lot decremented without its claim cleared would be counted twice, and
    a claim cleared without the decrement is food the pantry still thinks it has.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(ReservationRow)
                .where(col(ReservationRow.plan_slot_id) == plan_slot_id)
                .order_by(col(ReservationRow.id))
            )
        ).all()
        if not rows:
            return []
        taken = [_reservation_to_contract(row) for row in rows]
        for claim in rows:
            lot = await active.get(StockItemRow, claim.stock_item_id)
            if lot is not None:
                lot.magnitude -= claim.magnitude
                active.add(lot)
            await active.delete(claim)
        await active.commit()
        return taken


async def available(cook_id: int, ingredient_ids: list[int] | None = None) -> list[Availability]:
    """What this cook has, and how much of each lot nothing has claimed.

    `free` is computed from the claims rather than stored beside the quantity. A
    `reserved` column would be a second source of truth about the same butter, and the
    two would disagree the first time anything went wrong halfway through.

    A fully claimed lot still appears, with nothing free. It is there, only spoken for,
    and hiding it would read as "you have no flour" to somebody standing in front of it.
    """
    async with session() as active:
        statement = select(StockItemRow).where(
            col(StockItemRow.cook_id) == cook_id,
            col(StockItemRow.magnitude) > SPENT,
        )
        if ingredient_ids is not None:
            if not ingredient_ids:
                return []
            statement = statement.where(col(StockItemRow.ingredient_id).in_(ingredient_ids))
        rows = (await active.exec(statement.order_by(col(StockItemRow.id)))).all()
        lot_ids = [row.id for row in rows if row.id is not None]
        if not lot_ids:
            return []
        claims = (
            await active.exec(
                select(ReservationRow).where(col(ReservationRow.stock_item_id).in_(lot_ids))
            )
        ).all()
        spoken_for: dict[int, Decimal] = {}
        for claim in claims:
            spoken_for[claim.stock_item_id] = (
                spoken_for.get(claim.stock_item_id, Decimal(0)) + claim.magnitude
            )
        return [
            Availability(
                lot=_to_contract(row),
                free=Quantity(
                    magnitude=row.magnitude - spoken_for.get(row.id or 0, Decimal(0)),
                    unit=row.unit,
                ),
            )
            for row in rows
            if row.id is not None
        ]
