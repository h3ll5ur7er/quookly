"""Planning a week: what is eaten when, whether it suits, and what has to be bought.

The sequence (UC-4.1 to UC-4.4): establish a period and its slots → resolve who is
attending each → size each meal to that table → verify suitability → reserve stock →
report what could not be reserved as the shopping list.

**Every change re-provisions the plan.** Claims are released and made again from scratch
rather than adjusted, so "the plan's reservations match the plan" is true by construction
instead of by remembering to keep them in step. The same argument as restating an eater's
constraints wholesale: a merge needs a way to say "and let this one go", and the version
that forgets to is the one that leaves stock spoken for by a meal nobody is cooking.

Reading never writes. A plan is presented from the claims that exist, so a GET cannot
change what a cook has reserved.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from quookly.access import cook as cook_access
from quookly.access import eater as eater_access
from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.access import plan as plan_access
from quookly.access import preferences as preference_access
from quookly.access import recipe as recipe_access
from quookly.contracts.eater import Eater
from quookly.contracts.events import MealCooked
from quookly.contracts.plan import (
    Meal,
    MealPlan,
    PlanInput,
    PlanSummaryView,
    PlanView,
    ShoppingLineView,
    SlotInput,
    SlotView,
)
from quookly.contracts.planning import PlannedMeal, PlanRequirements, SizedMeal
from quookly.contracts.provisioning import Covered
from quookly.contracts.recipe import Recipe
from quookly.contracts.suitability import VerdictView
from quookly.engines import measure, planning, replenishment, suitability
from quookly.utilities import events


def _tidy(value: Decimal) -> str:
    """A factor as it reads. 1.0000 is how a computation leaves one batch."""
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


async def _meals_of(
    plan: MealPlan, locale: str
) -> tuple[list[PlannedMeal], dict[int, Recipe], dict[int, Eater]]:
    """The filled slots, with their recipes and the people at them.

    Recipes are fetched once each rather than once per slot: the same dish twice in a
    week is the ordinary case, not the exception.
    """
    recipe_ids = sorted({slot.recipe_id for slot in plan.slots if slot.recipe_id is not None})
    recipes: dict[int, Recipe] = {}
    for recipe_id in recipe_ids:
        found = await recipe_access.fetch(recipe_id, locale)
        if found is not None and found.cook_id == plan.cook_id:
            recipes[recipe_id] = found

    attending = await eater_access.for_ids(
        sorted({eater_id for slot in plan.slots for eater_id in slot.attendee_ids}),
        plan.cook_id,
    )
    by_id = {eater.id: eater for eater in attending}

    # Cooked meals are left out. They are a record rather than a plan: the food is eaten,
    # so they need no stock held and nothing bought for them.
    meals = [
        PlannedMeal(
            plan_slot_id=slot.id,
            recipe=recipes[slot.recipe_id],
            eaters=[by_id[eater_id] for eater_id in slot.attendee_ids if eater_id in by_id],
        )
        for slot in plan.slots
        if slot.recipe_id is not None and slot.recipe_id in recipes and slot.cooked_at is None
    ]
    return meals, recipes, by_id


async def _densities(needed: PlanRequirements) -> dict[int, Decimal | None]:
    return await registry.densities_for(
        sorted({requirement.ingredient_id for requirement in needed.requirements})
    )


async def _reprovision(plan: MealPlan, locale: str) -> None:
    """Let go of everything this plan holds, then hold what it needs again.

    Wholesale rather than incrementally. Between the release and the reserve this plan's
    stock is briefly free, which on a household instance means nothing — and the
    alternative is arithmetic that has to stay right across every kind of edit.
    """
    for slot in plan.slots:
        await pantry_access.release_for_slot(slot.id)

    meals, _, _ = await _meals_of(plan, locale)
    needed = planning.requirements_for(meals)
    if not needed.requirements:
        return

    provided = replenishment.net(
        needed.requirements,
        await pantry_access.available(
            plan.cook_id,
            sorted({requirement.ingredient_id for requirement in needed.requirements}),
        ),
        await _densities(needed),
    )
    for draw in provided.draws:
        await pantry_access.reserve_against(
            draw.stock_item_id, plan_slot_id=draw.plan_slot_id, quantity=draw.quantity
        )


async def _covered(plan: MealPlan) -> list[Covered]:
    """What each meal is holding, said in terms of ingredients rather than lots.

    The shopping list is worked out from these — from the claims that were really made,
    not from a second pass over what is on the shelf. Two passes are two answers to the
    same question, and FR-7 is the promise that there is one.
    """
    covered: list[Covered] = []
    for slot in plan.slots:
        for claim in await pantry_access.held_for_slot(slot.id):
            lot = await pantry_access.fetch(claim.stock_item_id)
            if lot is not None:
                covered.append(
                    Covered(
                        plan_slot_id=slot.id,
                        ingredient_id=lot.ingredient_id,
                        quantity=claim.quantity,
                    )
                )
    return covered


def _already_cooked(plan: MealPlan, on_date: date, meal: Meal) -> bool:
    return any(
        slot.on_date == on_date and slot.meal is meal and slot.cooked_at is not None
        for slot in plan.slots
    )


def _judge(recipe: Recipe, eaters: Sequence[Eater]) -> VerdictView | None:
    """Whether the people coming can eat this (UC-4.3).

    Nobody named means no verdict rather than *suitable*. An empty table satisfies every
    constraint there is, and reporting that as a clean bill of health would be a
    reassurance about a question nobody asked.
    """
    if not eaters:
        return None
    return VerdictView.of(suitability.evaluate(suitability.facts_for(recipe.lines), list(eaters)))


async def _view(plan: MealPlan, locale: str) -> PlanView:
    meals, recipes, people = await _meals_of(plan, locale)
    by_slot: dict[int, PlannedMeal] = {meal.plan_slot_id: meal for meal in meals}
    needed = planning.requirements_for(meals)
    sized: dict[int, SizedMeal] = {one.plan_slot_id: one for one in needed.meals}

    densities = await _densities(needed)
    missing = replenishment.outstanding(needed.requirements, await _covered(plan), densities)

    names = await registry.for_ids([line.ingredient_id for line in missing], locale)
    preferences = await preference_access.for_cook(plan.cook_id)
    shopping = [
        ShoppingLineView(
            ingredient_id=line.ingredient_id,
            name=names[line.ingredient_id].name
            if line.ingredient_id in names
            else str(line.ingredient_id),
            quantity=str(
                measure.render(
                    line.quantity,
                    names[line.ingredient_id].kind,
                    names[line.ingredient_id].density,
                    preferences,
                )
                if line.ingredient_id in names
                else line.quantity
            ),
        )
        for line in missing
    ]

    slots = []
    for slot in plan.slots:
        meal = by_slot.get(slot.id)
        size = sized.get(slot.id)
        # Read from the recipes and the household rather than from the meal, because a
        # cooked slot has no meal — it is out of the sizing — and still has to say what
        # was cooked and who was there.
        dish = None if slot.recipe_id is None else recipes.get(slot.recipe_id)
        slots.append(
            SlotView(
                id=slot.id,
                on_date=slot.on_date,
                meal=slot.meal,
                recipe_id=slot.recipe_id,
                recipe_title=None if dish is None else dish.title,
                attendee_ids=slot.attendee_ids,
                attendees=[
                    people[eater_id].name for eater_id in slot.attendee_ids if eater_id in people
                ],
                cooked=slot.cooked_at is not None,
                factor=None if size is None else _tidy(size.factor),
                sizing=None if size is None else size.sizing,
                suitability=None if meal is None else _judge(meal.recipe, meal.eaters),
            )
        )

    return PlanView(
        id=plan.id,
        starts_on=plan.starts_on,
        ends_on=plan.ends_on,
        slots=slots,
        shopping=shopping,
    )


async def _owned(plan_id: int, cook_id: int) -> MealPlan | None:
    """The plan, if it is this cook's. Another cook's reads as absent rather than as
    forbidden, for the same reason another household's eater does."""
    plan = await plan_access.fetch(plan_id)
    return None if plan is None or plan.cook_id != cook_id else plan


