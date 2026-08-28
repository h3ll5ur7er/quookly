"""Access to plans and their slots, in domain verbs.

A plan is a period; a slot is one meal on one day inside it. A slot may exist without a
recipe and without a guest list, because that is what most of a week looks like while it
is being planned, and a model that refuses the half-planned state refuses the way anybody
actually plans.

Reservations belong to the pantry, not here. What this layer does about them is refuse to
delete a slot that still holds any — see `close_slot`.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import (
    CookingSessionRow,
    CookingTimerRow,
    MealPlanRow,
    PlanSlotRow,
    ReservationRow,
    SlotAttendeeRow,
)
from quookly.contracts.plan import Meal, MealPlan, PlanSlot


def _slot_to_contract(row: PlanSlotRow, attendee_ids: list[int]) -> PlanSlot:
    assert row.id is not None, "a persisted slot always has an id"
    return PlanSlot(
        id=row.id,
        plan_id=row.plan_id,
        on_date=row.on_date,
        meal=row.meal,
        recipe_id=row.recipe_id,
        attendee_ids=attendee_ids,
        servings=row.servings,
        cooked_at=row.cooked_at,
    )


async def _attendance_for(active: AsyncSession, slot_ids: Sequence[int]) -> dict[int, list[int]]:
    """Who is at each of these meals, in one query rather than one per slot."""
    seated: dict[int, list[int]] = {slot_id: [] for slot_id in slot_ids}
    if not slot_ids:
        return seated
    rows = (
        await active.exec(
            select(SlotAttendeeRow)
            .where(col(SlotAttendeeRow.slot_id).in_(slot_ids))
            .order_by(col(SlotAttendeeRow.id))
        )
    ).all()
    for row in rows:
        seated[row.slot_id].append(row.eater_id)
    return seated


async def _slots_of(active: AsyncSession, plan_id: int) -> list[PlanSlot]:
    """The plan's slots, in the order the week runs."""
    rows = (
        await active.exec(
            select(PlanSlotRow)
            .where(col(PlanSlotRow.plan_id) == plan_id)
            .order_by(col(PlanSlotRow.on_date), col(PlanSlotRow.meal), col(PlanSlotRow.id))
        )
    ).all()
    seated = await _attendance_for(active, [row.id for row in rows if row.id is not None])
    return [_slot_to_contract(row, seated[row.id]) for row in rows if row.id is not None]


async def _to_contract(active: AsyncSession, row: MealPlanRow) -> MealPlan:
    assert row.id is not None, "a persisted plan always has an id"
    return MealPlan(
        id=row.id,
        cook_id=row.cook_id,
        starts_on=row.starts_on,
        ends_on=row.ends_on,
        slots=await _slots_of(active, row.id),
    )


async def create(*, cook_id: int, starts_on: date, ends_on: date) -> MealPlan:
    """Open a period to plan (UC-4.1). Both dates inclusive."""
    if ends_on < starts_on:
        raise ValueError("a plan does not end before it begins")
    row = MealPlanRow(cook_id=cook_id, starts_on=starts_on, ends_on=ends_on)
    async with session() as active:
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return await _to_contract(active, row)


async def fetch(plan_id: int) -> MealPlan | None:
    """One plan whole, slots and guest lists included."""
    async with session() as active:
        row = await active.get(MealPlanRow, plan_id)
        return None if row is None else await _to_contract(active, row)


async def list_for_cook(cook_id: int) -> list[MealPlan]:
    """This cook's plans, most recent period first."""
    async with session() as active:
        rows = (
            await active.exec(
                select(MealPlanRow)
                .where(col(MealPlanRow.cook_id) == cook_id)
                .order_by(col(MealPlanRow.starts_on).desc(), col(MealPlanRow.id).desc())
            )
        ).all()
        return [await _to_contract(active, row) for row in rows]


async def fetch_slot(slot_id: int) -> PlanSlot | None:
    async with session() as active:
        row = await active.get(PlanSlotRow, slot_id)
        if row is None:
            return None
        seated = await _attendance_for(active, [slot_id])
        return _slot_to_contract(row, seated[slot_id])


async def open_slot(plan_id: int, *, on_date: date, meal: Meal) -> PlanSlot:
    """The slot for this meal on this day, making it if it is not there yet.

    Returning the existing one rather than refusing: a cook tapping Monday dinner twice
    has not asked for two Monday dinners, and an error there would be a bug report about
    the interface rather than about them.
    """
    async with session() as active:
        existing = (
            await active.exec(
                select(PlanSlotRow).where(
                    col(PlanSlotRow.plan_id) == plan_id,
                    col(PlanSlotRow.on_date) == on_date,
                    col(PlanSlotRow.meal) == meal,
                )
            )
        ).first()
        if existing is not None:
            assert existing.id is not None
            seated = await _attendance_for(active, [existing.id])
            return _slot_to_contract(existing, seated[existing.id])

        row = PlanSlotRow(plan_id=plan_id, on_date=on_date, meal=meal)
        active.add(row)
        try:
            await active.commit()
        except IntegrityError as exc:
            raise ValueError(f"no plan with id {plan_id}") from exc
        await active.refresh(row)
        return _slot_to_contract(row, [])


async def assign(slot_id: int, recipe_id: int | None) -> PlanSlot | None:
    """Put a recipe in a slot, or take the one that is there back out (UC-4.1).

    Taking one out is not deleting the slot. "Thursday dinner, undecided again" is a
    state a cook returns to, and losing the guest list with the recipe would mean
    re-entering it every time they changed their mind.
    """
    async with session() as active:
        row = await active.get(PlanSlotRow, slot_id)
        if row is None:
            return None
        row.recipe_id = recipe_id
        active.add(row)
        await active.commit()
        await active.refresh(row)
        seated = await _attendance_for(active, [slot_id])
        return _slot_to_contract(row, seated[slot_id])


