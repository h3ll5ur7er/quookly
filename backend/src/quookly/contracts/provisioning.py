"""Netting what a plan needs against what the kitchen already has (V8).

Three shapes: what is needed, what can be drawn from stock to cover it, and what is left
to buy. The shopping list is the third one — derived from the shortfall the netting
reports rather than computed a second way, so the two cannot come to disagree (FR-7).
"""

from dataclasses import dataclass, field

from quookly.contracts.measure import Quantity


@dataclass(frozen=True, slots=True)
class Requirement:
    """What one planned meal needs of one ingredient.

    `quantity` is absent for a line the cook judges themselves — salt to taste, oil for
    frying. Absent rather than zero, and it draws nothing and buys nothing: twice as much
    "to taste" is still "to taste", and putting it on a shopping list would be inventing
    an amount nobody wrote.
    """

    plan_slot_id: int
    ingredient_id: int
    quantity: Quantity | None = None


@dataclass(frozen=True, slots=True)
class Draw:
    """Some of one lot, marked to cover one meal's need for it.

    In the **lot's** own unit, because that is the unit a reservation is made in and the
    only one in which "how much of that packet is left" is answerable without arithmetic.
    """

    plan_slot_id: int
    stock_item_id: int
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class Covered:
    """How much of one meal's need for one ingredient is already held aside.

    What a `Draw` became once it was really reserved. The shopping list is worked out
    from these rather than from a second pass over the availability, so the list and the
    reservations cannot come to disagree about the same butter (FR-7).
    """

    plan_slot_id: int
    ingredient_id: int
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class Shortfall:
    """What has to be bought, per ingredient, across the whole plan."""

    ingredient_id: int
    quantity: Quantity


@dataclass(frozen=True, slots=True)
class Provisioning:
    """What the plan can take from the kitchen, and what it still needs.

    Both halves of one calculation. The shopping list is the shortfall — not a second
    pass over the requirements that could reach a different answer.
    """

    draws: list[Draw] = field(default_factory=list)
    shortfall: list[Shortfall] = field(default_factory=list)