async def list_for(cook_id: int) -> list[PlanSummaryView]:
    """This cook's plans, most recent period first."""
    return [
        PlanSummaryView(
            id=plan.id,
            starts_on=plan.starts_on,
            ends_on=plan.ends_on,
            planned=sum(1 for slot in plan.slots if slot.recipe_id is not None),
        )
        for plan in await plan_access.list_for_cook(cook_id)
    ]


async def open_plan(submitted: PlanInput, cook_id: int, locale: str | None = None) -> PlanView:
    """Open a period to plan (UC-4.1)."""
    plan = await plan_access.create(
        cook_id=cook_id, starts_on=submitted.starts_on, ends_on=submitted.ends_on
    )
    return await _view(plan, locale or await cook_access.locale_for(cook_id))


async def present(plan_id: int, cook_id: int, locale: str | None = None) -> PlanView | None:
    """The week and its shopping list. A read: nothing here reserves or releases."""
    plan = await _owned(plan_id, cook_id)
    if plan is None:
        return None
    return await _view(plan, locale or await cook_access.locale_for(cook_id))


async def place(
    plan_id: int, submitted: SlotInput, cook_id: int, locale: str | None = None
) -> PlanView | None:
    """State one meal whole: the day, the dish, and who is coming (UC-4.1, UC-4.2)."""
    plan = await _owned(plan_id, cook_id)
    if plan is None or _already_cooked(plan, submitted.on_date, submitted.meal):
        # A cooked meal is a record. Editing one would re-reserve stock for food that has
        # been eaten, and there is no honest way to un-cook it.
        return None
    reading = locale or await cook_access.locale_for(cook_id)

    slot = await plan_access.open_slot(plan_id, on_date=submitted.on_date, meal=submitted.meal)
    # A recipe that is not this cook's reads as no recipe at all, rather than as a
    # refusal: an id belonging to somebody else is not theirs to be told about.
    recipe = (
        None
        if submitted.recipe_id is None
        else await recipe_access.fetch(submitted.recipe_id, reading)
    )
    await plan_access.assign(
        slot.id, None if recipe is None or recipe.cook_id != cook_id else recipe.id
    )
    # Scoped to the cook, so an eater id from another household seats nobody.
    theirs = {eater.id for eater in await eater_access.for_ids(submitted.attendee_ids, cook_id)}
    await plan_access.attend(slot.id, [one for one in submitted.attendee_ids if one in theirs])

    return await _restate(plan_id, cook_id, reading)


