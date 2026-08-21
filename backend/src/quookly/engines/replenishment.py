"""Netting what a plan needs against what is already in the kitchen (V8, UC-4.4).

A rule engine: pure functions of their arguments. Availability and densities arrive as
parameters rather than being fetched, which is what makes the two decisions here
exhaustible as a table of cases.

Those two decisions carry most of the weight. **Which lot is drawn from** decides whether
food gets eaten before it spoils, which is most of why this product exists. And **what is
left over** is the shopping list — derived from the same pass rather than computed a
second way, so the list and the reservations cannot come to disagree (FR-7).
"""

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from quookly.contracts.errors import DensityRequired, IncompatibleUnits
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.pantry import Availability
from quookly.contracts.provisioning import (
    Covered,
    Draw,
    Provisioning,
    Requirement,
    Shortfall,
)
from quookly.engines import measure

#: A date every real one sorts before, for lots that carry none. An undated packet cannot
#: go off, so it is the one that can wait — reached for only once the dated ones are gone.
_NEVER = date.max

NOTHING = Decimal(0)


def _urgency(entry: Availability) -> tuple[date, Decimal, int]:
    """The order lots are drawn in: soonest to go off, then smallest, then by id.

    Smallest first among equal dates finishes the straggler. Two open bags of flour where
    one is nearly empty should become one open bag, not two emptier ones — which is how
    half-used packets stop accumulating at the back of a cupboard.

    The id is a tiebreak and nothing more. Without it the order would depend on how the
    rows happened to arrive, and a plan would not reserve the same stock twice running.
    """
    return (entry.lot.expires_on or _NEVER, entry.free.magnitude, entry.lot.id)


def _converted(quantity: Quantity, target: Unit, density: Decimal | None) -> Quantity | None:
    """`quantity` in `target`, or nothing if the two do not correspond.

    Not an error. A lot of milk measured by mass simply cannot answer "how much of it is
    200 ml" without a density, and assuming water would misweigh it. The lot stays where
    it is and the need goes on the shopping list instead.
    """
    try:
        return measure.convert(quantity, target, density)
    except (IncompatibleUnits, DensityRequired):
        return None


def _add(running: Quantity, addition: Quantity, density: Decimal | None) -> Quantity | None:
    """`running` plus `addition`, expressed in `running`'s unit, or nothing."""
    converted = _converted(addition, running.unit, density)
    if converted is None:
        return None
    return Quantity(running.magnitude + converted.magnitude, running.unit)


def net(
    requirements: Sequence[Requirement],
    availability: Sequence[Availability],
    densities: Mapping[int, Decimal | None],
) -> Provisioning:
    """What the plan can take from the kitchen, and what it still needs.

    Requirements are served in the order given, so a plan's earlier meals get first call
    on a lot that cannot cover both. Arbitrary, but it has to be *something*, and the
    order the cook laid the week out in is the one they will expect.
    """
    spare: dict[int, Decimal] = {entry.lot.id: entry.free.magnitude for entry in availability}
    by_ingredient: dict[int, list[Availability]] = {}
    for entry in sorted(availability, key=_urgency):
        by_ingredient.setdefault(entry.lot.ingredient_id, []).append(entry)

    draws: list[Draw] = []
    missing: list[Shortfall] = []

    for requirement in requirements:
        wanted = requirement.quantity
        if wanted is None:
            # Salt to taste. Twice as much to taste is still to taste, and putting a
            # number on a shopping list would be inventing an amount nobody wrote.
            continue
        density = densities.get(requirement.ingredient_id)
        # Tracked in the *requirement's* unit throughout. Subtracting each draw after
        # converting it back would leave a hair behind on every non-terminating
        # conversion, and a shortfall of 0.0000001 g reads as "buy more flour".
        still_needed = wanted.magnitude

        for entry in by_ingredient.get(requirement.ingredient_id, []):
            if still_needed <= NOTHING:
                break
            free = spare[entry.lot.id]
            if free <= NOTHING:
                continue
            in_our_terms = _converted(Quantity(free, entry.free.unit), wanted.unit, density)
            if in_our_terms is None:
                continue

            taking = min(still_needed, in_our_terms.magnitude)
            from_the_lot = _converted(Quantity(taking, wanted.unit), entry.free.unit, density)
            if from_the_lot is None:  # pragma: no cover - the reverse of a conversion that worked
                continue
            # Clamped, because converting there and back can land a hair over what is
            # there — and a reservation for more than is free is refused outright, which
            # would fail the whole plan over a rounding artefact.
            drawn = min(from_the_lot.magnitude, free)
            if drawn <= NOTHING:
                continue

            spare[entry.lot.id] = free - drawn
            still_needed -= taking
            draws.append(
                Draw(
                    plan_slot_id=requirement.plan_slot_id,
                    stock_item_id=entry.lot.id,
                    quantity=Quantity(drawn, entry.free.unit),
                )
            )

        if still_needed > NOTHING:
            _record(
                missing, requirement.ingredient_id, Quantity(still_needed, wanted.unit), density
            )

    return Provisioning(draws=draws, shortfall=missing)


def _record(
    missing: list[Shortfall],
    ingredient_id: int,
    amount: Quantity,
    density: Decimal | None,
) -> None:
    """Add to the shopping list, folding into an existing line where the units allow.

    One line for flour rather than one per meal (FR-7): a cook in a shop wants to know how
    much to buy, not how the week decomposes. Two eggs and 200 g of egg have no sum, so
    they get two lines — honest, where one would be a number somebody has to unpick.
    """
    for position, line in enumerate(missing):
        if line.ingredient_id != ingredient_id:
            continue
        combined = _add(line.quantity, amount, density)
        if combined is not None:
            missing[position] = Shortfall(ingredient_id=ingredient_id, quantity=combined)
            return
    missing.append(Shortfall(ingredient_id=ingredient_id, quantity=amount))


def outstanding(
    requirements: Sequence[Requirement],
    covered: Sequence[Covered],
    densities: Mapping[int, Decimal | None],
) -> list[Shortfall]:
    """What is still to buy, given what the plan is already holding aside (UC-4.4).

    The shopping list as read rather than as computed: `net` decides what to reserve, and
    this reports the remainder from the reservations that were actually made. Working it
    out from the availability a second time would be a second answer to the same
    question, and FR-7 is the promise that there is only one.

    Aggregation is shared with `net`, so a list read after planning has the same shape as
    the one planning produced.
    """
    held: dict[tuple[int, int], list[Quantity]] = {}
    for entry in covered:
        held.setdefault((entry.plan_slot_id, entry.ingredient_id), []).append(entry.quantity)

    missing: list[Shortfall] = []
    for requirement in requirements:
        wanted = requirement.quantity
        if wanted is None:
            continue
        density = densities.get(requirement.ingredient_id)
        still_needed = wanted.magnitude
        for amount in held.get((requirement.plan_slot_id, requirement.ingredient_id), []):
            in_our_terms = _converted(amount, wanted.unit, density)
            if in_our_terms is not None:
                still_needed -= in_our_terms.magnitude
        if still_needed > NOTHING:
            _record(
                missing, requirement.ingredient_id, Quantity(still_needed, wanted.unit), density
            )
    return missing
