"""Asking a model what a word a recipe uses means (UC-7.4, ADR-062).

A capability engine, like `GenerationEngine`: it knows what to ask and what shape an
answer has to be, and nothing about whether the answer is true. That judgement belongs to
the person who approves the page, which is the whole of ADR-056.

**Techniques only.** A model may say what to do with your hands. It may not write about a
food: an ingredient page sits beside a panel of the registry's facts, and generated prose
next to computed facts is the one arrangement where a reader cannot tell which half was
checked (ADR-062). The manager refuses such a request; the instructions here are what stop
an answer drifting into one anyway.
"""

from typing import Any

from quookly.access import model
from quookly.contracts.academy import Wording
from quookly.contracts.errors import NothingToExplain
from quookly.engines.matching import unlinked
from quookly.utilities.diagnostics import get_logger

log = get_logger("explanation")

#: How much room one explanation gets. A paragraph, not an essay — and, as with a recipe,
#: really a limit on how long a decoding loop may run before it is called one.
ROOM_TO_EXPLAIN = 700

#: Warm enough to write a readable sentence, cool enough not to invent a technique.
PLAIN = 0.3

EXPLANATION_SHAPE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "spellings": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "explanation": {"type": "string"},
        "caution": {"type": "string"},
    },
    "required": ["name", "summary", "explanation"],
}

_INSTRUCTIONS = """You are writing one short encyclopedia entry for a cookery reference.

The reader is a cook who has met this word in a recipe and does not know it. Explain what
it means and how it is done, in two or three plain sentences. No preamble, no history, no
recipe.

The word is being used in a recipe, so read it that way: `fold` is a way of combining, not
what you do to laundry.

Write about the technique — what a cook does with their hands, and why. Do not write about
what any ingredient contains, and never mention allergens: those are recorded elsewhere in
this application and read from there, and a sentence here that disagrees with them is worse
than no sentence at all.

`name` is what this is called, on its own. `spellings` are the other forms a recipe step
might use — `folded in`, `folding` — and not near-synonyms for other techniques.

`caution` is only for where getting it wrong burns or poisons somebody. Leave it empty
otherwise: a warning on every entry is a warning on none."""


async def explain(term: str, locale: str) -> Wording:
    """One entry, in the reader's language.

    Raises `NothingToExplain` where the answer has no summary or no explanation — the two
    things without which there is no page, and the shape a model's refusal takes.
    """
    answer, _ = await model.complete_structured(
        f"The word is {term!r}. Write the entry in {locale}.",
        EXPLANATION_SHAPE,
        system=_INSTRUCTIONS,
        max_tokens=ROOM_TO_EXPLAIN,
        temperature=PLAIN,
    )

    summary = _said(answer.get("summary"))
    explanation = _said(answer.get("explanation"))
    if not summary or not explanation:
        raise NothingToExplain(term)

    name = _said(answer.get("name")) or term
    spellings = [
        spelling
        for raw in answer.get("spellings") or []
        if (spelling := _said(raw)) and spelling.casefold() != name.casefold()
    ]
    # The word that was asked about is always one, or the page would not answer to the
    # word that produced it — and the cook who asked would tap it again and be told nobody
    # has explained it.
    if term.casefold() not in {one.casefold() for one in [name, *spellings]}:
        spellings.append(term)

    return Wording(
        name=name,
        spellings=spellings,
        summary=summary,
        explanation=explanation,
        caution=_said(answer.get("caution")) or None,
    )


def _said(value: object) -> str:
    """One field, as text, with any link markup taken back out.

    Stripped rather than trusted: only a person may say a word means a particular page
    (ADR-059), and prose is exactly where a model would try.
    """
    return unlinked(value.strip()) if isinstance(value, str) else ""
