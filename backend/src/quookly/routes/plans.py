"""Plan endpoints — the week, and what it means you have to buy (UC-4.1 to UC-4.4)."""

from fastapi import APIRouter, HTTPException, Response, status

from quookly.contracts.plan import PlanInput, PlanSummaryView, PlanView, SlotInput
from quookly.managers import plan as plan_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

# Another cook's plan reads as absent rather than as forbidden: confirming that an id
# exists is itself an answer, and a plan names a household's week.
NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such plan.")


@router.get("/plans", response_model=list[PlanSummaryView])
async def list_plans(cook: CurrentCook) -> list[PlanSummaryView]:
    """This cook's plans."""
    return await plan_manager.list_for(cook.cook_id)


@router.post("/plans", response_model=PlanView, status_code=status.HTTP_201_CREATED)
async def create_plan(submitted: PlanInput, cook: CurrentCook) -> PlanView:
    """Open a period to plan (UC-4.1)."""
    return await plan_manager.open_plan(submitted, cook.cook_id)


@router.get("/plans/{plan_id}", response_model=PlanView)
async def get_plan(plan_id: int, cook: CurrentCook) -> PlanView:
    """The week, with its shopping list. A read — nothing here reserves or releases."""
    presented = await plan_manager.present(plan_id, cook.cook_id)
    if presented is None:
        raise NOT_FOUND
    return presented


@router.put("/plans/{plan_id}/slots", response_model=PlanView)
async def place_slot(plan_id: int, submitted: SlotInput, cook: CurrentCook) -> PlanView:
    """State one meal whole: the day, the dish, and who is coming (UC-4.1, UC-4.2).

    Returns the whole plan rather than the slot, because changing one meal changes the
    shopping list — and a client that worked out how would be a second copy of the
    manager.
    """
    placed = await plan_manager.place(plan_id, submitted, cook.cook_id)
    if placed is None:
        raise NOT_FOUND
    return placed


@router.post("/plans/{plan_id}/slots/{slot_id}/cooked", response_model=PlanView)
async def mark_cooked(plan_id: int, slot_id: int, cook: CurrentCook) -> PlanView:
    """Record that a planned meal was cooked, consuming what it held (UC-4.5, FR-19).

    One way. Un-marking would mean re-adding stock that never came back, which is the
    path ADR-004 was written to avoid; a mistake is corrected in the pantry, where
    quantities are restated anyway.
    """
    cooked = await plan_manager.mark_cooked(plan_id, slot_id, cook.cook_id)
    if cooked is None:
        raise NOT_FOUND
    return cooked


@router.delete("/plans/{plan_id}/slots/{slot_id}", response_model=PlanView)
async def clear_slot(plan_id: int, slot_id: int, cook: CurrentCook) -> PlanView:
    """Take a meal off the plan, releasing what it was holding.

    A body on a delete, unusually, for the same reason as above: the list has changed and
    the cook is looking at it.
    """
    cleared = await plan_manager.clear(plan_id, slot_id, cook.cook_id)
    if cleared is None:
        raise NOT_FOUND
    return cleared


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: int, cook: CurrentCook) -> Response:
    """Forget a plan, giving back everything it was holding."""
    if not await plan_manager.discard(plan_id, cook.cook_id):
        raise NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)
