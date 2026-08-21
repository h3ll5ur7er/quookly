"""Turning what a page says into canonical structure (V2).

This is the product's core competence and the thing that will be refined indefinitely.
The rule underneath all of it: **a quantity that cannot be read is left absent.** A line
keeps its words and loses its number rather than acquiring a guessed one — a wrong number
is worse than a visible gap, because a cook cannot see that it is wrong.
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator
from decimal import Decimal, InvalidOperation
from typing import Any

from quookly.contracts.interpretation import (
    InterpretedLine,
    InterpretedRecipe,
    InterpretedStep,
    Source,
)
from quookly.contracts.measure import Unit

# What a unit is called in the wild, mapped to what Quookly means by it.
#
# One deliberate exception: **cup is read as the American one.** A US cup is 236.6ml and a
# metric cup is 250ml, a 6% error on everything measured that way — and "cup" is an
# American word in recipes. Reading it as the metric unit would be the quieter of two
# wrong answers rather than the right one. Everything else keeps the meaning Quookly
# already writes, where the regional difference is either nil or under two percent.
_UNITS: dict[str, Unit] = {
    "mg": Unit.MILLIGRAM,
    "milligram": Unit.MILLIGRAM,
    "g": Unit.GRAM,
    "gr": Unit.GRAM,
    "gram": Unit.GRAM,
    "gramme": Unit.GRAM,
    "kg": Unit.KILOGRAM,
    "kilo": Unit.KILOGRAM,
    "kilogram": Unit.KILOGRAM,
    "oz": Unit.OUNCE,
    "ounce": Unit.OUNCE,
    "lb": Unit.POUND,
    "pound": Unit.POUND,
    "ml": Unit.MILLILITRE,
    "millilitre": Unit.MILLILITRE,
    "milliliter": Unit.MILLILITRE,
    "cl": Unit.CENTILITRE,
    "centilitre": Unit.CENTILITRE,
    "dl": Unit.DECILITRE,
    "decilitre": Unit.DECILITRE,
    "l": Unit.LITRE,
    "litre": Unit.LITRE,
    "liter": Unit.LITRE,
    "tsp": Unit.TEASPOON_METRIC,
    "teaspoon": Unit.TEASPOON_METRIC,
    "tbsp": Unit.TABLESPOON_METRIC,
    "tbs": Unit.TABLESPOON_METRIC,
    "tablespoon": Unit.TABLESPOON_METRIC,
    "cup": Unit.CUP_US,
    "fl oz": Unit.FLUID_OUNCE_US,
    "fluid ounce": Unit.FLUID_OUNCE_US,
    "piece": Unit.PIECE,
}

# Amounts that are judgements rather than measurements. V2 names this case by example —
# "a knob of butter" — and the honest reading keeps the words and refuses a number.
_VAGUE = ("knob", "pinch", "handful", "splash", "dash", "drizzle", "sprinkle", "glug")

_VAGUE_PATTERN = re.compile(
    rf"^(?P<amount>(?:a|an)\s+(?:{'|'.join(_VAGUE)}))\s+of\s+(?P<name>.+)$",
    re.IGNORECASE,
)

# A leading amount: digits, a fraction, or both, optionally the low end of a range.
_AMOUNT = re.compile(
    # The bare fraction comes first: alternation is ordered, and "3" would otherwise win
    # against "3/4" and leave the denominator behind as part of the ingredient name.
    r"^\s*(?P<amount>\d+/\d+|\d+(?:[.,]\d+)?(?:\s+\d+/\d+)?)"
    r"\s*(?:(?:-|–|—|\s+to\s+)\s*\d+(?:[.,]\d+)?(?:\s+\d+/\d+)?)?"
    r"\s*(?P<rest>.*)$"
)

_UNIT_PATTERN = re.compile(
    rf"^(?P<unit>{'|'.join(sorted((re.escape(name) for name in _UNITS), key=len, reverse=True))})"
    r"(?:s|es)?\b\.?\s*(?:of\s+)?(?P<rest>.*)$",
    re.IGNORECASE,
)

_OPTIONAL = re.compile(r"[(\[]\s*optional\s*[)\]]|,\s*optional\s*$", re.IGNORECASE)

_WHITESPACE = re.compile(r"\s+")

#: U+2044, which is what NFKD decomposition of ½ and its relatives uses.
FRACTION_SLASH = "\u2044"


def _tidy(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip(" ,;:.-")


def _amount(text: str) -> Decimal | None:
    """Read a written amount: a decimal, a fraction, or a whole number and a fraction.

    Unicode fractions have already been expanded by the caller, so "1½" arrives as
    "1 1/2" and needs no special case here.
    """
    whole = Decimal(0)
    parts = text.replace(",", ".").split()
    try:
        for part in parts:
            if "/" in part:
                numerator, _, denominator = part.partition("/")
                whole += Decimal(numerator) / Decimal(denominator)
            else:
                whole += Decimal(part)
    except (InvalidOperation, ZeroDivisionError, ArithmeticError):
        return None
    return whole if whole > 0 else None


def _expand_fractions(text: str) -> str:
    """Turn ½ into 1/2, and 1½ into 1 1/2.

    Recipe sites use the typographic characters freely, and a reader that chokes on them
    would fail on a large share of real pages for a purely cosmetic reason.
    """
    expanded: list[str] = []
    for character in text:
        # NFKD turns ½ into "1⁄2" — with U+2044 FRACTION SLASH, not an ordinary slash.
        fraction = unicodedata.normalize("NFKD", character)
        if fraction != character and FRACTION_SLASH in fraction:
            # A digit immediately before it means a mixed number: "1½" is "1 1/2".
            if expanded and expanded[-1].isdigit():
                expanded.append(" ")
            expanded.append(fraction.replace(FRACTION_SLASH, "/"))
        else:
            expanded.append(character)
    return "".join(expanded)


def read_ingredient(written: str) -> InterpretedLine | None:
    """Read one ingredient line as a page wrote it.

    Returns `None` for a line with nothing in it. Everything else comes back as a line —
    an unreadable quantity is absent rather than fatal, because the ingredient is still
    worth having and the cook can supply the amount.
    """
    original = written.strip()
    if not original:
        return None

    body = _expand_fractions(original)
    optional = bool(_OPTIONAL.search(body))
    body = _tidy(_OPTIONAL.sub("", body))

    vague = _VAGUE_PATTERN.match(body)
    if vague:
        return InterpretedLine(
            ingredient=_tidy(vague.group("name")),
            preparation=vague.group("amount").strip(),
            optional=optional,
            written=original,
        )

    ingredient, preparation = _split_note(body)

    amount = _AMOUNT.match(ingredient)
    if not amount:
        return InterpretedLine(
            ingredient=_tidy(ingredient),
            preparation=preparation,
            optional=optional,
            written=original,
        )

    magnitude = _amount(amount.group("amount"))
    rest = amount.group("rest").strip()
    unit_match = _UNIT_PATTERN.match(rest)

    if unit_match:
        unit = _UNITS[unit_match.group("unit").lower()]
        name = unit_match.group("rest")
    elif _looks_like_a_unit(rest):
        # A number followed by a word that behaves like a unit but is not one Quookly
        # knows — "2 wineglasses of sherry". Guessing would be a wrong number; the line
        # keeps its words and loses its amount.
        return InterpretedLine(
            ingredient=_tidy(ingredient),
            preparation=preparation,
            optional=optional,
            written=original,
        )
    else:
        # A bare count: "3 large free-range eggs".
        unit = Unit.PIECE
        name = rest

    if magnitude is None:
        return InterpretedLine(
            ingredient=_tidy(ingredient),
            preparation=preparation,
            optional=optional,
            written=original,
        )

    return InterpretedLine(
        ingredient=_tidy(name) or _tidy(ingredient),
        magnitude=magnitude,
        unit=unit,
        preparation=preparation,
        optional=optional,
        written=original,
    )


def _looks_like_a_unit(rest: str) -> bool:
    """Whether what follows a number is a measure rather than the ingredient itself.

    "3 large eggs" counts eggs; "2 wineglasses of sherry" measures sherry in something
    unknown. The tell is `of`: a measure takes it and a count does not.
    """
    return bool(re.match(r"^\w+s?\s+of\s+", rest, re.IGNORECASE))


def _split_note(body: str) -> tuple[str, str | None]:
    """Separate a trailing note from the ingredient.

    "225g unsalted butter, softened" is butter, softened — the note describes this use of
    the ingredient rather than the ingredient itself.
    """
    head, separator, tail = body.partition(",")
    if not separator or not tail.strip():
        return body, None
    return head.strip(), _WHITESPACE.sub(" ", tail).strip()


# --- schema.org metadata ------------------------------------------------------------
#
# Checked against live pages, the major publishers embed one of these and it beats any
# reading of the surrounding article (ADR-028). The work here is not extraction so much as
# accommodation: sites agree on the vocabulary and disagree about almost every shape.

_MARKUP = re.compile(r"<[^>]+>")
_ISO_DURATION = re.compile(r"^P(?:T)?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?", re.IGNORECASE)

# A yield says how many of *something*. "Serves 4" and "4 servings" mean portions; "Makes
# 8 pancakes" means eight things. A bare number means portions — that is schema.org's own
# reading of `"recipeYield": "4"`, and what a site writing it means.
#
# "Makes 8", with no noun at all, is the ambiguous one, and it is read as eight *things*.
# The two mistakes are not equal. Calling portions "pieces" makes a recipe refuse to scale
# to a household, which a cook sees. Calling pieces "portions" makes it scale — silently,
# and wrongly, to a fraction of the batter.
_YIELD = re.compile(r"(?P<magnitude>\d+(?:[.,]\d+)?)\s*(?P<noun>[a-z]+)?", re.IGNORECASE)
_PORTION_WORDS = ("serving", "servings", "portion", "portions", "person", "people")
_COUNTING_VERBS = ("makes", "yields", "gives")


def _types(block: dict[str, Any]) -> list[str]:
    declared = block.get("@type") or []
    return [str(kind) for kind in (declared if isinstance(declared, list) else [declared])]


def _recipe_blocks(blocks: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Every Recipe in these blocks, including ones inside an `@graph`."""
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if "Recipe" in _types(block):
            yield block
        graph = block.get("@graph")
        if isinstance(graph, list):
            yield from _recipe_blocks(graph)