async def clear(
    plan_id: int, slot_id: int, cook_id: int, locale: str | None = None
) -> PlanView | None:
    """Take a meal off the plan (UC-4.1).

    Its claims go first. `close_slot` refuses while any are held, which is what makes the
    order impossible to get wrong — a claim left pointing at a deleted meal is stock that
    is neither free nor gone.
    """
    plan = await _owned(plan_id, cook_id)
    kept = None if plan is None else next((one for one in plan.slots if one.id == slot_id), None)
    if kept is None or kept.cooked_at is not None:
        return None
    await pantry_access.release_for_slot(slot_id)
    await plan_access.close_slot(slot_id)
    return await _restate(plan_id, cook_id, locale or await cook_access.locale_for(cook_id))


async def mark_cooked(
    plan_id: int, slot_id: int, cook_id: int, locale: str | None = None
) -> PlanView | None:
    """Record that a planned meal was cooked (UC-4.5, FR-19).

    States the fact and lets whoever cares act on it. What actually happens to the stock
    is the pantry's business, and this manager does not know that stock accounting exists
    — which is what will let a cooking session (Phase 5) publish the same fact without
    either of them learning about the other.

    The fact is published *before* the slot is marked. If marking then fails, the cook
    marks it again: the claims are already gone, consuming none consumes nothing, and the
    second attempt lands. The other order would leave a meal recorded as cooked whose
    stock was never taken — reserved forever, which is the failure ADR-004 exists to
    prevent.
    """
    plan = await _owned(plan_id, cook_id)
    if plan is None:
        return None
    slot = next((one for one in plan.slots if one.id == slot_id), None)
    if slot is None or slot.recipe_id is None:
        # A slot holding no dish was not cooked; it was skipped. Marking it would put a
        # meal in the record that nobody ate.
        return None

    if slot.cooked_at is None:
        await events.publish(
            MealCooked(cook_id=cook_id, plan_slot_id=slot_id, at=datetime.now(UTC))
        )
        await plan_access.mark_cooked(slot_id)

    reread = await _owned(plan_id, cook_id)
    return (
        None
        if reread is None
        else await _view(reread, locale or await cook_access.locale_for(cook_id))
    )


async def discard(plan_id: int, cook_id: int) -> bool:
    """Forget a plan, giving back everything it was holding."""
    plan = await _owned(plan_id, cook_id)
    if plan is None:
        return False
    for slot in plan.slots:
        await pantry_access.release_for_slot(slot.id)
    return await plan_access.remove(plan_id)


async def _restate(plan_id: int, cook_id: int, locale: str) -> PlanView | None:
    """Re-read the plan, re-provision it, and hand it back whole.

    Re-read because the change has happened and the copy in hand is stale; whole because
    a client that had to work out what a change did to the shopping list would be a
    second implementation of this manager.
    """
    plan = await _owned(plan_id, cook_id)
    if plan is None:
        return None
    await _reprovision(plan, locale)
    return await _view(plan, locale)
