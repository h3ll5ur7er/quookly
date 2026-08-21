"""Turning a recipe into something a standing, distracted human can follow (V15).

Execution guidance is a different question from interpretation. Interpretation asks *what
is this recipe*; execution asks *how does a person get through it* — what to prep before
starting, what order the steps go in, where the timers belong, and how long the whole
thing will take.

A rule engine: everything arrives as an argument. Which means every judgement here is a
table of cases rather than a fixture, and there is nothing to mock.

**Built** so far: the two times a recipe takes (UC-2.6, FR-23,
[ADR-037](../../../doc/07-decisions.md)). Mise-en-place grouping, step ordering and timer
specifications join it with cooking mode.
"""

from collections.abc import Sequence

from quookly.contracts.execution import Attention, Span, Timing
from quookly.contracts.recipe import Step


class _Running:
    """One of the three numbers, being added up.

    A class rather than a pair of locals because "seconds so far, and whether anything
    declined to say" travels together everywhere it goes, and splitting them is how one
    of them gets forgotten.
    """

    def __init__(self) -> None:
        self.seconds = 0
        self.silent = False

    def add(self, duration: int | None) -> None:
        if duration is None:
            self.silent = True
        else:
            self.seconds += duration

    def settled(self) -> Span | None:
        # Nothing to report either way: no steps of this kind, or none that said how long.
        # Both are "nobody said", and the difference is not one a screen can act on.
        return None if self.seconds == 0 else Span(self.seconds, at_least=self.silent)


def timing(steps: Sequence[Step]) -> Timing | None:
    """The two times this recipe takes, and its lead, or nothing where it does not say.

    **Sequential, deliberately.** Overlap is real — while the oven heats you make the
    batter — but a written recipe does not say which steps overlap, and inferring it from
    prose would make the total *shorter* than the truth. That is the one direction that
    makes somebody late. A cook who wants the overlap counted writes it as one step, which
    is how they would say it out loud anyway.
    """
    hands_on, total, ahead = _Running(), _Running(), _Running()
    for step in steps:
        match step.attention:
            case Attention.HANDS_ON:
                hands_on.add(step.duration_seconds)
                total.add(step.duration_seconds)
            case Attention.WAITING:
                total.add(step.duration_seconds)
            case Attention.AHEAD:
                ahead.add(step.duration_seconds)

    settled = Timing(hands_on=hands_on.settled(), total=total.settled(), ahead=ahead.settled())
    # A recipe that says nothing about time says nothing, rather than three absences
    # dressed up as an answer.
    if settled.hands_on is None and settled.total is None and settled.ahead is None:
        return None
    return settled
