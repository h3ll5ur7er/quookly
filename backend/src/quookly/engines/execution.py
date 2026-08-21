"""Turning a recipe into something a standing, distracted human can follow (V15).

Execution guidance is a different question from interpretation. Interpretation asks *what
is this recipe*; execution asks *how does a person get through it* — what to prep before
starting, what order the steps go in, where the timers belong, and how long the whole
thing will take.

A rule engine: everything arrives as an argument. Which means every judgement here is a
table of cases rather than a fixture, and there is nothing to mock.

**It returns structure, never content.** Everything it says about lines it says as
positions in the recipe's own list. That is what keeps measurement out of here: an engine
that hands back indices cannot scale, convert or round anything, so V4 stays in one place
by construction rather than by a rule somebody has to remember.
"""

import re
from collections.abc import Sequence

from quookly.contracts.execution import (
    Attention,
    ExecutionPlan,
    PlannedStep,
    PrepGroup,
    Span,
    Timing,
)
from quookly.contracts.recipe import IngredientLine, Step


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


#: An ingredient's name, as a recipe would actually write it. English plurals are worth the
#: one character: a recipe says "beat the eggs" and the registry says "egg", and without
#: this every countable ingredient would go unmatched. A language whose plurals are not a
#: trailing letter simply gets fewer matches — which shows nothing, never the wrong thing.
_PLURAL = "e?s?"


def _mentions(instruction: str, name: str) -> bool:
    """Whether this instruction is talking about this ingredient.

    Word boundaries either side, so "a buttered pan" is not butter. That matters more than
    it sounds: the failure this rule has to avoid is not missing a mention, it is claiming
    one — a step pointing at an ingredient it does not use is a step a cook cannot trust.
    """
    return re.search(rf"\b{re.escape(name)}{_PLURAL}\b", instruction, re.IGNORECASE) is not None


def _head(name: str) -> str:
    """The word a cook would actually use: "plain flour" said out loud is "the flour"."""
    return name.rsplit(" ", 1)[-1]


def _named_by(instruction: str, lines: Sequence[IngredientLine]) -> list[int]:
    """The lines this step is talking about, or none where it cannot be sure.

    Full names first. Only where none matched is the shortened form tried, and only when
    exactly one line in *this recipe* answers to it — "the flour" is a clear reference in a
    recipe with one flour and an ambiguous one in a recipe with two. Ambiguity resolves to
    nothing, because showing a cook the wrong ingredient at the hob is worse than showing
    them none.
    """
    named = {
        position
        for position, line in enumerate(lines)
        if _mentions(instruction, line.ingredient.name)
    }

    shared: dict[str, list[int]] = {}
    for position, line in enumerate(lines):
        shared.setdefault(_head(line.ingredient.name).casefold(), []).append(position)

    for head, positions in shared.items():
        if len(positions) == 1 and _mentions(instruction, head):
            named.add(positions[0])

    return sorted(named)


def _mise_en_place(lines: Sequence[IngredientLine]) -> list[PrepGroup]:
    """Everything to have ready, gathered by the work it wants (UC-9.2).

    Grouped by preparation rather than left in written order, because that is how the work
    actually goes: all the chopping at once, with one board out. Groups keep the order the
    recipe introduced them in, so a cook meets them where they expect.

    What wants nothing doing comes last. The work is what takes the time and is worth
    starting on; weighing out flour is a moment, and putting it at the top would bury the
    part worth beginning.
    """
    grouped: dict[str, list[int]] = {}
    plain: list[int] = []
    for position, line in enumerate(lines):
        if line.preparation is None:
            plain.append(position)
        else:
            grouped.setdefault(line.preparation, []).append(position)

    groups = [PrepGroup(preparation=work, lines=positions) for work, positions in grouped.items()]
    if plain:
        groups.append(PrepGroup(preparation=None, lines=plain))
    return groups


def plan(lines: Sequence[IngredientLine], steps: Sequence[Step]) -> ExecutionPlan:
    """A recipe arranged for doing rather than for reading (UC-9.2, UC-9.3).

    Positions are the recipe's own throughout, so a cook told "step 4" finds step 4 and a
    session resumed on another device points at the same instruction.
    """
    planned = [
        PlannedStep(position=position, lines=_named_by(step.instruction, lines))
        for position, step in enumerate(steps)
    ]

    # The *leading* run only. A chilling step in the middle is not work for the day
    # before — you cannot chill dough you have not made, and lifting it to the front
    # would produce an order nobody could follow.
    lead = 0
    while lead < len(steps) and steps[lead].attention is Attention.AHEAD:
        lead += 1

    return ExecutionPlan(
        mise_en_place=_mise_en_place(lines),
        ahead=planned[:lead],
        steps=planned[lead:],
    )
