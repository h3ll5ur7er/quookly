"""What a cook has already put in the basket (V8, UC-4.4).

A tick against a plan and an ingredient, carrying the quantity it was ticked at. Reading
compares the two: a tick for 500 g does not answer a list that now asks for 800 g, and the
line comes back as still to buy rather than as bought. Absence is never zero, and neither
is a stale yes.
"""

from datetime import UTC, datetime

from sqlmodel import col, delete, select

from quookly.access.database import session
from quookly.access.models import ShoppingTickRow
from quookly.contracts.measure import Quantity


async def ticked(plan_id: int) -> dict[int, Quantity]:
    """What has been ticked off this plan's list, by ingredient and at what quantity."""
    async with session() as active:
        rows = (
            await active.exec(
                select(ShoppingTickRow).where(col(ShoppingTickRow.plan_id) == plan_id)
            )
        ).all()
    return {row.ingredient_id: Quantity(magnitude=row.magnitude, unit=row.unit) for row in rows}


async def tick(plan_id: int, ingredient_id: int, quantity: Quantity) -> None:
    """Mark one line bought, at the quantity the list was asking for.

    Replaces any earlier tick rather than adding one, so ticking twice is the same as
    ticking once — a request that arrives again from a phone with poor signal in a shop
    should not become two facts.
    """
    async with session() as active:
        held = (
            await active.exec(
                select(ShoppingTickRow)
                .where(col(ShoppingTickRow.plan_id) == plan_id)
                .where(col(ShoppingTickRow.ingredient_id) == ingredient_id)
            )
        ).first()
        if held is None:
            held = ShoppingTickRow(
                plan_id=plan_id,
                ingredient_id=ingredient_id,
                magnitude=quantity.magnitude,
                unit=quantity.unit,
                ticked_at=datetime.now(UTC),
            )
        else:
            held.magnitude = quantity.magnitude
            held.unit = quantity.unit
            held.ticked_at = datetime.now(UTC)
        active.add(held)
        await active.commit()


async def untick(plan_id: int, ingredient_id: int) -> None:
    """Put one line back on the list. Unticking what was never ticked does nothing."""
    async with session() as active:
        await active.exec(
            delete(ShoppingTickRow)
            .where(col(ShoppingTickRow.plan_id) == plan_id)
            .where(col(ShoppingTickRow.ingredient_id) == ingredient_id)
        )
        await active.commit()


async def clear(plan_id: int) -> None:
    """Forget every tick on this plan. Used when the plan itself goes."""
    async with session() as active:
        await active.exec(delete(ShoppingTickRow).where(col(ShoppingTickRow.plan_id) == plan_id))
        await active.commit()
