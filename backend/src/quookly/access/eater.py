"""Access to eaters and their dietary constraints, in domain verbs.

An eater is stored as a row plus a set of constraint rows, and returned as one whole
person. Callers deal in people; rows and joins stay here.

Everything read out of here feeds `SuitabilityEngine`, which is the safety-critical path.
Two behaviours therefore matter more than the rest and are tested as such: a constraint
removed in the interface is really gone, and severity survives the round trip unchanged.
"""

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from quookly.access.database import session
from quookly.access.models import EaterConstraintRow, EaterRow
from quookly.contracts.eater import STANDARD_PORTION, AgeBand, Constraint, Eater

# Two places is as fine as a portion multiplier gets: the difference between 1.33 and
# 1.333 of a serving is not something anybody can plate.
APPETITE_PRECISION = Decimal("0.01")

_UNSET: AgeBand | str | Decimal | None = None


def _appetite(value: Decimal) -> Decimal:
    """Round to what is stored, and refuse what cannot be eaten.

    Rounding here rather than letting the column do it means the value read back is the
    value `add` returned, instead of the two disagreeing until somebody reloads the page.
    """
    if value <= 0:
        raise ValueError("an appetite multiplier is greater than zero")
    return value.quantize(APPETITE_PRECISION, rounding=ROUND_HALF_UP)


def _distinct(constraints: Sequence[Constraint]) -> list[Constraint]:
    """Drop exact repeats, keeping the order they were given in.

    Only *exact* repeats. Two constraints naming the same allergen at different severities
    contradict each other, and resolving that is a judgement for `SuitabilityEngine` — it
    already takes the worst finding — not something storage should quietly decide.
    """
    seen: set[Constraint] = set()
    kept: list[Constraint] = []
    for constraint in constraints:
        if constraint not in seen:
            seen.add(constraint)
            kept.append(constraint)
    return kept


def _to_contract(row: EaterRow, constraints: list[Constraint]) -> Eater:
    assert row.id is not None, "a persisted eater always has an id"
    return Eater(
        id=row.id,
        cook_id=row.cook_id,
        name=row.name,
        age_band=row.age_band,
        appetite=row.appetite,
        constraints=constraints,
    )


async def _constraints_for(
    active: AsyncSession, eater_ids: Sequence[int]
) -> dict[int, list[Constraint]]:
    """Every constraint for these eaters, in one query rather than one per person."""
    gathered: dict[int, list[Constraint]] = {eater_id: [] for eater_id in eater_ids}
    if not eater_ids:
        return gathered
    rows = (
        await active.exec(
            select(EaterConstraintRow)
            .where(col(EaterConstraintRow.eater_id).in_(eater_ids))
            .order_by(col(EaterConstraintRow.id))
        )
    ).all()
    for row in rows:
        gathered[row.eater_id].append(
            Constraint(
                allergen=row.allergen,
                ingredient_slug=row.ingredient_slug,
                severity=row.severity,
            )
        )
    return gathered


async def _load(active: AsyncSession, rows: Sequence[EaterRow]) -> list[Eater]:
    ids = [row.id for row in rows if row.id is not None]
    constraints = await _constraints_for(active, ids)
    return [_to_contract(row, constraints[row.id]) for row in rows if row.id is not None]


async def add(
    *,
    cook_id: int,
    name: str,
    age_band: AgeBand,
    appetite: Decimal = STANDARD_PORTION,
    constraints: Sequence[Constraint] = (),
) -> Eater:
    """Record somebody this cook cooks for (UC-6.3, UC-6.4)."""
    row = EaterRow(cook_id=cook_id, name=name, age_band=age_band, appetite=_appetite(appetite))
    async with session() as active:
        active.add(row)
        await active.flush()
        assert row.id is not None
        kept = _distinct(constraints)
        for constraint in kept:
            active.add(
                EaterConstraintRow(
                    eater_id=row.id,
                    allergen=constraint.allergen,
                    ingredient_slug=constraint.ingredient_slug,
                    severity=constraint.severity,
                )
            )
        await active.commit()
        await active.refresh(row)
        return _to_contract(row, kept)


async def fetch(eater_id: int) -> Eater | None:
    """One eater whole, constraints included."""
    async with session() as active:
        row = await active.get(EaterRow, eater_id)
        if row is None:
            return None
        return (await _load(active, [row]))[0]


async def list_for_cook(cook_id: int) -> list[Eater]:
    """This cook's household, in the order it was built up."""
    async with session() as active:
        rows = (
            await active.exec(
                select(EaterRow).where(col(EaterRow.cook_id) == cook_id).order_by(col(EaterRow.id))
            )
        ).all()
        return await _load(active, rows)


async def for_ids(eater_ids: Sequence[int], cook_id: int) -> list[Eater]:
    """The named eaters, whole — for "cook this, for these four people".

    Scoped to the cook, so an id belonging to another household comes back as nothing
    rather than as somebody's medical history. Returned in the household's own order.
    """
    if not eater_ids:
        return []
    async with session() as active:
        rows = (
            await active.exec(
                select(EaterRow)
                .where(
                    col(EaterRow.cook_id) == cook_id,
                    col(EaterRow.id).in_(list(eater_ids)),
                )
                .order_by(col(EaterRow.id))
            )
        ).all()
        return await _load(active, rows)


async def amend(
    eater_id: int,
    *,
    name: str | None = None,
    age_band: AgeBand | None = None,
    appetite: Decimal | None = None,
) -> Eater | None:
    """Change what is known about a person, leaving their constraints alone.

    Constraints are restated separately: folding them in would mean every rename had to
    resend the whole list, and forgetting to would delete an allergy.
    """
    async with session() as active:
        row = await active.get(EaterRow, eater_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if age_band is not None:
            row.age_band = age_band
        if appetite is not None:
            row.appetite = _appetite(appetite)
        active.add(row)
        await active.commit()
        await active.refresh(row)
        return (await _load(active, [row]))[0]


async def restate_constraints(eater_id: int, constraints: Sequence[Constraint]) -> Eater | None:
    """Replace this eater's constraints with exactly these.

    Wholesale, because the interface edits the whole list: merging instead would leave a
    constraint the cook deleted still applying, which is the wrong way round to fail.
    """
    async with session() as active:
        row = await active.get(EaterRow, eater_id)
        if row is None:
            return None
        await active.exec(
            delete(EaterConstraintRow).where(col(EaterConstraintRow.eater_id) == eater_id)
        )
        kept = _distinct(constraints)
        for constraint in kept:
            active.add(
                EaterConstraintRow(
                    eater_id=eater_id,
                    allergen=constraint.allergen,
                    ingredient_slug=constraint.ingredient_slug,
                    severity=constraint.severity,
                )
            )
        await active.commit()
        return _to_contract(row, kept)


async def remove(eater_id: int) -> bool:
    """Forget somebody, and their constraints with them.

    The constraint rows go explicitly rather than by cascade. Left behind they would
    attach themselves to whoever next took that id — someone else's allergies, silently.
    """
    async with session() as active:
        row = await active.get(EaterRow, eater_id)
        if row is None:
            return False
        await active.exec(
            delete(EaterConstraintRow).where(col(EaterConstraintRow.eater_id) == eater_id)
        )
        await active.delete(row)
        await active.commit()
        return True
