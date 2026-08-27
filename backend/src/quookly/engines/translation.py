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
