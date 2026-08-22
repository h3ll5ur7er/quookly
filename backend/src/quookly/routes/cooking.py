"""Cooking-mode endpoints — a meal being made, one step at a time (UC-9.*)."""

from fastapi import APIRouter, HTTPException, status

from quookly.contracts.cooking import AtStepInput, CookNowInput, SessionView, StartInput
from quookly.managers import cooking as cooking_manager
from quookly.managers import plan as plan_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

# Another cook's session reads as absent rather than as forbidden, and so does a meal that
# cannot be cooked: confirming an id exists is itself an answer.
NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such meal to cook.")


@router.get("/cooking/sessions", response_model=list[SessionView])
async def list_sessions(cook: CurrentCook) -> list[SessionView]:
    """What this cook has on the go (UC-9.7).

    The endpoint that makes an interrupted session findable at all. A list rather than one
    session, because a kitchen has the oven on while something else simmers.
    """
    return await cooking_manager.resumable(cook.cook_id)


@router.post("/cooking/sessions", response_model=SessionView, status_code=status.HTTP_201_CREATED)
async def start_session(submitted: StartInput, cook: CurrentCook) -> SessionView:
    """Begin cooking a planned meal (UC-9.1, UC-9.2).

    Asking for a meal already being cooked returns the session that is running. A cook who
    reopens the app has come back to what they were doing, and a second session would
    throw away where they were and every timer with it.
    """
    started = await cooking_manager.start(submitted.plan_slot_id, cook.cook_id)
    if started is None:
        raise NOT_FOUND
    return started


@router.post(
    "/cooking/sessions/for-recipe",
    response_model=SessionView,
    status_code=status.HTTP_201_CREATED,
)
async def start_recipe(submitted: CookNowInput, cook: CurrentCook) -> SessionView:
    """Cook a recipe outright, without planning it first (UC-9.1b).

    *Plan it for today, then cook it* — the two calls ADR-042 said this would be, composed
    here because a route is the one layer allowed to reach two managers. Neither manager
    learns about the other, and the meal is reserved for and recorded exactly as a planned
    one is, because it **is** a planned one by the time cooking sees it.

    Its own path rather than a nullable field on the endpoint above: that one names a meal,
    this one names a dish.
    """
    placed = await plan_manager.slot_for_now(submitted.recipe_id, cook.cook_id)
    if placed is None:
        raise NOT_FOUND
    started = await cooking_manager.start(placed.id, cook.cook_id)
    if started is None:
        raise NOT_FOUND
    return started


@router.get("/cooking/sessions/{session_id}", response_model=SessionView)
async def get_session(session_id: int, cook: CurrentCook) -> SessionView:
    """The whole session — prep list, steps, timers, and where the cook is."""
    presented = await cooking_manager.present(session_id, cook.cook_id)
    if presented is None:
        raise NOT_FOUND
    return presented


@router.put("/cooking/sessions/{session_id}/step", response_model=SessionView)
async def move_to_step(session_id: int, submitted: AtStepInput, cook: CurrentCook) -> SessionView:
    """Put the cook at a step, or back on the mise-en-place (UC-9.3).

    A position rather than "next", because a cook goes back to re-read the step before as
    often as they go on.
    """
    moved = await cooking_manager.move_to(session_id, submitted.position, cook.cook_id)
    if moved is None:
        raise NOT_FOUND
    return moved


@router.post("/cooking/sessions/{session_id}/timers/{step_position}/started")
async def start_timer(session_id: int, step_position: int, cook: CurrentCook) -> SessionView:
    """Set a step's timer running (UC-9.4).

    The server records the instant; the client counts. Which is what lets a locked phone
    and a tablet in the other room agree about how long the sauce has had.
    """
    started = await cooking_manager.start_timer(session_id, step_position, cook.cook_id)
    if started is None:
        raise NOT_FOUND
    return started


@router.post("/cooking/sessions/{session_id}/timers/{step_position}/paused")
async def pause_timer(session_id: int, step_position: int, cook: CurrentCook) -> SessionView:
    """Stop a step's timer, keeping what it has counted (UC-9.4)."""
    paused = await cooking_manager.pause_timer(session_id, step_position, cook.cook_id)
    if paused is None:
        raise NOT_FOUND
    return paused


@router.post("/cooking/sessions/{session_id}/timers/{step_position}/reset")
async def reset_timer(session_id: int, step_position: int, cook: CurrentCook) -> SessionView:
    """Put a step's timer back to nothing (UC-9.4)."""
    reset = await cooking_manager.reset_timer(session_id, step_position, cook.cook_id)
    if reset is None:
        raise NOT_FOUND
    return reset


@router.post("/cooking/sessions/{session_id}/completed", response_model=SessionView)
async def complete_session(session_id: int, cook: CurrentCook) -> SessionView:
    """The meal is made (UC-9.6, FR-19).

    Consumes what the meal was holding, and marks it cooked on the plan. One way, for the
    reason ADR-004 gives: un-marking would mean re-adding stock that never came back.
    """
    completed = await cooking_manager.complete(session_id, cook.cook_id)
    if completed is None:
        raise NOT_FOUND
    return completed


@router.post("/cooking/sessions/{session_id}/abandoned", response_model=SessionView)
async def abandon_session(session_id: int, cook: CurrentCook) -> SessionView:
    """The cook stopped, and nothing was eaten (UC-9.8).

    The meal keeps its claim on the stock: it is still planned, and releasing what it was
    holding would take it off the shopping list at the same time.
    """
    abandoned = await cooking_manager.abandon(session_id, cook.cook_id)
    if abandoned is None:
        raise NOT_FOUND
    return abandoned
