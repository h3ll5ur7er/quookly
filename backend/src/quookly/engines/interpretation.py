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

from quookly.access import model
from quookly.contracts.errors import NotARecipe
from quookly.contracts.interpretation import (
    InterpretedLine,
    InterpretedRecipe,
    InterpretedStep,
    Source,
)
from quookly.contracts.measure import Unit
from quookly.contracts.web import ReadableContent

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
    # German, which is how a Swiss recipe site writes a spoonful. `TL` and `EL` are
    # Teelöffel and Esslöffel, and both are metric — this is the German-speaking world,
    # not the American one.
    "tl": Unit.TEASPOON_METRIC,
    "teelöffel": Unit.TEASPOON_METRIC,
    "el": Unit.TABLESPOON_METRIC,
    "esslöffel": Unit.TABLESPOON_METRIC,
    "gramm": Unit.GRAM,
    "kilogramm": Unit.KILOGRAM,
    "deziliter": Unit.DECILITRE,
    "stück": Unit.PIECE,
    "stk": Unit.PIECE,
    # French. The abbreviations "cs" and "cc" are left out deliberately: two letters that
    # common are as likely to be the start of an ingredient as a measure.
    # Listed in the plural too: French pluralises the first word — "cuillères à café" —
    # and the general "add an s at the end" rule cannot reach it.
    "cuillère à soupe": Unit.TABLESPOON_METRIC,
    "cuillères à soupe": Unit.TABLESPOON_METRIC,
    "cuillere à soupe": Unit.TABLESPOON_METRIC,
    "cuilleres à soupe": Unit.TABLESPOON_METRIC,
    "c. à s.": Unit.TABLESPOON_METRIC,
    "cuillère à café": Unit.TEASPOON_METRIC,
    "cuillères à café": Unit.TEASPOON_METRIC,
    "cuillere à café": Unit.TEASPOON_METRIC,
    "cuilleres à café": Unit.TEASPOON_METRIC,
    "c. à c.": Unit.TEASPOON_METRIC,
}

# Measures that are judgements rather than amounts, in each language Quookly reads. A
# pinch is a pinch whoever is pinching; turning one into grams would be a number a cook
# cannot see is wrong.
_VAGUE_UNITS = frozenset(
    {
        "pinch",
        "pinches",
        "knob",
        "handful",
        "dash",
        "splash",
        "drizzle",
        "prise",
        "prisen",
        "msp",
        "msp.",
        "messerspitze",
        "schuss",
        "handvoll",
        "bund",
        "päckchen",
        "päckli",
        "spritzer",
        "pincée",
        "pincee",
        "poignée",
        "poignee",
        "trait",
        "sachet",
        "filet",
    }
)

# Amounts that are judgements rather than measurements. V2 names this case by example —
# "a knob of butter" — and the honest reading keeps the words and refuses a number.
_VAGUE = ("knob", "pinch", "handful", "splash", "dash", "drizzle", "sprinkle", "glug")

# "a good pinch of salt", "a generous knob of butter" — the adjective is part of the
# hand-waving, not part of the ingredient.
_VAGUE_PATTERN = re.compile(
    rf"^(?P<amount>(?:a|an)\s+(?:\w+\s+)?(?:{'|'.join(_VAGUE)}))\s+of\s+(?P<name>.+)$",
    re.IGNORECASE,
)

# A trailing purpose. In an ingredient list "for frying" and "to serve" say what the
# ingredient is *for*, and belong with the note rather than in the ingredient's name —
# "butter for the pan" will never resolve against a registry, and "butter" will.
_PURPOSE = re.compile(
    r"^(?P<name>.+?)[,;]?\s+(?P<purpose>(?:for|to)\s+\w+(?:\s+\w+)?)$", re.IGNORECASE
)
_PURPOSE_WORDS = (
    "frying",
    "greasing",
    "dusting",
    "serving",
    "garnish",
    "drizzling",
    "brushing",
    "sprinkling",
    "taste",
    "serve",
    "finish",
    "decorate",
    "top",
    "the pan",
    "the tin",
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
    r"(?:s|es)?\b\.?\s*(?:of|de|d'|du|des)\s+(?P<rest>.*)$|"
    rf"^(?P<unit2>{'|'.join(sorted((re.escape(name) for name in _UNITS), key=len, reverse=True))})"
    r"(?:s|es)?\b\.?\s*(?P<rest2>.*)$",
    re.IGNORECASE,
)