def _text_of(value: Any) -> str:
    """The readable text of an instruction, however the site chose to wrap it."""
    if isinstance(value, str):
        return _tidy_prose(value)
    if isinstance(value, dict):
        return _tidy_prose(str(value.get("text") or value.get("name") or ""))
    return ""


def _tidy_prose(text: str) -> str:
    """Strip embedded markup. Sites put tags in instruction text, and a cook reading a
    recipe should not be reading a `<b>`."""
    return _WHITESPACE.sub(" ", _MARKUP.sub("", text)).strip()


def _steps_from(value: Any) -> list[InterpretedStep]:
    """Flatten however the site expressed its method into an ordered list of steps."""
    if isinstance(value, str):
        # One block of prose with line breaks in it, which is how several sites do it.
        lines = [_tidy_prose(line) for line in value.splitlines()]
        return [InterpretedStep(instruction=line) for line in lines if line]

    if not isinstance(value, list):
        return []

    steps: list[InterpretedStep] = []
    for entry in value:
        if isinstance(entry, dict) and "HowToSection" in _types(entry):
            # A grouping — "for the batter", "to serve". The grouping is presentation;
            # the steps inside it are the method.
            steps.extend(_steps_from(entry.get("itemListElement") or []))
            continue
        text = _text_of(entry)
        if text:
            steps.append(InterpretedStep(instruction=text))
    return steps


