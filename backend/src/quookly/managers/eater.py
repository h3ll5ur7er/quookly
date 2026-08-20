"""Eaters: recording who is cooked for, and keeping households apart.

The sequence is short — this manager exists because a client may not call resource access
directly, and because ownership has to be decided somewhere above the store.

Ownership is decided here rather than in the routes, and it is decided by returning
nothing rather than by refusing. An eater belonging to another cook reads as absent: a
403 would confirm that the id exists, and what it holds is somebody's medical history.
"""

from decimal import Decimal

from quookly.access import eater as eater_access
from quookly.contracts.eater import (
    Constraint,
    ConstraintView,
    Eater,
    EaterInput,
    EaterView,
)


def _view(eater: Eater) -> EaterView:
    return EaterView(
        id=eater.id,
        name=eater.name,
        age_band=eater.age_band,
        appetite=_tidy(eater.appetite),
        constraints=[
            ConstraintView(
                allergen=constraint.allergen,
                ingredient_slug=constraint.ingredient_slug,
                severity=constraint.severity,
            )
            for constraint in eater.constraints
        ],
    )


def _tidy(appetite: Decimal) -> str:
    """Render the multiplier the way it was meant, not the way it is stored.

    A standard portion is stored as 1.00 and reads as "1". Trailing zeros from the column
    are an artefact of storage, and putting them in front of a cook invites them to think
    the precision means something.
    """
    text = f"{appetite:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _constraints(submitted: EaterInput) -> list[Constraint]:
    return [
        Constraint(
            allergen=constraint.allergen,
            ingredient_slug=constraint.ingredient_slug,
            severity=constraint.severity,
        )
        for constraint in submitted.constraints
    ]


async def list_for(cook_id: int) -> list[EaterView]:
    """This cook's household."""
    return [_view(eater) for eater in await eater_access.list_for_cook(cook_id)]


async def add(submitted: EaterInput, cook_id: int) -> EaterView:
    """Record somebody new (UC-6.3)."""
    recorded = await eater_access.add(
        cook_id=cook_id,
        name=submitted.name,
        age_band=submitted.age_band,
        appetite=submitted.appetite,
        constraints=_constraints(submitted),
    )
    return _view(recorded)


async def present(eater_id: int, cook_id: int) -> EaterView | None:
    """One eater, if they are this cook's to see."""
    eater = await eater_access.fetch(eater_id)
    if eater is None or eater.cook_id != cook_id:
        return None
    return _view(eater)


async def replace(eater_id: int, submitted: EaterInput, cook_id: int) -> EaterView | None:
    """Rewrite an eater whole, constraints included (UC-6.4).

    Both halves or neither: the details are amended and the constraints restated, so a
    cook who deletes an allergy in the form has deleted it everywhere.
    """
    existing = await eater_access.fetch(eater_id)
    if existing is None or existing.cook_id != cook_id:
        return None
    await eater_access.amend(
        eater_id,
        name=submitted.name,
        age_band=submitted.age_band,
        appetite=submitted.appetite,
    )
    updated = await eater_access.restate_constraints(eater_id, _constraints(submitted))
    return None if updated is None else _view(updated)


async def remove(eater_id: int, cook_id: int) -> bool:
    """Forget somebody. False if they were never this cook's to forget."""
    existing = await eater_access.fetch(eater_id)
    if existing is None or existing.cook_id != cook_id:
        return False
    return await eater_access.remove(eater_id)
