"""Pantry endpoints — what is in the kitchen (UC-5.1 to UC-5.4)."""

from fastapi import APIRouter, HTTPException, Response, status

from quookly.contracts.errors import UnknownUnit
from quookly.contracts.pantry import AdjustInput, PantryEntry, ReceiveInput, WasteInput
from quookly.managers import pantry as pantry_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

# Another cook's lot reads as absent rather than as forbidden, for the same reason
# another household's eater does: confirming that an id exists is itself an answer.
NO_SUCH_LOT = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such stock.")
NO_SUCH_INGREDIENT = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="This instance has no ingredient by that name.",
)


@router.get("/pantry", response_model=list[PantryEntry])
async def list_pantry(cook: CurrentCook) -> list[PantryEntry]:
    """Everything this cook has, by ingredient (UC-5.2)."""
    return await pantry_manager.present(cook.cook_id)


# Declared before any `/pantry/{...}` route: they share a prefix, and the first match wins.
@router.get("/pantry/using-soon", response_model=list[PantryEntry])
async def list_using_soon(cook: CurrentCook) -> list[PantryEntry]:
    """What wants eating, most pressing first (UC-5.2)."""
    return await pantry_manager.using_soon(cook.cook_id)


@router.post("/pantry", response_model=PantryEntry, status_code=status.HTTP_201_CREATED)
async def receive_stock(submitted: ReceiveInput, cook: CurrentCook) -> PantryEntry:
    """Record stock arriving (UC-5.1).

    Returns the whole entry rather than the new lot, so the card a cook is looking at
    updates as a whole instead of the client guessing what the total became.
    """
    try:
        entry = await pantry_manager.receive(submitted, cook.cook_id)
    except UnknownUnit as unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown unit: {unknown}.",
        ) from None
    if entry is None:
        raise NO_SUCH_INGREDIENT
    return entry


@router.patch("/pantry/lots/{stock_item_id}", response_model=PantryEntry)
async def adjust_lot(stock_item_id: int, submitted: AdjustInput, cook: CurrentCook) -> PantryEntry:
    """Say how much is actually there (UC-5.3)."""
    entry = await pantry_manager.adjust(stock_item_id, submitted, cook.cook_id)
    if entry is None:
        raise NO_SUCH_LOT
    return entry


@router.post("/pantry/lots/{stock_item_id}/waste", response_model=PantryEntry)
async def record_waste(stock_item_id: int, submitted: WasteInput, cook: CurrentCook) -> PantryEntry:
    """Throw some of a lot away, and say why (UC-5.4).

    A different endpoint from `adjust` rather than a flag on it. Adjusting says the
    number was wrong; wasting says food left the kitchen. Only the second belongs in the
    figure this product exists to bring down, and one verb could never tell them apart.
    """
    try:
        entry = await pantry_manager.waste(stock_item_id, submitted, cook.cook_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    if entry is None:
        raise NO_SUCH_LOT
    return entry


@router.delete("/pantry/lots/{stock_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def discard_lot(stock_item_id: int, cook: CurrentCook) -> Response:
    """Delete a lot entered by mistake — food that was never in the house."""
    try:
        removed = await pantry_manager.discard(stock_item_id, cook.cook_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not removed:
        raise NO_SUCH_LOT
    return Response(status_code=status.HTTP_204_NO_CONTENT)
