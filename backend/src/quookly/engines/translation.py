"""Translating a recipe's prose (Phase 8b, ADR-032).

A capability engine, the same shape as `InterpretationEngine` pointed at a different
question. It knows what to ask and what shape an answer has to be, and nothing about
whether the answer is a *good* translation — that is the reader's judgement, and a
person's correction is the mechanism for it (ADR-064).

**Prose only.** Quantities, durations and temperatures are columns rendered per cook, and
ingredient names resolve through the registry per locale. None of that is sent, which is
what makes it impossible for a translation to change what a recipe asks for — and why no
verdict is affected: no verdict has ever consulted prose (ADR-006).
"""

from typing import Any

from quookly.access import model
from quookly.contracts.errors import NothingToTranslate
from quookly.contracts.translation import Translatable
from quookly.engines.matching import unlinked
from quookly.utilities.diagnostics import get_logger

log = get_logger("translation")

#: Room for a whole recipe's prose. As elsewhere, really a limit on how long a decoding
#: loop may run before it is called one.
ROOM_TO_TRANSLATE = 3000

#: Cool. This is not a writing task, and warmth here is a model improving the recipe.
FAITHFUL = 0.1

TRANSLATION_SHAPE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "steps"],
}

_INSTRUCTIONS = """You are translating a recipe. You are not writing one.

Translate the title, the summary and each step. Keep the steps in the same order and
return exactly as many as you were given — one translated step per step, even where two
would read better joined.

Leave every number exactly as it is: amounts, temperatures, times, tin sizes. They are
recorded separately by the application that will show this, and a converted number here
would sit beside the one it renders and disagree with it.

Leave ingredient names as the recipe writes them. They are resolved separately too.

Translate what the recipe says, including where it is clumsy. A clearer method is a
different recipe, and somebody wrote this one."""


async def render(original: Translatable, source: str, wanted: str) -> Translatable:
    """The same recipe's prose, in another language.

    Returns the original untouched where the two languages are the same, or where there is
    nothing to translate: both are answers, and neither is worth a round trip.

    Raises `NothingToTranslate` where the answer does not line up with what was sent — a
    missing title, or a different number of steps. A stored translation is paired back to
    the recipe by position, so an answer that does not line up cannot be stored at all.
    """
    if source == wanted or not original.steps:
        return original

    answer, _ = await model.complete_structured(
        _asked(original, source, wanted),
        TRANSLATION_SHAPE,
        system=_INSTRUCTIONS,
        max_tokens=ROOM_TO_TRANSLATE,
        temperature=FAITHFUL,
    )

    title = _said(answer.get("title"))
    steps = [_said(one) for one in answer.get("steps") or []]
    if not title or len(steps) != len(original.steps) or not all(steps):
        raise NothingToTranslate(
            f"the answer had {len(steps)} step(s) for a recipe with {len(original.steps)}"
        )

    return Translatable(title=title, summary=_said(answer.get("summary")) or None, steps=steps)


def _asked(original: Translatable, source: str, wanted: str) -> str:
    """The whole recipe in one prompt, rather than a step at a time.

    A step translated alone loses what the step before it established: *it* is the batter,
    and only the whole recipe says so. One round trip is also cheaper than eight.
    """
    lines = [f"Translate this recipe from {source} into {wanted}.", "", f"Title: {original.title}"]
    if original.summary:
        lines.append(f"Summary: {original.summary}")
    lines.append("")
    lines.append("Steps:")
    lines.extend(f"{position}. {step}" for position, step in enumerate(original.steps, start=1))
    return "\n".join(lines)


def _said(value: object) -> str:
    """One field, as text, with any link markup taken back out (ADR-059)."""
    return unlinked(value.strip()) if isinstance(value, str) else ""


#: A runaway guard, and deliberately not a test of whether the answer is a *name*.
#:
#: There is no such test. The shipped registry's own names run to 103 characters —
#: "yogurt substitute, soy-based. with fruit or flavour, with sugar, with calcium and
#: vitamins fortified" is a published row, not an explanation — so any length that would
#: reject a sentence would reject real food. This only catches an answer that has stopped
#: being one, and what actually keeps the answer short is the instruction and `max_tokens`.
LONGEST_NAME = 160

#: Room for a word. A limit on how long a decoding loop may run before it is called one.
ROOM_TO_NAME = 60

NAME_SHAPE: dict[str, Any] = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
}

_NAMING = """You are naming one food in another language.

Answer with the name a cook writes on a shopping list — nothing else. No article, no
explanation, no alternatives, no notes about regional usage.

If the food has no name in that language, give the name it is known by there, even where
that is the original word. A borrowed word is a real answer.

Singular or plural: keep whichever the given name uses."""


async def name_of(name: str, source: str, wanted: str) -> str:
    """One food's name in another language.

    A different question from `render`, and it needed asking differently. A recipe is prose
    and this is a **term**: an answer that reads as a sentence is a model that explained
    the food rather than naming it, and storing that would put a paragraph where a recipe
    line expects a word.

    Returns the name unchanged where the two languages are the same — a round trip to be
    told what a word already is.

    Raises `NothingToTranslate` where the answer is empty or has run away. Refusing is the
    right failure: an entry keeps the one name it has, and the reader falls back to it
    rather than to whatever came back.

    Note what is *not* checked: whether the answer is a name rather than a description.
    That cannot be told by length — the shipped registry has published names of a hundred
    characters — so the instruction is where it is asked for, and a wrong answer is
    correctable on the entry screen like any other.
    """
    if source == wanted or not name.strip():
        return name

    answer, _ = await model.complete_structured(
        f"Name this food in {wanted}. It is written here in {source}.\n\n{name}",
        NAME_SHAPE,
        system=_NAMING,
        max_tokens=ROOM_TO_NAME,
        temperature=FAITHFUL,
    )

    said = _said(answer.get("name"))
    if not said or len(said) > LONGEST_NAME:
        raise NothingToTranslate(f"the answer was not a name for {name!r}: {said!r}")
    return said
