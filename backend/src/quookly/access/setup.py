"""What a cook has explicitly answered during setup.

The only part of onboarding that is stored (ADR-014). Progress itself is derived from the
profile every time it is asked for; what cannot be derived is the difference between a
cook who has no dietary constraints to record and one who has never been asked (FR-15).
"""

from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from quookly.access.database import session
from quookly.access.models import SetupDeclarationRow
from quookly.contracts.onboarding import SetupStep


async def declare(cook_id: int, step: SetupStep) -> None:
    """Record that this cook answered this question, whatever the answer was.

    Declaring twice is not an error. A cook tapping "nobody has any" a second time has
    said the same true thing again, and refusing it would be a failure they cannot act on.
    """
    async with session() as active:
        active.add(SetupDeclarationRow(cook_id=cook_id, step=step))
        try:
            await active.commit()
        except IntegrityError:
            await active.rollback()


async def declarations_for(cook_id: int) -> frozenset[SetupStep]:
    """Which questions this cook has answered outright."""
    async with session() as active:
        rows = (
            await active.exec(
                select(SetupDeclarationRow).where(col(SetupDeclarationRow.cook_id) == cook_id)
            )
        ).all()
    return frozenset(row.step for row in rows)