# The same, for a measure that is a judgement: "1 Prise Salz", "2 pinches salt".
_VAGUE_UNIT_PATTERN = re.compile(
    r"^(?P<unit>"
    + "|".join(sorted((re.escape(name) for name in _VAGUE_UNITS), key=len, reverse=True))
    + r")"
    r"\b\.?\s*(?:of|de|d'|du|des)?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

_OPTIONAL = re.compile(
    r"[(\[]\s*optional\s*[)\]]|[,–—-]\s*optional\s*$|\s+\(optional\)", re.IGNORECASE
)

_WHITESPACE = re.compile(r"\s+")

#: A comma that separates a note from an ingredient, as opposed to one inside a number.
#: Half of Europe writes 2,5 where the other half writes 2.5.
_SEPARATING_COMMA = re.compile(r"(?<!\d),|,(?!\d)")

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
        name, purpose = _split_note(vague.group("name"))
        amount = vague.group("amount").strip()
        return InterpretedLine(
            ingredient=_tidy(name),
            preparation=f"{amount}, {purpose}" if purpose else amount,
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
    vague_unit = _VAGUE_UNIT_PATTERN.match(rest)
    if vague_unit and vague_unit.group("rest").strip():
        # "1 Prise Salz", "2 pinches salt". The measure is a judgement, so the line keeps
        # its words and refuses a number — in whatever language it was judged in.
        return InterpretedLine(
            ingredient=_tidy(vague_unit.group("rest")),
            preparation=f"{amount.group('amount').strip()} {vague_unit.group('unit')}".strip(),
            optional=optional,
            written=original,
        )

    unit_match = _UNIT_PATTERN.match(rest)

    if unit_match:
        matched = unit_match.group("unit") or unit_match.group("unit2")
        unit = _UNITS[matched.lower()]
        name = unit_match.group("rest") or unit_match.group("rest2") or ""
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
    the ingredient rather than the ingredient itself. A trailing purpose counts too, with
    or without the comma: "butter for the pan" is butter, and it is the only one of the
    two that will ever resolve against a registry.
    """
    # Not a comma between two digits. "2,5 dl Milch" is two and a half decilitres, and
    # splitting it here turned a quantity into "2" with a note reading "5 dl Milch".
    comma = _SEPARATING_COMMA.search(body)
    if comma:
        head, tail = body[: comma.start()], body[comma.end() :]
        if tail.strip():
            return head.strip(), _WHITESPACE.sub(" ", tail).strip()

    purpose = _PURPOSE.match(body.strip())
    if purpose and purpose.group("purpose").lower().split(maxsplit=1)[-1] in _PURPOSE_WORDS:
        return purpose.group("name").strip(), purpose.group("purpose").strip()
    return body, None


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
_PORTION_WORDS = (
    "serving",
    "servings",
    "portion",
    "portions",
    "person",
    "people",
    # German and French, because "4 Portionen" and "4 personnes" are how the sites a Swiss
    # cook reads say it (FR-10).
    "portionen",
    "personen",
    "personnes",
    "parts",
    "part",
)
_COUNTING_VERBS = ("makes", "yields", "gives", "ergibt", "ergeben", "donne")


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


# --- reading the prose ---------------------------------------------------------------
#
# The blog case: a thousand words of childhood memory around forty of recipe. This is the
# half that mediates a model, which makes this a *capability* engine rather than a rule
# engine. It is allowed to reach resource access; the import-linter contract names the
# rule engines explicitly so that stays a decision rather than a drift.

#: A page's text is long and a context window is not. An answer cut short by the token
#: limit is refused (ADR-026), so sending less beats being refused for sending too much.
#: Generous for a recipe page: the longest blog preamble is a few thousand words.
MOST_TEXT_SENT = 24_000

_INSTRUCTIONS = """You extract recipes from web pages.

Return only what the page actually says. Do not invent quantities, ingredients or steps,
and do not complete a recipe that is incomplete — a missing amount is better than an
invented one, because a cook cannot see that an invented one is wrong.

Write each ingredient the way a recipe lists it, not the way the article says it:
the amount, then the unit, then the ingredient, then any preparation after a comma.
"You will want 225g of plain flour, sifted if you can be bothered" becomes
"225g plain flour, sifted". Mark an ingredient the page calls optional by ending the
line with "(optional)". Where the page gives no amount, give none.

For recipe_yield, copy how the page says it — "Makes 8", "Serves 4" — or leave it empty if
it does not say. Leave narrative, advertising, comments and navigation out."""

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "recipe_yield": {"type": "string"},
        "ingredients": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    # `recipe_yield` is required so the model has to answer rather than omit the field.
    # An empty string means the page does not say, which is a different thing from not
    # having looked — and a recipe with no yield cannot be scaled to a household.
    "required": ["title", "recipe_yield", "ingredients", "steps"],
    "additionalProperties": False,
}


async def read_prose(content: ReadableContent) -> InterpretedRecipe:
    """Ask a model to find the recipe in a page's text.

    The model decides what is a recipe; the reader decides what a quantity means. It is
    asked for ingredient lines *as written*, and the same tested reader turns them into
    quantities — so there is one implementation of "what does 225g mean" rather than two
    that drift apart. It is also the easier question to ask: telling recipe from reminiscence
    is what a model is good at, and arithmetic is not.
    """
    text = content.text.strip()
    if not text:
        # Asking a model to read nothing produces an invented recipe, which is the one
        # outcome worse than an error.
        raise NotARecipe(f"there is nothing to read at {content.url}")

    answer, _ = await model.complete_structured(
        f"Read this page and extract the recipe.\n\n{text[:MOST_TEXT_SENT]}",
        _SCHEMA,
        system=_INSTRUCTIONS,
    )

    title = _tidy_prose(str(answer.get("title") or ""))
    written_lines = answer.get("ingredients") or []
    if not title or not isinstance(written_lines, list) or not written_lines:
        raise NotARecipe(f"no recipe was found at {content.url}")

    lines = [
        line
        for line in (read_ingredient(str(written)) for written in written_lines)
        if line is not None
    ]
    if not lines:
        raise NotARecipe(f"no recipe was found at {content.url}")

    magnitude, unit = read_yield(answer.get("recipe_yield"))
    return InterpretedRecipe(
        title=title,
        source=Source.MODEL,
        summary=_tidy_prose(str(answer.get("summary") or "")) or None,
        yield_magnitude=magnitude,
        yield_unit=unit,
        lines=lines,
        steps=_steps_from(answer.get("steps")),
    )


async def read_page(content: ReadableContent) -> InterpretedRecipe:
    """Read a fetched page, by whichever route it will give up a recipe (UC-1.3).

    Metadata first, always. It is better and it is free: the ingredient list is already a
    list, the steps are already in order, and nobody had to guess which paragraph was
    preamble. Spending a model round trip to get a worse answer would be a strange
    tradeoff (ADR-028).

    An instance with no model configured is not a broken instance. It cannot read a blog,
    and it can still import from every site that publishes its recipes properly — which,
    checked against live pages, is most of the large ones.
    """
    from_metadata = read_metadata(content.structured)
    if from_metadata is not None:
        return from_metadata
    return await read_prose(content)


# --- names a registry might know -----------------------------------------------------

# Words that say which one to buy rather than what it is. Dropping these turns "3 large
# free-range eggs" into eggs, which the registry knows and has classified.
#
# The list is deliberately timid, and stays that way. Dropping *any* adjective would make
# "coconut milk" resolve to milk — attaching a dairy allergen to a dairy-free ingredient
# and weighing it wrongly besides. "Whole", as in whole milk, is pointedly absent for the
# same reason: it looks like a size word and is not one.
_SHOPPING_WORDS = frozenset(
    {
        "large",
        "small",
        "medium",
        "extra",
        "free-range",
        "free",
        "range",
        "organic",
        "fresh",
        "ripe",
        "good",
        "good-quality",
        "best",
        "best-quality",
        "quality",
    }
)

# Enough of English plurals for a shopping list. A registry holds "egg"; recipes ask for
# eggs, tomatoes and cherries.
_PLURALS = (("ies", "y"), ("oes", "o"), ("ches", "ch"), ("shes", "sh"), ("s", ""))

# Words that end in s and are not plurals. Trying "molasse" would find nothing, which
# costs only a lookup — these are here so the singular is not offered *instead*.
_NOT_PLURAL = frozenset({"molasses", "asparagus", "couscous", "hummus", "watercress"})


def _singular(name: str) -> str | None:
    """The singular of a name, if it looks plural."""
    last = name.rsplit(maxsplit=1)[-1] if name.split() else name
    if last.lower() in _NOT_PLURAL or not last.lower().endswith("s"):
        return None
    for ending, replacement in _PLURALS:
        if last.lower().endswith(ending):
            singular = last[: -len(ending)] + replacement
            return name[: len(name) - len(last)] + singular
    return None


def candidate_names(written: str) -> list[str]:
    """Names to try against the registry, most specific first.

    The name as written always comes first: the registry may know the whole thing, and if
    it does that is the better match. What follows is the same name with shopping words
    removed and plurals reduced — so "3 large free-range eggs" reaches "egg" without
    "coconut milk" ever reaching "milk".

    A list rather than a single best guess, because *this* service does not know what the
    registry holds. Choosing among them is resolution's job; offering them is reading's.
    """
    name = _WHITESPACE.sub(" ", written).strip()
    if not name:
        return []

    offered: list[str] = []

    def offer(candidate: str) -> None:
        tidied = candidate.strip()
        if tidied and tidied not in offered:
            offered.append(tidied)

    offer(name)

    words = name.split()
    kept = [word for word in words if word.lower().strip(",") not in _SHOPPING_WORDS]
    if kept and len(kept) != len(words):
        offer(" ".join(kept))

    for candidate in list(offered):
        singular = _singular(candidate)
        if singular:
            offer(singular)

    return offered
