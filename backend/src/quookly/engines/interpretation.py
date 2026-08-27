"""Turning what a page says into canonical structure (V2).

This is the product's core competence and the thing that will be refined indefinitely.
The rule underneath all of it: **a quantity that cannot be read is left absent.** A line
keeps its words and loses its number rather than acquiring a guessed one — a wrong number
is worse than a visible gap, because a cook cannot see that it is wrong.
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any

from quookly.access import model
from quookly.contracts.errors import NotARecipe
from quookly.contracts.execution import Attention
from quookly.contracts.interpretation import (
    InterpretedLine,
    InterpretedRecipe,
    InterpretedStep,
    Source,
)
from quookly.contracts.measure import Unit
from quookly.contracts.web import ReadableContent
from quookly.utilities.diagnostics import get_logger

log = get_logger("interpretation")

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
#: The little word between a measure and what it measures, in each language Quookly reads.
#: The apostrophe is written both ways on purpose: a French page types "gousses d’ail" with
#: a typographic apostrophe, and a pattern that only knows the straight one leaves the
#: elision stuck to the ingredient — "d’ail" resolves against no registry, "ail" does.
_ELIDED = r"(?:of|de|d['’]|du|des|von)"

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

# Where an ingredient came from, which is the same kind of note read from the other end.
# "Broth from boiling the chicken" is broth; "juice from one lemon" is juice. Unlike a
# purpose this needs no word list — "from" is doing all the work, and what follows it is
# always provenance rather than part of the name.
_PROVENANCE = re.compile(r"^(?P<name>.+?)[,;]?\s+(?P<from>from\s+\S.*)$", re.IGNORECASE)
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
    rf"(?:s|es)?\b\.?\s*{_ELIDED}\s+(?P<rest>.*)$|"
    rf"^(?P<unit2>{'|'.join(sorted((re.escape(name) for name in _UNITS), key=len, reverse=True))})"
    r"(?:s|es)?\b\.?\s*(?P<rest2>.*)$",
    re.IGNORECASE,
)

# The same, for a measure that is a judgement: "1 Prise Salz", "2 pinches salt".
_VAGUE_UNIT_PATTERN = re.compile(
    r"^(?P<unit>"
    + "|".join(sorted((re.escape(name) for name in _VAGUE_UNITS), key=len, reverse=True))
    + r")"
    rf"\b\.?\s*{_ELIDED}?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

#: Doubled brackets, which at least one large site emits, and the mismatched pair one of
#: them publishes — "((… ) )". Collapsed before anything reads them, because a reader that
#: insisted on balance would put the whole apology in the ingredient's name.
_DOUBLED_BRACKETS = re.compile(r"\(\s*\(|\)\s*\)")

#: A note a page put in brackets. Taken out before commas are looked at: the note usually
#: contains one, and splitting there is what turned "neutral oil (such as vegetable,
#: canola, or avocado oil)" into an ingredient called "neutral oil (such as vegetable".
_BRACKETED = re.compile(r"[(\[]([^()\[\]]*)[)\]]")

#: Words for the shape a countable ingredient arrives in. Without these "4 cloves garlic"
#: is four of something called "cloves garlic" — and a name like that resolves against no
#: registry, so importing one recipe invents an ingredient nobody has heard of and nobody
#: has classified for allergens. That is a worse outcome than an unread quantity.
_COUNTING_WORDS = frozenset(
    {
        "clove",
        "cloves",
        "slice",
        "slices",
        "sprig",
        "sprigs",
        "stick",
        "sticks",
        "stalk",
        "stalks",
        "can",
        "cans",
        "tin",
        "tins",
        "jar",
        "jars",
        "packet",
        "packets",
        "bunch",
        "bunches",
        "head",
        "heads",
        "rasher",
        "rashers",
        "fillet",
        "fillets",
        "sheet",
        "sheets",
        "strip",
        "strips",
        "chunk",
        "chunks",
        "cube",
        "cubes",
        "bar",
        "bars",
        # German, which is how a Swiss page writes a clove of garlic.
        "zehe",
        "zehen",
        "scheibe",
        "scheiben",
        "stange",
        "stangen",
        "bund",
        "dose",
        "dosen",
        # French.
        "gousse",
        "gousses",
        "tranche",
        "tranches",
        "brin",
        "brins",
        "botte",
        "bottes",
    }
)

_COUNTING_PATTERN = re.compile(
    r"^(?P<counted>"
    + "|".join(sorted((re.escape(word) for word in _COUNTING_WORDS), key=len, reverse=True))
    + rf")\b\.?\s*{_ELIDED}?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

#: A number that measures a *length* rather than a count. "4-inch piece ginger" is one
#: piece of ginger four inches long; read as a count it is four gingers, which is nine
#: times the recipe. The recipe does not say how much that weighs, so nothing here invents
#: a figure — the length becomes the note and the amount stays absent.
_SIZE_PATTERN = re.compile(
    r"^[-–—]?\s*(?P<measure>inch|inches|in\.|\"|cm|centimetre|centimeter|mm)\b"
    r"\s*(?P<shape>piece|pieces|chunk|chunks|length|lengths|knob|stück|morceau)?\s*"
    rf"{_ELIDED}?\s*(?P<rest>.*)$",
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
    # Before the commas are looked at: a bracketed note usually contains one.
    body, aside = _bracketed(body)

    vague = _VAGUE_PATTERN.match(body)
    if vague:
        name, purpose = _split_note(vague.group("name"))
        amount = vague.group("amount").strip()
        return InterpretedLine(
            ingredient=_tidy(name),
            preparation=_joined(amount, purpose, aside),
            optional=optional,
            written=original,
        )

    ingredient, written_note = _split_note(body)
    preparation = _joined(written_note, aside)

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
            preparation=_joined(
                f"{amount.group('amount').strip()} {vague_unit.group('unit')}".strip(), preparation
            ),
            optional=optional,
            written=original,
        )

    size = _SIZE_PATTERN.match(rest)
    if size and size.group("rest").strip():
        # "4-inch piece ginger". The number is a length, and the recipe does not say what
        # that weighs — so the length becomes a note and the amount stays absent, rather
        # than the line claiming four gingers.
        measured = f"{amount.group('amount').strip()}-{size.group('measure')}"
        shape = size.group("shape")
        return InterpretedLine(
            ingredient=_tidy(size.group("rest")),
            preparation=_joined(f"{measured} {shape}".strip() if shape else measured, preparation),
            optional=optional,
            written=original,
        )

    counted = _COUNTING_PATTERN.match(rest)
    if counted and counted.group("rest").strip() and magnitude is not None:
        # "4 cloves garlic" is four of a thing, and the thing is garlic. Read as a name,
        # "cloves garlic" resolves against no registry and invents an ingredient.
        return InterpretedLine(
            ingredient=_tidy(counted.group("rest")),
            magnitude=magnitude,
            unit=Unit.PIECE,
            preparation=_joined(counted.group("counted").strip(), preparation),
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


def _bracketed(body: str) -> tuple[str, str | None]:
    """Take a page's bracketed asides out of the line, and hand them back as a note.

    Before commas are looked at, deliberately: a bracketed note usually contains one, and
    splitting there is what left an ingredient called "neutral oil ((such as vegetable".

    Several brackets on one line are joined rather than fought over. And a line that is
    *nothing but* a bracket keeps its words: emptying the name would lose the ingredient,
    which is the one thing importing must never do.
    """
    collapsed = _DOUBLED_BRACKETS.sub(lambda found: found.group()[0], body)
    notes = [found.strip() for found in _BRACKETED.findall(collapsed) if found.strip()]
    if not notes:
        return body, None

    without = _tidy(_BRACKETED.sub(" ", collapsed))
    if not without:
        return body, None
    return without, "; ".join(notes)


def _joined(*notes: str | None) -> str | None:
    """Every note this line carried, or nothing where it carried none."""
    kept = [note for note in notes if note]
    return ", ".join(kept) if kept else None


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

    provenance = _PROVENANCE.match(body.strip())
    if provenance:
        return provenance.group("name").strip(), provenance.group("from").strip()
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


def _attention(named: Any) -> Attention:
    """What the model said a step asks of the cook, or hands-on if it said nothing usable.

    Falling back rather than refusing. A step whose attention could not be read is still a
    step, and hands-on over-reports the work rather than under-reporting it — the failure
    that does not make anybody late.
    """
    try:
        return Attention(str(named))
    except ValueError:
        return Attention.HANDS_ON


def _steps_read(value: Any) -> list[InterpretedStep]:
    """The model's steps, each with what it asks of the cook.

    Separate from `_steps_from`, which flattens whatever shape a *site* chose. This reads
    one shape, because this end of the conversation is one we specified. Bare strings are
    still accepted: a model that ignores the shape it was given should cost a recipe its
    attention, not the whole import.
    """
    if not isinstance(value, list):
        return []

    steps: list[InterpretedStep] = []
    for entry in value:
        if isinstance(entry, str):
            text, attention = _tidy_prose(entry), Attention.HANDS_ON
        elif isinstance(entry, dict):
            text = _tidy_prose(str(entry.get("instruction") or ""))
            attention = _attention(entry.get("attention"))
        else:
            continue
        if text:
            steps.append(InterpretedStep(instruction=text, attention=attention))
    return steps


#: Words for a stretch of time, in the languages Quookly reads, and what one is worth in
#: seconds. Abbreviations included because a recipe writes "25 min" as often as "25
#: minutes"; "h" is left out, because a bare h after a number is as likely to be the start
#: of a word as an hour.
_TIME_WORDS: dict[str, int] = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "secs": 1,
    "sekunde": 1,
    "sekunden": 1,
    "seconde": 1,
    "secondes": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "mins": 60,
    "minuten": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "hrs": 3600,
    "stunde": 3600,
    "stunden": 3600,
    "heure": 3600,
    "heures": 3600,
}

#: How a recipe writes the far end of a range. Words as well as dashes: "2 to 3 minutes"
#: is at least as common as "2-3 minutes", and without the word the pattern reads the
#: *upper* end — which is the direction that burns things.
_RANGE = r"(?:[-–—]|to|or|bis|und|à|ou)"

#: A number — or the first end of a range — followed by a word for time. The range is what
#: makes this worth a pattern rather than a lookup: "25-30 minutes" is how every recipe
#: writes an oven, and the lower end is the one a timer should use.
_DURATION = re.compile(
    rf"(?P<amount>\d+(?:[.,]\d+)?)\s*(?:{_RANGE}\s*\d+(?:[.,]\d+)?\s*)?"
    rf"(?P<unit>{'|'.join(sorted(_TIME_WORDS, key=len, reverse=True))})\b",
    re.IGNORECASE,
)

#: A number followed by a degree marker. The marker is the whole of the test: without it
#: "200 g" and "1 cup" are temperatures, and a wrong oven is a ruined dinner. `Grad` is
#: how a German recipe writes it and is always Celsius.
_TEMPERATURE = re.compile(
    r"(?P<amount>\d{2,3})\s*(?:°\s*(?P<scale>[CF])\b|(?P<scale2>[CF])\b|grad\b)",
    re.IGNORECASE,
)


def _number(written: str) -> Decimal:
    return Decimal(written.replace(",", "."))


def read_step_timing(instruction: str) -> tuple[int | None, int | None]:
    """How long a step takes and how hot, read out of its own words.

    The same division of labour as everywhere else: a model decides what a step *says*,
    and this decides what a number in it *means*. Without it an imported recipe has no
    timers at all, which is the one thing a cook standing at a hob reaches for.

    Absent rather than guessed, in both. "Chop 5 onions" has a number in it and no
    duration; a five-second timer would be worse than none. A gas mark is a real oven
    setting and not a temperature, so it stays unread rather than becoming one.
    """
    seconds: int | None = None
    #: Summed across a run, so "1 hour 30 minutes" is not one hour. Only a run: a second
    #: duration further into the sentence belongs to a different action.
    at = 0
    for match in _DURATION.finditer(instruction):
        if seconds is not None and match.start() > at:
            break
        counted = int(_number(match.group("amount")) * _TIME_WORDS[match.group("unit").lower()])
        seconds = counted if seconds is None else seconds + counted
        at = match.end() + 1

    celsius: int | None = None
    hot = _TEMPERATURE.search(instruction)
    if hot is not None:
        scale = (hot.group("scale") or hot.group("scale2") or "C").upper()
        degrees = int(hot.group("amount"))
        # Every temperature in this system is Celsius. A cook with a European oven cannot
        # act on 350 °F, and the conversion is exact enough to round.
        celsius = degrees if scale == "C" else round((degrees - 32) * 5 / 9)

    return seconds, celsius


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


def read_serves(written: Any) -> Decimal | None:
    """How many people a recipe feeds, where its yield says something else.

    "Makes 12 pancakes (serves 4)" is two facts, and only the second lets the recipe be
    scaled to a table. Sites express the pair by putting both in `recipeYield`, usually as
    a list — `["12 pancakes", "4 servings"]` — and `read_yield` takes only the first, so
    this looks through the rest for one that reads as portions.

    Absent is the common case and a real answer. Nothing here invents a pieces-per-serving
    figure; a wrong one would misportion every meal planned from the recipe, silently.
    """
    candidates = written if isinstance(written, list) else [written]
    for candidate in candidates:
        magnitude, unit = read_yield(candidate)
        if unit is Unit.SERVING and magnitude is not None:
            return magnitude
    return None


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
                # `cookTime` is the site saying how long it is *in the oven*, which is
                # waiting by definition. Left as hands-on it would report ninety minutes
                # of work for a cake that is twenty (ADR-037).
                attention=Attention.WAITING,
            )

        magnitude, unit = read_yield(block.get("recipeYield"))
        return InterpretedRecipe(
            title=title,
            source=Source.METADATA,
            summary=_tidy_prose(str(block.get("description") or "")) or None,
            yield_magnitude=magnitude,
            yield_unit=unit,
            # Only where the yield says something else. A yield already in servings is
            # the answer, and carrying a second copy of it invites the two to disagree.
            serves=None if unit is Unit.SERVING else read_serves(block.get("recipeYield")),
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
it does not say.

For serves, give just the number of people the page says it feeds, when the page says that
separately from what it makes: "Makes 12 pancakes (serves 4)" is a recipe_yield of
"12 pancakes" and a serves of "4". Leave serves empty otherwise, including when
recipe_yield already counts portions. Leave narrative, advertising, comments and navigation
out."""

