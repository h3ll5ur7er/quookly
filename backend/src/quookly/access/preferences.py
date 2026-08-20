"""A cook's unit preferences.

Stored per ingredient kind, and merged over the defaults on the way out so callers never
have to reason about a partially configured cook.
"""

from sqlmodel import col, select

from quookly.access.database import session
from quookly.access.models import UnitPreferenceRow
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Unit
from quookly.contracts.preferences import DEFAULT_UNITS, UnitPreferences


async def for_cook(cook_id: int) -> UnitPreferences:
    """This cook's preferences, with defaults filling anything they have not chosen."""
    async with session() as active:
        rows = (
            await active.exec(
                select(UnitPreferenceRow).where(col(UnitPreferenceRow.cook_id) == cook_id)
            )
        ).all()
    chosen = {row.kind: row.unit for row in rows}
    return UnitPreferences({**DEFAULT_UNITS, **chosen})


async def choose(cook_id: int, kind: IngredientKind, unit: Unit) -> None:
    """Set the preferred unit for one kind, replacing any previous choice."""
    async with session() as active:
        existing = (
            await active.exec(
                select(UnitPreferenceRow).where(
                    col(UnitPreferenceRow.cook_id) == cook_id,
                    col(UnitPreferenceRow.kind) == kind,
                )
            )
        ).first()
        if existing is None:
            active.add(UnitPreferenceRow(cook_id=cook_id, kind=kind, unit=unit))
        else:
            existing.unit = unit
            active.add(existing)
        await active.commit()
