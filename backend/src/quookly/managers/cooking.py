"""Cooking a meal, one step at a time (V15, UC-9.*).

The only session state in the system, which is why execution guidance earns a manager
rather than living inside `RecipeManager`. A session is opened for a **planned meal**: the
plan is where a meal is recorded, where its stock is held aside, and where "what did we eat
on Tuesday" is answered, and cooking mode is how one of those meals gets made
([ADR-042](../../../doc/07-decisions.md)).

On completion this states that the meal was cooked and returns. What happens to the stock
is the pantry's business (V9), and this manager does not know stock accounting exists.
"""

from collections.abc import Mapping
from datetime import UTC, datetime

from quookly.access import academy as academy_access
from quookly.access import cook as cook_access
from quookly.access import cooking as cooking_access
from quookly.access import eater as eater_access
from quookly.access import plan as plan_access
from quookly.access import preferences as preference_access
from quookly.access import recipe as recipe_access
from quookly.contracts.cooking import (
    CookingSession,
    GuidedStepView,
    PrepGroupView,
    SessionOutcome,
    SessionView,
    Timer,
    TimerView,
)
from quookly.contracts.eater import Eater
from quookly.contracts.events import MealCooked
from quookly.contracts.execution import ExecutionPlan, PlannedStep
from quookly.contracts.matching import MentionView
from quookly.contracts.plan import PlanSlot
from quookly.contracts.planning import PlannedMeal
from quookly.contracts.recipe import PresentedLine, Recipe
from quookly.contracts.suitability import VerdictView
from quookly.engines import execution, matching, measure, planning, suitability
from quookly.utilities import events
from quookly.utilities.diagnostics import get_logger

_log = get_logger("cooking")


def _now() -> datetime:
    """Now, as a value the tests can hold still. Every timer here is a claim about it."""
    return datetime.now(UTC)


async def _slot_of(session: CookingSession, cook_id: int) -> PlanSlot | None:
    """The meal this session is cooking, if it is this cook's.

    Another cook's session reads as absent rather than as forbidden, for the same reason
    another household's eater does: saying "forbidden" confirms it exists.
    """
    if session.cook_id != cook_id:
        return None
    return await plan_access.fetch_slot(session.plan_slot_id)


async def _owned_slot(plan_slot_id: int, cook_id: int) -> PlanSlot | None:
    slot = await plan_access.fetch_slot(plan_slot_id)
    if slot is None:
        return None
    plan = await plan_access.fetch(slot.plan_id)
    return None if plan is None or plan.cook_id != cook_id else slot


def _step_view(
    recipe: Recipe,
    planned: PlannedStep,
    lines: list[PresentedLine],
    timers: dict[int, Timer],
    jargon: dict[int, list[MentionView]],
) -> GuidedStepView:
    step = recipe.steps[planned.position]
    timer = timers.get(planned.position)
    return GuidedStepView(
        position=planned.position,
        instruction=step.instruction,
        mentions=jargon.get(planned.position, []),
        duration_seconds=step.duration_seconds,
        temperature_celsius=step.temperature_celsius,
        attention=step.attention,
        # The quantities this step asks for, sitting with the instruction. A cook at the
        # hob should not have to go back to the ingredient list to find out how much flour
        # "the flour" was.
        lines=[lines[position] for position in planned.lines if position < len(lines)],
        # A timer only once the cook has started one. One that exists beforehand is a
        # timer already counting down something nobody began.
        timer=(
            None
            if timer is None or step.duration_seconds is None
            else TimerView(
                step_position=timer.step_position,
                running_since=timer.running_since,
                elapsed_seconds=timer.elapsed_seconds,
                duration_seconds=step.duration_seconds,
            )
        ),
    )


def _judge(recipe: Recipe, slot: PlanSlot, eaters: Mapping[int, Eater]) -> VerdictView | None:
    """Whether the people at this meal can eat it.

    Judged here as well as on the plan, because this is the last moment before the food
    exists and a guest may have been added since it was planned. Nobody listed means no
    verdict rather than *suitable*: an empty table satisfies every constraint there is.
    """
    attending = [eaters[eater_id] for eater_id in slot.attendee_ids if eater_id in eaters]
    if not attending:
        return None
    return VerdictView.of(suitability.evaluate(suitability.facts_for(recipe.lines), attending))


