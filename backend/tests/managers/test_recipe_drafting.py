"""Turning a recipe a model read into one that can be stored.

The one thing tested here that is not bookkeeping: link syntax does not survive the trip.
Generating, varying and importing all pass through `_draft_from`, so this is the single
place where a model's words become a cook's recipe (ADR-059).
"""

from decimal import Decimal

from quookly.contracts.interpretation import (
    InterpretedLine,
    InterpretedRecipe,
    InterpretedStep,
    Source,
)
from quookly.contracts.measure import Unit
from quookly.contracts.recipe import Provenance
from quookly.managers.recipe import _draft_from


def _read(*instructions: str) -> InterpretedRecipe:
    return InterpretedRecipe(
        title="Pancakes",
        source=Source.MODEL,
        yield_magnitude=Decimal("12"),
        yield_unit=Unit.PIECE,
        lines=[InterpretedLine(ingredient="plain flour")],
        steps=[InterpretedStep(instruction=one) for one in instructions],
    )


def _drafted(*instructions: str) -> list[str]:
    draft = _draft_from(_read(*instructions), {"plain flour": 1}, Provenance.GENERATED)
    return [step.instruction for step in draft.steps]


class TestAModelCannotWriteALink:
    def test_a_link_it_wrote_is_not_stored(self) -> None:
        assert _drafted("Sift the [[plain-flour|flour]] in.") == ["Sift the flour in."]

    def test_the_words_are_kept(self) -> None:
        """Stripped, not refused: a model that emits the syntax still yields a usable step."""
        assert _drafted("Now [[blanch]] the beans.") == ["Now blanch the beans."]

    def test_ordinary_prose_is_untouched(self) -> None:
        assert _drafted("Rest the batter.") == ["Rest the batter."]
