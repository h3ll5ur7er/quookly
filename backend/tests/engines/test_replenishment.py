"""Netting what a plan needs against what is already in the kitchen (V8, UC-4.4).

A rule engine: pure functions of their arguments, tested as a table of cases. Availability
and densities arrive as parameters, which is what makes this exhaustible without a
database.

Two behaviours carry most of the weight. Which lot gets drawn from decides whether food is
eaten before it spoils, which is most of why this product exists. And a shortfall that is
a hair off zero is a shopping list telling somebody to buy 0.0000001 g of flour.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.pantry import Availability, StockItem
from quookly.contracts.provisioning import Requirement
from quookly.engines import replenishment

FLOUR = 1
MILK = 2
EGG = 3

MONDAY = date(2026, 8, 24)
FRIDAY = date(2026, 8, 28)

#: Nothing here reads it; a lot has one, so the fixture carries one.
RECEIVED = datetime(2026, 8, 20, tzinfo=UTC)

#: Whole milk, grams per millilitre. Enough to make a mass/volume conversion real.
MILK_DENSITY = Decimal("1.03")


def lot(
    stock_item_id: int,
    ingredient_id: int,
    free: str,
    unit: Unit = Unit.GRAM,
    expires_on: date | None = None,
    held: str | None = None,
) -> Availability:
    """One lot on the shelf, and how much of it nothing has claimed."""
    return Availability(
        lot=StockItem(
            id=stock_item_id,
            cook_id=1,
            ingredient_id=ingredient_id,
            quantity=Quantity(Decimal(held or free), unit),
            expires_on=expires_on,
            note=None,
            received_at=RECEIVED,
        ),
        free=Quantity(Decimal(free), unit),
    )


def needs(
    ingredient_id: int, amount: str | None, unit: Unit = Unit.GRAM, slot: int = 10
) -> Requirement:
    return Requirement(
        plan_slot_id=slot,
        ingredient_id=ingredient_id,
        quantity=None if amount is None else Quantity(Decimal(amount), unit),
    )


def test_a_plan_that_needs_nothing_draws_nothing() -> None:
    provided = replenishment.net([], [], {})

    assert provided.draws == []
    assert provided.shortfall == []


def test_what_is_not_in_the_kitchen_goes_on_the_list() -> None:
    provided = replenishment.net([needs(FLOUR, "300")], [], {})

    assert provided.draws == []
    assert [(one.ingredient_id, one.quantity) for one in provided.shortfall] == [
        (FLOUR, Quantity(Decimal("300"), Unit.GRAM))
    ]


def test_what_is_in_the_kitchen_is_drawn_rather_than_bought() -> None:
    provided = replenishment.net([needs(FLOUR, "300")], [lot(1, FLOUR, "500")], {})

    assert [(one.stock_item_id, one.quantity) for one in provided.draws] == [
        (1, Quantity(Decimal("300"), Unit.GRAM))
    ]
    assert provided.shortfall == []


def test_a_half_covered_need_is_half_drawn_and_half_bought() -> None:
    provided = replenishment.net([needs(FLOUR, "500")], [lot(1, FLOUR, "200")], {})

    assert [one.quantity for one in provided.draws] == [Quantity(Decimal("200"), Unit.GRAM)]
    assert [one.quantity for one in provided.shortfall] == [Quantity(Decimal("300"), Unit.GRAM)]


def test_the_packet_going_off_first_is_the_one_used() -> None:
    """The whole point. A rule that reached for the freshest bag would leave the older one
    to be thrown away, which is the waste this product exists to reduce."""
    provided = replenishment.net(
        [needs(FLOUR, "300")],
        [lot(1, FLOUR, "500", expires_on=FRIDAY), lot(2, FLOUR, "500", expires_on=MONDAY)],
        {},
    )

    assert [one.stock_item_id for one in provided.draws] == [2]


def test_a_packet_with_no_date_is_reached_for_last() -> None:
    """It cannot go off, so it is the one that can wait."""
    provided = replenishment.net(
        [needs(FLOUR, "600")],
        [lot(1, FLOUR, "500"), lot(2, FLOUR, "500", expires_on=FRIDAY)],
        {},
    )

    assert [(one.stock_item_id, one.quantity.magnitude) for one in provided.draws] == [
        (2, Decimal("500")),
        (1, Decimal("100")),
    ]


def test_between_equal_dates_the_straggler_is_finished_first() -> None:
    """Two undated bags, one nearly empty. Using the small one up leaves one open packet
    instead of two, which is how half-used bags stop accumulating."""
    provided = replenishment.net(
        [needs(FLOUR, "300")],
        [lot(1, FLOUR, "500"), lot(2, FLOUR, "100")],
        {},
    )

    assert [(one.stock_item_id, one.quantity.magnitude) for one in provided.draws] == [
        (2, Decimal("100")),
        (1, Decimal("200")),
    ]


def test_a_lot_in_another_unit_still_counts() -> None:
    """A kilo bag covers a 300 g need. The draw is expressed in the bag's own unit,
    because that is the unit the reservation is made in."""
    provided = replenishment.net(
        [needs(FLOUR, "300")], [lot(1, FLOUR, "1", unit=Unit.KILOGRAM)], {}
    )

    assert [one.quantity for one in provided.draws] == [Quantity(Decimal("0.3"), Unit.KILOGRAM)]
    assert provided.shortfall == []


def test_mass_covers_a_volume_where_a_density_is_known() -> None:
    provided = replenishment.net(
        [needs(MILK, "200", unit=Unit.MILLILITRE)],
        [lot(1, MILK, "500")],
        {MILK: MILK_DENSITY},
    )

    assert [one.stock_item_id for one in provided.draws] == [1]
    assert provided.draws[0].quantity.unit is Unit.GRAM
    assert provided.draws[0].quantity.magnitude == pytest.approx(Decimal("206"))
    assert provided.shortfall == []


def test_without_a_density_the_lot_simply_cannot_help() -> None:
    """Not an error. The milk is there; nothing here can say how much of it 200 ml is,
    and assuming water would misweigh it. It goes on the list instead."""
    provided = replenishment.net(
        [needs(MILK, "200", unit=Unit.MILLILITRE)], [lot(1, MILK, "500")], {MILK: None}
    )

    assert provided.draws == []
    assert [one.quantity for one in provided.shortfall] == [
        Quantity(Decimal("200"), Unit.MILLILITRE)
    ]


def test_a_count_and_a_mass_do_not_correspond() -> None:
    provided = replenishment.net(
        [needs(EGG, "2", unit=Unit.PIECE)], [lot(1, EGG, "300")], {EGG: None}
    )

    assert provided.draws == []
    assert [one.quantity.unit for one in provided.shortfall] == [Unit.PIECE]


def test_a_line_with_no_quantity_draws_nothing_and_buys_nothing() -> None:
    """Salt to taste. Twice as much to taste is still to taste, and putting a number on a
    shopping list would be inventing an amount nobody wrote."""
    provided = replenishment.net([needs(FLOUR, None)], [lot(1, FLOUR, "500")], {})

    assert provided.draws == []
    assert provided.shortfall == []


def test_two_meals_do_not_both_get_the_same_flour() -> None:
    provided = replenishment.net(
        [needs(FLOUR, "300", slot=10), needs(FLOUR, "300", slot=11)],
        [lot(1, FLOUR, "500")],
        {},
    )

    assert [(one.plan_slot_id, one.quantity.magnitude) for one in provided.draws] == [
        (10, Decimal("300")),
        (11, Decimal("200")),
    ]
    assert [one.quantity for one in provided.shortfall] == [Quantity(Decimal("100"), Unit.GRAM)]


def test_the_list_is_aggregated_per_ingredient_across_the_plan() -> None:
    """One line for flour, not one per meal (FR-7). A cook standing in a shop wants to
    know how much flour to buy, not how the week decomposes."""
    provided = replenishment.net(
        [needs(FLOUR, "300", slot=10), needs(FLOUR, "200", slot=11)], [], {}
    )

    assert [(one.ingredient_id, one.quantity) for one in provided.shortfall] == [
        (FLOUR, Quantity(Decimal("500"), Unit.GRAM))
    ]


def test_a_list_in_two_units_is_added_up_in_the_first_one_asked_for() -> None:
    provided = replenishment.net(
        [needs(FLOUR, "300", slot=10), needs(FLOUR, "1", unit=Unit.KILOGRAM, slot=11)], [], {}
    )

    assert [one.quantity for one in provided.shortfall] == [Quantity(Decimal("1300"), Unit.GRAM)]


def test_a_need_that_cannot_be_added_to_the_rest_gets_its_own_line() -> None:
    """Two eggs and 200 g of egg have no sum. Two lines is honest; one would be a number
    somebody has to unpick in a shop."""
    provided = replenishment.net(
        [needs(EGG, "2", unit=Unit.PIECE, slot=10), needs(EGG, "200", slot=11)], [], {EGG: None}
    )

    assert [one.quantity for one in provided.shortfall] == [
        Quantity(Decimal("2"), Unit.PIECE),
        Quantity(Decimal("200"), Unit.GRAM),
    ]


def test_a_draw_never_asks_for_more_of_a_lot_than_is_going_spare() -> None:
    """Converting there and back can land a hair over. A reservation for more than is
    free is refused outright, so a rounding artefact would fail the whole plan."""
    provided = replenishment.net(
        [needs(MILK, "500", unit=Unit.MILLILITRE)],
        [lot(1, MILK, "515", expires_on=MONDAY)],
        {MILK: MILK_DENSITY},
    )

    assert provided.draws[0].quantity.magnitude <= Decimal("515")


def test_stock_that_exactly_covers_a_need_leaves_nothing_to_buy() -> None:
    """Across a conversion, where the arithmetic does not terminate. A shortfall of
    0.0000000001 g reads as "buy more flour" and is the kind of thing nobody notices
    until it is on a shopping list."""
    provided = replenishment.net(
        [needs(MILK, "300", unit=Unit.MILLILITRE)],
        [lot(1, MILK, "103", expires_on=MONDAY), lot(2, MILK, "206", expires_on=FRIDAY)],
        {MILK: MILK_DENSITY},
    )

    assert provided.shortfall == []


def test_the_same_question_gets_the_same_answer_twice() -> None:
    """Draws are attributed to reservations that are then really made. An order that
    shifted between calls would make a plan unrepeatable."""
    requirements = [needs(FLOUR, "400", slot=10), needs(FLOUR, "300", slot=11)]
    shelf = [lot(1, FLOUR, "500"), lot(2, FLOUR, "500", expires_on=MONDAY)]

    first = replenishment.net(requirements, shelf, {})
    again = replenishment.net(requirements, shelf, {})

    assert first == again