async def _view(session: CookingSession, slot: PlanSlot, locale: str) -> SessionView | None:
    """The session as the cooking screen reads it: the meal, scaled and arranged."""
    if slot.recipe_id is None:
        return None
    recipe = await recipe_access.fetch(slot.recipe_id, locale)
    if recipe is None:
        return None

    attending = await eater_access.for_ids(slot.attendee_ids, session.cook_id)
    by_id = {eater.id: eater for eater in attending}

    # Sized by the same rule the plan used, so a session and the shopping list that bought
    # for it cannot come to different conclusions about how much to make (FR-18).
    sized = planning.requirements_for(
        [PlannedMeal(plan_slot_id=slot.id, recipe=recipe, eaters=list(attending))]
    ).meals[0]

    preferences = await preference_access.for_cook(session.cook_id)
    lines = measure.rendered_lines(recipe.lines, preferences, sized.factor)
    arranged: ExecutionPlan = execution.plan(recipe.lines, recipe.steps)
    timers = {timer.step_position: timer for timer in session.timers}

    # The same marks the recipe page carries (UC-9.5). Fetched once for the session rather
    # than per step: the vocabulary is the same for every step of it.
    vocabulary, names = await academy_access.vocabulary(locale)
    spotted = matching.mentioned_in([step.instruction for step in recipe.steps], vocabulary)
    jargon = {
        position: [
            MentionView(
                slug=one.slug, name=names.get(one.slug, one.slug), start=one.start, end=one.end
            )
            for one in found
        ]
        for position, found in enumerate(spotted)
    }

    return SessionView(
        id=session.id,
        plan_slot_id=slot.id,
        title=recipe.title,
        yield_quantity=measure.viewed(measure.scale(recipe.yield_quantity, sized.factor)),
        serves=measure.servings_of(recipe.serves, sized.factor),
        sizing=sized.sizing,
        suitability=_judge(recipe, slot, by_id),
        mise_en_place=[
            PrepGroupView(
                preparation=group.preparation,
                lines=[lines[position] for position in group.lines if position < len(lines)],
            )
            for group in arranged.mise_en_place
        ],
        ahead=[_step_view(recipe, one, lines, timers, jargon) for one in arranged.ahead],
        steps=[_step_view(recipe, one, lines, timers, jargon) for one in arranged.steps],
        at_step=session.at_step,
        started_at=session.started_at,
        finished_at=session.finished_at,
        outcome=session.outcome,
    )


async def _presented(
    session: CookingSession, cook_id: int, locale: str | None
) -> SessionView | None:
    slot = await _slot_of(session, cook_id)
    if slot is None:
        return None
    return await _view(session, slot, locale or await cook_access.locale_for(cook_id))


async def start(plan_slot_id: int, cook_id: int, locale: str | None = None) -> SessionView | None:
    """Begin cooking a planned meal (UC-9.1).

    Coming back to a meal already being cooked returns the session that is running rather
    than opening a second one. That is not a nicety: a cook who reopens the app has come
    back to what they were doing, and a fresh session would throw away where they were
    and every timer with it (UC-9.7).
    """
    slot = await _owned_slot(plan_slot_id, cook_id)
    if slot is None or slot.recipe_id is None:
        # A slot holding no dish cannot be cooked; there is nothing to follow.
        return None
    if slot.cooked_at is not None:
        # Already eaten. Cooking it again would be a second meal, and it would take stock
        # for one that was never planned.
        return None

    running = await cooking_access.open_for_slot(plan_slot_id)
    session = running or await cooking_access.open_session(cook_id, plan_slot_id)
    return await _presented(session, cook_id, locale)


async def resumable(cook_id: int, locale: str | None = None) -> list[SessionView]:
    """What this cook has on the go (UC-9.7).

    A list, because a kitchen has the oven on while something else simmers. Most of the
    time it holds nothing or one thing, and a screen can say so.
    """
    reading = locale or await cook_access.locale_for(cook_id)
    views = [
        await _presented(session, cook_id, reading)
        for session in await cooking_access.open_for_cook(cook_id)
    ]
    return [view for view in views if view is not None]


async def present(session_id: int, cook_id: int, locale: str | None = None) -> SessionView | None:
    """One session, whole. What a device picking the meal up asks for."""
    session = await cooking_access.fetch(session_id)
    return None if session is None else await _presented(session, cook_id, locale)