async def size(slot_id: int, servings: Decimal | None) -> PlanSlot | None:
    """Say how much of the recipe this meal makes, or stop saying (UC-9.1b).

    Separate from `assign` because it survives a change of recipe being the wrong
    behaviour: "eight" means eight of *that* recipe, and carrying it onto another one
    would silently resize a dish nobody sized.
    """
    async with session() as active:
        row = await active.get(PlanSlotRow, slot_id)
        if row is None:
            return None
        row.servings = servings
        active.add(row)
        await active.commit()
        await active.refresh(row)
        seated = await _attendance_for(active, [slot_id])
        return _slot_to_contract(row, seated[slot_id])


async def attend(slot_id: int, eater_ids: Sequence[int]) -> PlanSlot | None:
    """Say who is at this meal — exactly these people (UC-4.2).

    Wholesale, because the interface edits the whole guest list. Merging would leave
    somebody seated at a meal the cook took them off, and their constraints would go on
    being checked against it — a verdict about a table that nobody is sitting at.
    """
    async with session() as active:
        row = await active.get(PlanSlotRow, slot_id)
        if row is None:
            return None
        await active.exec(delete(SlotAttendeeRow).where(col(SlotAttendeeRow.slot_id) == slot_id))
        kept: list[int] = []
        for eater_id in eater_ids:
            if eater_id not in kept:
                kept.append(eater_id)
                active.add(SlotAttendeeRow(slot_id=slot_id, eater_id=eater_id))
        await active.commit()
        return _slot_to_contract(row, kept)


async def mark_cooked(slot_id: int) -> PlanSlot | None:
    """Record that this meal was cooked (UC-4.5).

    One way, and idempotent: a slot already cooked keeps the instant it was first marked.
    Un-marking would mean re-adding stock that never came back, which is the path ADR-004
    was written to avoid — a mistake is corrected in the pantry, where quantities are
    restated anyway.
    """
    async with session() as active:
        row = await active.get(PlanSlotRow, slot_id)
        if row is None:
            return None
        if row.cooked_at is None:
            row.cooked_at = datetime.now(UTC)
            active.add(row)
            await active.commit()
            await active.refresh(row)
        seated = await _attendance_for(active, [slot_id])
        return _slot_to_contract(row, seated[slot_id])


async def _forget_sessions_for(active: AsyncSession, slot_ids: Sequence[int]) -> None:
    """Take the cooking sessions held against these slots, and their timers.

    Sessions cascade where reservations refuse, and the difference is what each one is a
    claim on. A reservation holds real stock, which lives outside the plan and is the
    cook's to release; a session is only the transcript of cooking one of these slots, and
    whether the meal was cooked at all is recorded on the slot itself — which is going
    either way. Timers first: they hang off the session, so the same constraint refuses
    one level further down otherwise.
    """
    if not slot_ids:
        return
    sessions = (
        await active.exec(
            select(CookingSessionRow).where(col(CookingSessionRow.plan_slot_id).in_(slot_ids))
        )
    ).all()
    session_ids = [one.id for one in sessions if one.id is not None]
    if not session_ids:
        return
    await active.exec(
        delete(CookingTimerRow).where(col(CookingTimerRow.session_id).in_(session_ids))
    )
    await active.exec(delete(CookingSessionRow).where(col(CookingSessionRow.id).in_(session_ids)))


async def close_slot(slot_id: int) -> bool:
    """Take a meal off the plan entirely, guest list and all.

    Refused while the slot still holds stock aside. Releasing is the caller's to do, and
    making the order an error rather than a cascade is what makes it impossible to get
    wrong: a reservation left pointing at nothing is stock that is neither free nor gone,
    which is the invisible-forever failure ADR-004 exists to prevent.
    """
    async with session() as active:
        row = await active.get(PlanSlotRow, slot_id)
        if row is None:
            return False
        held = (
            await active.exec(
                select(ReservationRow).where(col(ReservationRow.plan_slot_id) == slot_id)
            )
        ).first()
        if held is not None:
            raise ValueError("this meal is holding stock aside; release it first")
        await active.exec(delete(SlotAttendeeRow).where(col(SlotAttendeeRow.slot_id) == slot_id))
        await _forget_sessions_for(active, [slot_id])
        await active.delete(row)
        await active.commit()
        return True


async def remove(plan_id: int) -> bool:
    """Forget a whole plan, its slots and their guest lists with it.

    Refused, slot by slot, while any of them still holds stock: the same rule as
    `close_slot`, for the same reason.
    """
    async with session() as active:
        row = await active.get(MealPlanRow, plan_id)
        if row is None:
            return False
        slots = (
            await active.exec(select(PlanSlotRow).where(col(PlanSlotRow.plan_id) == plan_id))
        ).all()
        slot_ids = [slot.id for slot in slots if slot.id is not None]
        if slot_ids:
            held = (
                await active.exec(
                    select(ReservationRow).where(col(ReservationRow.plan_slot_id).in_(slot_ids))
                )
            ).first()
            if held is not None:
                raise ValueError("a meal in this plan is holding stock aside; release it first")
            await active.exec(
                delete(SlotAttendeeRow).where(col(SlotAttendeeRow.slot_id).in_(slot_ids))
            )
            await _forget_sessions_for(active, slot_ids)
            await active.exec(delete(PlanSlotRow).where(col(PlanSlotRow.plan_id) == plan_id))
        await active.delete(row)
        await active.commit()
        return True
