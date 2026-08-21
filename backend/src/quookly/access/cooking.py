"""Access to cooking sessions and their timers, in domain verbs.

A session is progress: where the cook is, and what each timer has counted. Callers deal in
sessions; rows stay here.

Nothing in this module decides what a timer's next state *is* — that arithmetic is
`ExecutionEngine`'s, where it can be exhausted as a table of cases (ADR-013). This writes
down what it is told.
"""

from datetime import UTC, datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import CookingSessionRow, CookingTimerRow
from quookly.contracts.cooking import CookingSession, SessionOutcome, Timer


def _now() -> datetime:
    return datetime.now(UTC)


def _timer(row: CookingTimerRow) -> Timer:
    return Timer(
        step_position=row.step_position,
        # SQLite hands back a naive datetime. Left naive it would subtract against an
        # aware "now" and raise — and a timer that raises on the second tick is worse
        # than one that is a second out.
        running_since=None if row.running_since is None else row.running_since.replace(tzinfo=UTC),
        elapsed_seconds=row.elapsed_seconds,
    )


async def _timers_for(active: AsyncSession, session_id: int) -> list[Timer]:
    rows = (
        await active.exec(
            select(CookingTimerRow)
            .where(col(CookingTimerRow.session_id) == session_id)
            .order_by(col(CookingTimerRow.step_position))
        )
    ).all()
    return [_timer(row) for row in rows]


async def _to_contract(active: AsyncSession, row: CookingSessionRow) -> CookingSession:
    assert row.id is not None
    return CookingSession(
        id=row.id,
        cook_id=row.cook_id,
        plan_slot_id=row.plan_slot_id,
        started_at=row.started_at.replace(tzinfo=UTC),
        at_step=row.at_step,
        finished_at=None if row.finished_at is None else row.finished_at.replace(tzinfo=UTC),
        outcome=row.outcome,
        timers=await _timers_for(active, row.id),
    )


async def open_session(cook_id: int, plan_slot_id: int) -> CookingSession:
    """Start cooking a planned meal (UC-9.1).

    Begins on the mise-en-place: `at_step` is absent, because getting things ready is
    where cooking starts and not a state to be skipped past.
    """
    row = CookingSessionRow(cook_id=cook_id, plan_slot_id=plan_slot_id)
    async with session() as active:
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return await _to_contract(active, row)


async def fetch(session_id: int) -> CookingSession | None:
    async with session() as active:
        row = await active.get(CookingSessionRow, session_id)
        return None if row is None else await _to_contract(active, row)


async def open_for_slot(plan_slot_id: int) -> CookingSession | None:
    """The session still running for this meal, if there is one.

    What makes starting a session idempotent: asking to cook a meal that is already being
    cooked is a cook coming back to it, not a second dinner (UC-9.7).
    """
    async with session() as active:
        row = (
            await active.exec(
                select(CookingSessionRow)
                .where(col(CookingSessionRow.plan_slot_id) == plan_slot_id)
                .where(col(CookingSessionRow.outcome).is_(None))
                .order_by(col(CookingSessionRow.id).desc())
            )
        ).first()
        return None if row is None else await _to_contract(active, row)


async def open_for_cook(cook_id: int) -> list[CookingSession]:
    """Everything this cook has on the go, most recent first (UC-9.7).

    A list rather than one, because a kitchen has the oven on while something else
    simmers, and a store that could only hold one would have to choose between them.
    """
    async with session() as active:
        rows = (
            await active.exec(
                select(CookingSessionRow)
                .where(col(CookingSessionRow.cook_id) == cook_id)
                .where(col(CookingSessionRow.outcome).is_(None))
                .order_by(
                    col(CookingSessionRow.started_at).desc(), col(CookingSessionRow.id).desc()
                )
            )
        ).all()
        return [await _to_contract(active, row) for row in rows]


async def advance_step(session_id: int, position: int | None) -> CookingSession | None:
    """Move the cook to a step, or back to the mise-en-place (UC-9.3).

    Set rather than incremented. A cook goes back to re-read the step before, and a store
    that only knew "next" could not carry them there.
    """
    async with session() as active:
        row = await active.get(CookingSessionRow, session_id)
        if row is None:
            return None
        row.at_step = position
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return await _to_contract(active, row)


async def record_timer(session_id: int, timer: Timer) -> CookingSession | None:
    """Write down a timer's state, creating it if this is its first mention."""
    async with session() as active:
        held = await active.get(CookingSessionRow, session_id)
        if held is None:
            return None
        row = (
            await active.exec(
                select(CookingTimerRow)
                .where(col(CookingTimerRow.session_id) == session_id)
                .where(col(CookingTimerRow.step_position) == timer.step_position)
            )
        ).first()
        if row is None:
            row = CookingTimerRow(session_id=session_id, step_position=timer.step_position)
        row.running_since = timer.running_since
        row.elapsed_seconds = timer.elapsed_seconds
        active.add(row)
        await active.commit()
        return await _to_contract(active, held)


async def timer_for(session_id: int, step_position: int) -> Timer | None:
    """One step's timer, if it has ever been started."""
    async with session() as active:
        row = (
            await active.exec(
                select(CookingTimerRow)
                .where(col(CookingTimerRow.session_id) == session_id)
                .where(col(CookingTimerRow.step_position) == step_position)
            )
        ).first()
        return None if row is None else _timer(row)


async def close_session(session_id: int, outcome: SessionOutcome) -> CookingSession | None:
    """End a session, one way or the other (UC-9.6, UC-9.8).

    One way. A session that ended is a record of what happened, and letting it reopen
    would be a second history of one meal — the same reasoning that makes a cooked plan
    slot permanent (ADR-004).

    Ending an ended session leaves the first ending in place, so a retried request cannot
    turn a completed meal into an abandoned one.
    """
    async with session() as active:
        row = await active.get(CookingSessionRow, session_id)
        if row is None:
            return None
        if row.outcome is None:
            row.outcome = outcome
            row.finished_at = _now()
            active.add(row)
            await active.commit()
            await active.refresh(row)
        return await _to_contract(active, row)
