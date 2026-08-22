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
#: closing bracket. Bounding the shape took that from four times in five to something like
#: one in ten, and each further ask divides it again. Two, because one still let a live run
#: fail; each retry costs a few seconds and only in the case that was already failing.
#:
#: Retrying is right *here* and would be wrong in `read_prose`: the same page should yield
#: the same recipe twice, and a silent re-read would be a second opinion nobody asked for.
#: It works at all because the asking is not deterministic — the same question asked again
#: is genuinely a different attempt.
ANOTHER_GO = 2

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
    return await _ask_for_one(
        _asked_for(description, ingredients, constraints, serves), _INSTRUCTIONS
    )


async def _ask_for_one(asked: str, instructions: str) -> InterpretedRecipe:
    """Ask once, and once more if the answer runs away with itself.

    Shared by writing a recipe and adapting one: the two differ in what they ask and in
    nothing else, which is the point of the engine.
    """
    for attempt in range(ANOTHER_GO + 1):
        try:
            answer, _ = await model.complete_structured(
                asked,
                RECIPE_SHAPE,
                system=instructions,
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


_VARYING = """You are adapting a recipe a cook already has, to a change they asked for.

Change what the change requires and leave the rest alone. A dairy-free shortbread is still
shortbread: the same shape, the same method, the same amounts wherever they still work. A
version that quietly becomes a different dish has not answered the question.

Where an ingredient has to go, put something in its place that does the same job, and adjust
the amount if the substitute behaves differently. Where a step depended on what was removed,
rewrite that step and only that step.

Everything else about writing a recipe still holds: real metric quantities, plain ingredient
names, one or two plain sentences a step, and a yield the recipe states itself.

Give the new recipe a name a cook would recognise as a version of the original."""


def _as_written(title: str, made: str, lines: Sequence[str], steps: Sequence[str]) -> str:
    """The original, written out the way a cookbook would print it.

    As text rather than as JSON, because a model adapts a recipe better when it is reading a
    recipe than when it is reading a data structure — and because the answer comes back in
    the shape, so the question does not have to.
    """
    return "\n".join(
        [
            f"{title}",
            f"Makes: {made}",
            "",
            "Ingredients:",
            *(f"- {line}" for line in lines),
            "",
            "Method:",
            *(f"{position}. {step}" for position, step in enumerate(steps, start=1)),
        ]
    )


async def vary(
    *,
    title: str,
    made: str,
    lines: Sequence[str],
    steps: Sequence[str],
    change: str,
    constraints: Sequence[str] = (),
) -> InterpretedRecipe:
    """Ask for a version of a recipe the cook already has (UC-1.7).

    The same shape back, the same reader, and the same refusal when nothing usable arrives.
    What differs from writing one outright is only what is asked — which is the whole of
    what this engine is for.
    """
    asked = [
        _as_written(title, made, lines, steps),
        "",
        f"Change asked for: {change}",
    ]
    if constraints:
        asked.append("It must also not contain: " + ", ".join(constraints) + ".")

    return await _ask_for_one("\n".join(asked), _VARYING)
