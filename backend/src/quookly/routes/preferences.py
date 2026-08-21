"""Unit preference endpoints (UC-6.2)."""

from fastapi import APIRouter, HTTPException, status

from quookly.contracts.errors import IncompatibleUnits, UnknownUnit
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.preferences import UnitChoice, UnitPreferenceView
from quookly.managers import preferences as preference_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()


@router.get("/preferences/units", response_model=list[UnitPreferenceView])
async def list_unit_preferences(cook: CurrentCook) -> list[UnitPreferenceView]:
    """Every kind of ingredient, and the unit this cook reads it in."""
    return await preference_manager.for_cook(cook.cook_id)


@router.put("/preferences/units/{kind}", response_model=list[UnitPreferenceView])
async def choose_unit(
    kind: IngredientKind, choice: UnitChoice, cook: CurrentCook
) -> list[UnitPreferenceView]:
    """Choose the unit for one kind of ingredient."""
    try:
        return await preference_manager.choose(cook.cook_id, kind, choice.unit)
    except UnknownUnit as unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown unit: {unknown}.",
        ) from None
    except IncompatibleUnits as mismatch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(mismatch),
        ) from None