#: How long a list of ingredients or steps is allowed to get.
#:
#: A bound rather than a hope. Reading a page is bounded by the page — there is only so much
#: text — but *writing* one is bounded by nothing, and a schema with an open-ended array is
#: an invitation to a decoder to keep filling it. Asked to invent a recipe, this model looped
#: to the token limit four times in five until the arrays had an end.
#:
#: Forty is well past any real recipe and well short of a loop.
MOST_LINES = 40

#: How long any one string may get. The arrays were only half the problem: a decoder can
#: run away *inside* a value as readily as between them, and a summary with no end is an
#: end it cannot find. The limits match what `RecipeInput` accepts, so an answer that fills
#: one is still a recipe this instance can store.
MOST_TITLE = 200
MOST_SUMMARY = 1000
MOST_LINE = 200
MOST_STEP = 2000

#: The shape a recipe comes back in, whether it was read off a page or asked for from
#: nothing. One shape, because the reader that makes sense of it is one reader — and a
#: second spelling of "ingredients" would be a second set of parsing bugs.
RECIPE_SHAPE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": MOST_TITLE},
        "summary": {"type": "string", "maxLength": MOST_SUMMARY},
        "recipe_yield": {"type": "string", "maxLength": 100},
        "serves": {"type": "string", "maxLength": 100},
        "ingredients": {
            "type": "array",
            "items": {"type": "string", "maxLength": MOST_LINE},
            "minItems": 1,
            "maxItems": MOST_LINES,
        },
        # Plain strings. What a step *asks of the cook* is a question about steps, and
        # steps belong to the editing pass that runs after this — asking twice would be
        # two prompts answering one question, drifting apart at their own pace.
        "steps": {
            "type": "array",
            "items": {"type": "string", "maxLength": MOST_STEP},
            "maxItems": MOST_LINES,
        },
    },
    # `recipe_yield` and `serves` are required so the model has to answer rather than omit
    # the field. Empty means the page does not say, which is a different thing from not
    # having looked.
    "required": ["title", "recipe_yield", "serves", "ingredients", "steps"],
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
        RECIPE_SHAPE,
        system=_INSTRUCTIONS,
    )
    return read_answer(answer, f"no recipe was found at {content.url}")


