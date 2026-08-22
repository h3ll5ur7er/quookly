"""Asking for a recipe that does not exist yet (V1, V3, UC-1.4, UC-1.5).

A capability engine: it mediates one external capability and is allowed to reach resource
access for it. What it knows is **what to ask**; it never knows whom — the provider is
`ModelAccess`'s business and nothing here may name one (ADR-003, ADR-026).

It also never decides what an answer *means*. The shape that comes back is the same shape a
page's recipe comes back in, and `InterpretationEngine`'s tested reader turns "225 g plain
flour" into a quantity. One implementation of that, however the words arrived.

**It decides nothing about safety either.** Constraints are put into the prompt to improve
the odds, and the result is judged independently against its resolved ingredients
(ADR-006). A model asserting "this is dairy-free" carries no weight at all; the verdict
comes from the ingredient set, and the two are separate services precisely so the judgement
cannot be talked out of its conclusion.
"""

from collections.abc import Sequence

from quookly.access import model
from quookly.contracts.errors import StructuredOutputUnusable
from quookly.contracts.interpretation import InterpretedRecipe
from quookly.engines.interpretation import RECIPE_SHAPE, read_answer
from quookly.utilities.diagnostics import get_logger

log = get_logger("generation")

#: How much room one recipe gets.
#:
#: Deliberately tight. A real recipe comes back in about five hundred tokens and the longest
#: imaginable in far under this — so the budget is not really a budget, it is **how long a
#: decoding loop is allowed to run before it is called one**. Set to twelve thousand, a
#: looping answer costs forty seconds before anybody finds out; set here, a few.
ROOM_TO_WRITE = 2500

#: How many times to ask again when the answer runs away with itself.
#:
#: Guided decoding sometimes loops — the model fills an array and cannot find its way to the
#: closing bracket. Bounding the arrays took that from four times in five to about one in
#: five, and a second ask takes it to one in twenty-five. Asking again is right *here* and
#: would be wrong in `read_prose`: the same page should yield the same recipe twice, and a
#: silent re-read would be a second opinion nobody asked for.
ANOTHER_GO = 1

#: Not deterministic, unlike extraction. The same page should yield the same recipe twice —
#: that is what makes reading trustworthy. But a cook who asks twice for "a quick pasta" and
#: is handed the identical answer has been given a lookup table, not a suggestion.
IMAGINATIVE = 0.7

_INSTRUCTIONS = """You are writing a recipe for a home cook, to be followed at a hob.

Write it the way a good cookbook does: real quantities, ordinary equipment, and steps that
can be done one at a time. Say each step in one or two plain sentences.

Give every ingredient a written amount — "225 g plain flour", "2 eggs", "1 tbsp olive oil" —
in metric, and name the ingredient plainly. "Plain flour", not "high-quality organic
stone-ground flour". Say "salt, to taste" where an amount would be invented.

Say how much it makes, as the recipe's own yield: "Serves 4", "Makes 12".

For each step, say what it asks of the cook. "hands_on" is work — chopping, stirring,
shaping. "waiting" is time the food needs while the cook is around: baking, simmering,
resting. "ahead" is time that passes without the cook: proving overnight, soaking, chilling
for a day. A step that waits ends at the wait, so a timer belongs to it.

Write something a person would actually make. Do not invent an ingredient nobody sells."""


def _asked_for(
    description: str | None,
    ingredients: Sequence[str],
    constraints: Sequence[str],
    serves: int | None,
) -> str:
    """The request, in the words a cook put it in plus the facts they did not have to say.

    Ingredients are given as things to *use*, not as the only things allowed. A recipe
    constrained to five items and nothing else is a list, not a dish — the cook wants the
    spinach used up, not a meal of spinach.
    """
    asked = ["Write a recipe."]
    if description:
        asked.append(f"What the cook asked for: {description}")
    if ingredients:
        asked.append(
            "Use these, which the cook already has and wants to use up: "
            + ", ".join(ingredients)
            + ". Ordinary storecupboard things may be added."
        )
    if constraints:
        # In the prompt to improve the odds. The guarantee is the verdict afterwards.
        asked.append("It must not contain: " + ", ".join(constraints) + ". This is not negotiable.")
    if serves:
        asked.append(f"It should serve {serves}.")
    return "\n\n".join(asked)


async def compose(
    *,
    description: str | None = None,
    ingredients: Sequence[str] = (),
    constraints: Sequence[str] = (),
    serves: int | None = None,
) -> InterpretedRecipe:
    """Ask for a recipe, and read the answer as a recipe (UC-1.4, UC-1.5).

    Raises `NotARecipe` where the answer has no title or no ingredients — the two things
    without which there is nothing to store, and the shape a model's refusal takes.
    """
    asked = _asked_for(description, ingredients, constraints, serves)
    for attempt in range(ANOTHER_GO + 1):
        try:
            answer, _ = await model.complete_structured(
                asked,
                RECIPE_SHAPE,
                system=_INSTRUCTIONS,
                max_tokens=ROOM_TO_WRITE,
                temperature=IMAGINATIVE,
            )
        except StructuredOutputUnusable:
            # An answer that ran away with itself rather than a provider that is down. It
            # is worth asking again, and only this.
            if attempt == ANOTHER_GO:
                raise
            log.info("the answer ran away with itself; asking again")
            continue
        return read_answer(answer, "nothing usable came back")

    raise StructuredOutputUnusable("nothing usable came back")