async def move_to(
    session_id: int, position: int | None, cook_id: int, locale: str | None = None
) -> SessionView | None:
    """Put the cook at a step, or back on the mise-en-place (UC-9.3).

    Absent is a real place rather than a missing answer: a cook goes back to the prep list
    to check what else wants chopping, and "nowhere" would be a worse thing to store.
    """
    session = await cooking_access.fetch(session_id)
    if session is None or await _slot_of(session, cook_id) is None:
        return None
    if not session.open:
        # A finished session is a record. Moving through it would be editing history.
        return None
    moved = await cooking_access.advance_step(session_id, position)
    return None if moved is None else await _presented(moved, cook_id, locale)


async def _retimed(
    session_id: int,
    step_position: int,
    cook_id: int,
    locale: str | None,
    change: str,
) -> SessionView | None:
    """Start, pause or reset one step's timer (UC-9.4).

    The three share everything but one line, and the one line is `ExecutionEngine`'s: the
    arithmetic that must not lose four minutes lives where it can be exhausted as a table
    of cases (ADR-013).
    """
    session = await cooking_access.fetch(session_id)
    if session is None or await _slot_of(session, cook_id) is None or not session.open:
        return None

    held = next(
        (timer for timer in session.timers if timer.step_position == step_position),
        execution.reset(step_position),
    )
    now = _now()
    match change:
        case "start":
            changed = execution.started(held, now)
        case "pause":
            changed = execution.paused(held, now)
        case _:
            changed = execution.reset(step_position)

    updated = await cooking_access.record_timer(session_id, changed)
    return None if updated is None else await _presented(updated, cook_id, locale)


async def start_timer(
    session_id: int, step_position: int, cook_id: int, locale: str | None = None
) -> SessionView | None:
    return await _retimed(session_id, step_position, cook_id, locale, "start")


async def pause_timer(
    session_id: int, step_position: int, cook_id: int, locale: str | None = None
) -> SessionView | None:
    return await _retimed(session_id, step_position, cook_id, locale, "pause")


async def reset_timer(
    session_id: int, step_position: int, cook_id: int, locale: str | None = None
) -> SessionView | None:
    return await _retimed(session_id, step_position, cook_id, locale, "reset")


async def complete(session_id: int, cook_id: int, locale: str | None = None) -> SessionView | None:
    """The meal is made (UC-9.6, FR-19).

    States the fact and lets whoever cares act on it. `PantryManager` owns inventory truth
    and subscribes; this manager does not know stock accounting exists, which is the
    Manager-to-Manager prohibition doing useful work rather than merely being obeyed.

    Published *before* the session is closed, for the reason ADR-039 gives: if closing
    then fails the cook finishes again, the claims are already gone, and consuming none
    consumes nothing. The other order would leave a meal recorded as cooked whose stock
    was never taken.
    """
    session = await cooking_access.fetch(session_id)
    slot = None if session is None else await _slot_of(session, cook_id)
    if session is None or slot is None:
        return None

    if session.open:
        await events.publish(
            MealCooked(cook_id=cook_id, plan_slot_id=session.plan_slot_id, at=_now())
        )
        # The plan is where a meal is recorded, so the slot learns it was cooked whichever
        # way the cook got there — guided, or a tap on the week.
        await plan_access.mark_cooked(session.plan_slot_id)
        await cooking_access.close_session(session_id, SessionOutcome.COMPLETED)
        _log.info("session %s completed for slot %s", session_id, session.plan_slot_id)

    return await present(session_id, cook_id, locale)


async def abandon(session_id: int, cook_id: int, locale: str | None = None) -> SessionView | None:
    """The cook stopped, and nothing was eaten (UC-9.8).

    Deliberately not a timeout, and deliberately not the same act as finishing. The
    difference between food that was eaten and food that was not is the difference the
    pantry turns on.

    **The meal keeps its claim on the stock.** An abandoned session did not un-plan the
    meal — Thursday's dinner is still Thursday's dinner, and releasing what it was holding
    would take it off the shopping list at the same time. Reservations belong to the
    planned meal and are let go when the meal is (ADR-038).
    """
    session = await cooking_access.fetch(session_id)
    if session is None or await _slot_of(session, cook_id) is None:
        return None
    await cooking_access.close_session(session_id, SessionOutcome.ABANDONED)
    return await present(session_id, cook_id, locale)