def read_answer(answer: dict[str, Any], nothing_there: str) -> InterpretedRecipe:
    """Turn a model's filled-in shape into a recipe, or refuse it.

    Shared with `GenerationEngine`, which asks a different question and gets the same shape
    back. That is the whole of the division between them: generation knows *what to ask*,
    this knows what an answer means, and "what does 225g mean" has one implementation
    however the words arrived.
    """
    title = _tidy_prose(str(answer.get("title") or ""))
    written_lines = answer.get("ingredients") or []
    if not title or not isinstance(written_lines, list) or not written_lines:
        raise NotARecipe(nothing_there)

    lines = [
        line
        for line in (read_ingredient(str(written)) for written in written_lines)
        if line is not None
    ]
    if not lines:
        raise NotARecipe(nothing_there)

    magnitude, unit = read_yield(answer.get("recipe_yield"))
    return InterpretedRecipe(
        title=title,
        source=Source.MODEL,
        summary=_tidy_prose(str(answer.get("summary") or "")) or None,
        yield_magnitude=magnitude,
        yield_unit=unit,
        serves=None if unit is Unit.SERVING else read_serves(answer.get("serves")),
        lines=lines,
        steps=_steps_read(answer.get("steps")),
    )


_EDITING = """You are given the method of a recipe as a website wrote it. Rewrite it as
instructions somebody can follow standing at a hob with their hands full.

Say each step in one or two plain sentences. Full sentences with their articles, not notes:
"Sift the flour into a bowl", never "Sift flour into bowl". Cut restatement, encouragement
and asides — "the mixture will look dry and dusty at first, and a bit unpromising" is not an
instruction. Cut anything that is not an instruction at all: gathering the ingredients,
"enjoy", the author's memories, links, advertising, and notes about storing leftovers.

Split a step that covers several moments. A moment is what a cook does before they look back
at the screen: "Break the eggs into a bowl and tip in the sugar" is one. "Melt the butter,
leave it to cool, then heat the oven" is three, because waiting comes between them. Do not
split every verb — two actions at the same bowl are one step.

**A step that waits ends at the wait.** "Pour in the batter and cook for two minutes" is
two steps: pouring, then cooking for two minutes. That is what gives the waiting a timer of
its own.

Keep every detail that changes the result, in the step it belongs to: times, temperatures,
quantities the step names, doneness cues such as "until the edges set", and warnings such as
"do not overmix". It is better to leave a step long than to lose one of these.

Keep the original order, use the imperative, and stay in the language the recipe is written
in. Do not invent anything the original did not say.

For each step, say what it asks of the cook. "hands_on" is work — chopping, stirring,
shaping. "waiting" is time the food needs while the cook is around: baking, simmering,
resting. "ahead" is time that passes without the cook: proving overnight, soaking, chilling
for a day. When a step is both, call it hands_on."""

