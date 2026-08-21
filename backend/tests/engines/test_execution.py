"""How long a recipe takes (V15, UC-2.6, FR-23, ADR-037).

A rule engine: steps arrive as arguments, so every case here is a table row rather than a
fixture. The cases that matter are the ones about absence — a step with no duration must
not contribute zero, because zero is a lie in the direction that makes every recipe look
quicker than it is.
"""

from quookly.contracts.execution import Attention, Span
from quookly.contracts.recipe import Step
from quookly.engines import execution


def step(
    seconds: int | None,
    attention: Attention = Attention.HANDS_ON,
    instruction: str = "Do the thing",
) -> Step:
    return Step(
        id=1,
        instruction=instruction,
        duration_seconds=seconds,
        temperature_celsius=None,
        attention=attention,
    )


def test_work_counts_towards_both_numbers() -> None:
    timing = execution.timing([step(300), step(600)])

    assert timing is not None
    assert timing.hands_on == Span(900, at_least=False)
    assert timing.total == Span(900, at_least=False)


def test_waiting_counts_towards_the_total_only() -> None:
    """The whole reason for two numbers. Bread is half an hour of work and a day of
    waiting, and either figure alone sends somebody to the wrong conclusion."""
    timing = execution.timing([step(600), step(5400, Attention.WAITING)])

    assert timing is not None
    assert timing.hands_on == Span(600, at_least=False)
    assert timing.total == Span(6000, at_least=False)


def test_work_done_in_advance_counts_towards_neither() -> None:
    timing = execution.timing([step(28800, Attention.AHEAD), step(600)])

    assert timing is not None
    assert timing.hands_on == Span(600, at_least=False)
    assert timing.total == Span(600, at_least=False)
    assert timing.ahead == Span(28800, at_least=False)


def test_nothing_is_done_in_advance_reads_as_absent() -> None:
    timing = execution.timing([step(600)])

    assert timing is not None
    assert timing.ahead is None


def test_an_untimed_step_makes_its_numbers_a_floor() -> None:
    """Not zero. A recipe of ten steps where one says nothing is *at least* what the
    other nine say, and reporting the sum as exact would be an invention."""
    timing = execution.timing([step(600), step(None)])

    assert timing is not None
    assert timing.hands_on == Span(600, at_least=True)
    assert timing.total == Span(600, at_least=True)


def test_an_untimed_wait_leaves_the_work_exact() -> None:
    """The two numbers are floors separately. A cook who knows the work is twenty minutes
    can decide to start; how long the oven takes is a different question."""
    timing = execution.timing([step(1200), step(None, Attention.WAITING)])

    assert timing is not None
    assert timing.hands_on == Span(1200, at_least=False)
    assert timing.total == Span(1200, at_least=True)


def test_a_recipe_that_says_nothing_about_time_says_nothing() -> None:
    """Absent, not "at least 0 min" — which reads as a fact and is not one."""
    assert execution.timing([step(None), step(None, Attention.WAITING)]) is None


def test_work_nobody_timed_is_absent_rather_than_zero() -> None:
    """Only the baking is timed. "At least 0 min hands-on" would tell a cook the cake
    makes itself."""
    timing = execution.timing([step(None), step(2700, Attention.WAITING)])

    assert timing is not None
    assert timing.hands_on is None
    assert timing.total == Span(2700, at_least=True)


def test_no_steps_at_all() -> None:
    assert execution.timing([]) is None


def test_a_step_says_hands_on_unless_it_says_otherwise() -> None:
    """The safe default (ADR-037): over-reporting the work is the failure that does not
    make anybody late for dinner."""
    assert step(600).attention is Attention.HANDS_ON
