"""Eater endpoints — the household a cook cooks for."""

from fastapi import APIRouter, HTTPException, Response, status

from quookly.contracts.eater import EaterInput, EaterView
from quookly.managers import eater as eater_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

# Another cook's eater is reported as absent rather than as forbidden. Confirming that an
# id exists is itself a leak when what it holds is somebody's allergies.
NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such eater.")


@router.get("/eaters", response_model=list[EaterView])
async def list_eaters(cook: CurrentCook) -> list[EaterView]:
    """Everyone this cook cooks for."""
    return await eater_manager.list_for(cook.cook_id)


@router.post("/eaters", response_model=EaterView, status_code=status.HTTP_201_CREATED)
async def create_eater(submitted: EaterInput, cook: CurrentCook) -> EaterView:
    """Record somebody new (UC-6.3, UC-6.4)."""
    return await eater_manager.add(submitted, cook.cook_id)


@router.get("/eaters/{eater_id}", response_model=EaterView)
async def get_eater(eater_id: int, cook: CurrentCook) -> EaterView:
    """One eater, whole."""
    presented = await eater_manager.present(eater_id, cook.cook_id)
    if presented is None:
        raise NOT_FOUND
    return presented


@router.put("/eaters/{eater_id}", response_model=EaterView)
async def replace_eater(eater_id: int, submitted: EaterInput, cook: CurrentCook) -> EaterView:
    """Rewrite an eater, constraints included.

    A whole-person replacement rather than a patch, so removing a constraint in the form
    removes it here — there is no shape of request that leaves a deleted allergy behind.
    """
    updated = await eater_manager.replace(eater_id, submitted, cook.cook_id)
    if updated is None:
        raise NOT_FOUND
    return updated


@router.delete("/eaters/{eater_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_eater(eater_id: int, cook: CurrentCook) -> Response:
    """Forget somebody."""
    if not await eater_manager.remove(eater_id, cook.cook_id):
        raise NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)