def _seconds(duration: Any) -> int | None:
    """Read an ISO-8601 duration. Absent rather than guessed if it is prose."""
    if not isinstance(duration, str):
        return None
    match = _ISO_DURATION.match(duration.strip())
    if not match or not (match.group("hours") or match.group("minutes")):
        return None
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    return hours * 3600 + minutes * 60


def read_yield(written: Any) -> tuple[Decimal | None, Unit | None]:
    """How much a recipe makes, from the several ways sites write it.

    Absent rather than guessed when it cannot be read: a wrong yield misscales every
    quantity in the recipe, and it does it silently.
    """
    if isinstance(written, list):
        written = written[0] if written else None
    if isinstance(written, int | float | Decimal):
        return Decimal(str(written)), Unit.SERVING
    if not isinstance(written, str):
        return None, None

    match = _YIELD.search(written)
    if not match:
        return None, None
    try:
        magnitude = Decimal(match.group("magnitude").replace(",", "."))
    except InvalidOperation:
        return None, None

    noun = (match.group("noun") or "").lower()
    if noun in _PORTION_WORDS:
        return magnitude, Unit.SERVING
    if noun:
        # "Makes 8 pancakes" — eight things, not eight portions.
        return magnitude, Unit.PIECE
    if any(verb in written.lower() for verb in _COUNTING_VERBS):
        # "Makes 8", with nothing said about what. Eight of something.
        return magnitude, Unit.PIECE
    return magnitude, Unit.SERVING


def read_metadata(blocks: Iterable[dict[str, Any]]) -> InterpretedRecipe | None:
    """Read the first usable schema.org Recipe out of a page's metadata.

    `None` when there is none, or when the one there is cannot stand on its own. A block
    with no name cannot be listed or told apart from another; a block with no ingredients
    is an essay. Neither is worth storing as a recipe, and returning half of one would
    push the problem to a screen.
    """
    for block in _recipe_blocks(blocks):
        title = _tidy_prose(str(block.get("name") or ""))
        written_lines = block.get("recipeIngredient") or block.get("ingredients") or []
        if not title or not isinstance(written_lines, list):
            continue

        lines = [
            line
            for line in (read_ingredient(str(written)) for written in written_lines)
            if line is not None
        ]
        if not lines:
            continue

        steps = _steps_from(block.get("recipeInstructions"))
        duration = _seconds(block.get("cookTime")) or _seconds(block.get("totalTime"))
        if duration is not None and steps:
            # The site gave one time for the whole method and did not say which step it
            # belongs to. The last one is where a cook waits, and attaching it to the
            # first would start a timer before anything is in the pan.
            last = steps[-1]
            steps[-1] = InterpretedStep(
                instruction=last.instruction,
                duration_seconds=duration,
                temperature_celsius=last.temperature_celsius,
            )

        magnitude, unit = read_yield(block.get("recipeYield"))
        return InterpretedRecipe(
            title=title,
            source=Source.METADATA,
            summary=_tidy_prose(str(block.get("description") or "")) or None,
            yield_magnitude=magnitude,
            yield_unit=unit,
            lines=lines,
            steps=steps,
        )
    return None