_EDITING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "instruction": {"type": "string"},
                    "attention": {
                        "type": "string",
                        "enum": [level.value for level in Attention],
                    },
                },
                "required": ["instruction", "attention"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["steps"],
    "additionalProperties": False,
}


def _timed(steps: list[InterpretedStep]) -> list[InterpretedStep]:
    """Give each step the time and temperature its own words carry."""
    read = []
    for step in steps:
        seconds, celsius = read_step_timing(step.instruction)
        read.append(
            InterpretedStep(
                instruction=step.instruction,
                duration_seconds=seconds,
                temperature_celsius=celsius,
                attention=step.attention,
            )
        )
    return read


def _carried_over(
    tidied: list[InterpretedStep], written: Sequence[InterpretedStep]
) -> list[InterpretedStep]:
    """Put back a duration the site gave, where the steps themselves say nothing.

    A site's single `cookTime` is a poor answer — it says how long the dish takes, not
    which step takes it — and it is better than none. So it is a fallback: a recipe whose
    steps carry their own times keeps those, and one whose steps say nothing keeps what the
    page said, on the last step, where the waiting is.
    """
    if any(step.duration_seconds is not None for step in tidied) or not tidied:
        return tidied
    given = [step.duration_seconds for step in written if step.duration_seconds is not None]
    if not given:
        return tidied

    last = tidied[-1]
    tidied[-1] = InterpretedStep(
        instruction=last.instruction,
        duration_seconds=max(given),
        temperature_celsius=last.temperature_celsius,
        attention=Attention.WAITING,
    )
    return tidied


