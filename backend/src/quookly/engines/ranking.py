"""Which recipe to suggest, and why (V10, UC-3.3, UC-3.4).

A rule engine: candidates arrive as counts and nothing is fetched, so the whole ordering
policy is a table of cases.

The judgement it encodes is small and worth stating plainly. **A suggestion earns its place
by saving something.** Food about to go off is the thing this product exists to reduce, so a
recipe that uses some comes before one the cook merely happens to have the ingredients for —
and both come before one that means a trip to the shop. Where a cook has *asked* something,
the answer to their question comes first and this policy breaks the ties.

Nothing here hides a recipe. A dish somebody at the table cannot eat is ranked last and says
so; leaving it out would be the interface deciding something about an allergy on the cook's
behalf, which is what ADR-010 forbids.
"""

from collections.abc import Sequence
from decimal import Decimal

from quookly.contracts.discovery import Candidate, Ranked, Reason

#: How much of a recipe has to be in the cupboard before "you have most of it" is a claim
#: worth making. Below this it is a shopping list, and saying so would be flattery.
MOST = Decimal("0.75")

#: What each thing that needs eating is worth, against a whole recipe's worth of coverage.
#: One pressing ingredient outweighs any amount of convenience, which is the point: a full
#: cupboard is not a reason to cook, and a wilting bunch of spinach is.
PRESSING = Decimal(10)

#: What being unsuitable costs. Large enough that nothing outranks it, so a recipe somebody
#: cannot eat is always at the bottom rather than merely low down.
UNSUITABLE = Decimal(1000)


def _coverage(candidate: Candidate) -> Decimal:
    """How much of this recipe is already in the kitchen, as a proportion.

    A proportion rather than a count, so a big recipe is not punished for being big: ten
    ingredients of twelve is a better answer than two of two, which is a cup of tea.
    """
    if candidate.needs <= 0:
        return Decimal(0)
    return Decimal(candidate.have) / Decimal(candidate.needs)


def _score(candidate: Candidate) -> tuple[Decimal, Decimal, Decimal, int]:
    """What decides the order. Smallest first, so every part is written to be minimised.

    Four parts rather than one number, because they are not commensurable and pretending
    otherwise is how a weighting becomes impossible to reason about. Suitability outranks
    everything, an answer to what the cook asked outranks a suggestion they did not, and
    usefulness settles the rest.

    The recipe's own id is last and is only a tiebreak. Without it the answer would depend
    on how rows happened to arrive, and the same question would get two answers.
    """
    return (
        UNSUITABLE if candidate.suitable is False else Decimal(0),
        -(candidate.relevance or Decimal(0)),
        -(len(candidate.pressing) * PRESSING + _coverage(candidate)),
        candidate.recipe_id,
    )


def _reasons(candidate: Candidate) -> list[Reason]:
    """What to tell the cook. A list that only reordered itself would be asking to be
    trusted rather than earning it."""
    reasons = []
    if candidate.pressing:
        reasons.append(Reason.USES_SOON)
    if candidate.needs > 0:
        if candidate.have >= candidate.needs:
            reasons.append(Reason.HAVE_EVERYTHING)
        elif _coverage(candidate) >= MOST:
            reasons.append(Reason.HAVE_MOST)
    if candidate.suitable is False:
        reasons.append(Reason.NOT_FOR_EVERYONE)
    return reasons


def rank(candidates: Sequence[Candidate]) -> list[Ranked]:
    """Order these recipes, and say why each is where it is."""
    ordered = sorted(candidates, key=_score)
    return [
        Ranked(
            recipe_id=candidate.recipe_id,
            reasons=_reasons(candidate),
            pressing=list(candidate.pressing),
            missing=max(candidate.needs - candidate.have, 0),
        )
        for candidate in ordered
    ]