async def tidy_steps(written: Sequence[InterpretedStep]) -> list[InterpretedStep]:
    """Edit a page's method into instructions a cook can follow (UC-1.3).

    The founding annoyance, met at the front door: a recipe page's method is written to be
    read on a sofa, and imported verbatim it is the thing this product exists to replace.

    **An improvement, not a requirement.** An instance with no model configured, or one
    whose model falls over, keeps the steps exactly as the page wrote them — the recipe
    still imports, and every site that publishes properly still works. The same is true of
    an answer that comes back empty: a recipe with no method is not an improvement on a
    wordy one.

    Applied to both readings, metadata and prose, because it is one question — *what does a
    cook actually do* — and two implementations of it would drift apart. It is also where
    the metadata path gets what it never had: a time and a temperature on the step they
    belong to, rather than the whole dish's figure landing on the end.
    """
    if not written:
        return []

    method = "\n".join(
        f"{position + 1}. {step.instruction}" for position, step in enumerate(written)
    )
    try:
        answer, _ = await model.complete_structured(
            f"Rewrite this method.\n\n{method}", _EDITING_SCHEMA, system=_EDITING
        )
    except Exception as failure:
        # Any failure at all. Editing is a courtesy, and a courtesy that can fail an import
        # is not one — an unreachable model must cost a cook a tidier recipe, not the
        # recipe.
        #
        # Logged, though. A catch-all this wide will swallow a programming error as
        # readily as an unreachable provider, and it did once: a botched rename made this
        # raise `NameError` on every import, and the only symptom was recipes quietly
        # arriving untidied.
        log.warning("could not tidy the method: %s", failure, exc_info=True)
        return list(written)

    edited = _steps_read(answer.get("steps"))
    if not edited:
        return list(written)
    return _carried_over(_timed(edited), written)


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
    read = from_metadata if from_metadata is not None else await read_prose(content)
    # Both readings go through the same edit. A page's method is written to be read on a
    # sofa, and carried through verbatim it is exactly the thing this product exists to
    # replace — however well the page published it.
    #
    # The language is set here rather than in either reader, because it comes from the
    # page rather than from the recipe and both routes read the same page.
    return replace(
        read, steps=await tidy_steps(read.steps), language=spoken_language(content.language)
    )


def spoken_language(said: str | None) -> str | None:
    """A page's `<html lang>` as a bare language code, or nothing.

    `de-CH`, `de_DE` and `DE` are one language to translate out of; the region is a
    punctuation habit. Anything that is not two or three letters is not a language — pages
    put all sorts of things in that attribute — and nothing is invented to fill the gap.
    """
    if not said:
        return None
    bare = said.strip().replace("_", "-").split("-")[0].casefold()
    return bare if bare.isalpha() and 2 <= len(bare) <= 3 else None


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
