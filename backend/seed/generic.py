"""Build the registry of generic foods from the published Swiss workbooks.

Run by hand, like its sibling `swiss.py`, and for the same reason: the suite must not need
the network, and what it produces is a fixed point a change to the reader is measured
against.

    cd backend && uv run --with openpyxl python seed/generic.py

**What this is, and how it differs from `swiss.py`.** That builder maps a handful of slugs
this application already knows onto published rows, by hand, because *which* wheat flour
answers for "plain flour" is a judgement. This one goes the other way: it takes the
published table as the list of ingredients and derives an entry per row. There is no
judgement per row here — there is judgement in the *rules*, which are in this file and
tested next door.

**Three editions, one table.** The FSVO publishes the same database in English, German and
French, and the row ids are identical across all three, which is what makes a trilingual
registry possible without translating anything ourselves. A cook importing a German recipe
resolves "Zwiebel" against the same entry an English one reaches by "onion" (FR-10).

**What is left out.** Prepared dishes — sandwiches, lasagne, gratins, cakes — because a
registry is the list of things a recipe line can name, and "Lasagne, homemade" is a recipe.
Shelf-stable snacks stay: a household stocks biscuits and crisps, and the pantry is where
they go. Cooked variants of a food that also appears raw are dropped, because a recipe
line says "carrot" and eight carrots in a picker is worse than one.
"""

import hashlib
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple

import openpyxl

sys.path.insert(0, str(Path(__file__).parent))

import allergens as allergen_rules  # noqa: E402

from quookly.contracts.matching import Named  # noqa: E402
from quookly.engines import matching  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "reference"
OUT = Path(__file__).parent / "generic-foods.json"

#: The editions these entries were read from, checked before anything is read. The same
#: argument as `swiss.py`: derived data should say which document it came from, and a
#: refreshed table should be something somebody did rather than something that happened.
#: Update these here and in `reference/README.md` together.
EDITIONS: dict[str, tuple[str, str, str]] = {
    # locale: (file, sheet, sha-256)
    "en-GB": (
        "swiss-food-composition-database.xlsx",
        "Generic Foods",
        "323bae2eecd639d2c3b3bf3797d30b1426ccb0253fb62810f522778b38089196",
    ),
    "de-CH": (
        "swiss-food-composition-database.de.xlsx",
        "Generische Lebensmittel",
        "f4bb854944ef811f9b8463984389f8121e73278c4fd24fc3e8d16336cb711270",
    ),
    "fr-CH": (
        "swiss-food-composition-database.fr.xlsx",
        "Aliments génériques",
        "1692aa241728f25d4823a6c97bb36c393f7f64173a00a8ed4175b1bf926a5405",
    ),
}

#: Column positions, identical in all three editions.
ID, NAME, SYNONYMS, CATEGORY, DENSITY = 0, 3, 4, 5, 6

#: What Quookly tracks, by the English workbook's heading.
NUTRIENTS: dict[str, str] = {
    "energy_kj": "Energy, kilojoules (kJ)",
    "energy_kcal": "Energy, kilocalories (kcal)",
    "fat": "Fat, total (g)",
    "saturates": "Fatty acids, saturated (g)",
    "carbohydrate": "Carbohydrates, available (g)",
    "sugars": "Sugars (g)",
    "fibre": "Dietary fibres (g)",
    "protein": "Protein (g)",
    "salt": "Salt (NaCl) (g)",
}

#: Categories that are dishes rather than ingredients. A registry is the list of things a
#: recipe line can name.
DISHES: tuple[str, ...] = (
    "Prepared dishes/",
    "Sweets/Cakes and tarts",
    "Sweets/Other sweet pastries",
    "Sweets/Creams and puddings",
)

#: How a food was cooked. Present in the name, and the reason the table has eight carrots.
COOKED = re.compile(
    r"\b(steamed|boiled|baked|fried|roast|roasted|cooked|grilled|braised|stewed|blanched|"
    r"poached|barbecued|microwaved|pan.fried|deep.fried|well done|medium done)\b",
    re.IGNORECASE,
)

#: Qualifiers that say how a food was handled rather than what it is, dropped from the
#: name a cook reads. "Leek, raw" is a leek — and "Lauch, roh" is a Lauch, which is why
#: this is per language rather than a single English set. Getting that wrong is not
#: cosmetic: "roh passionsfrucht" is not a thing anybody types.
STATE: dict[str, frozenset[str]] = {
    "en-GB": frozenset(
        {"raw", "fresh", "unprepared", "whole", "without addition of salt", "average"}
    ),
    "de-CH": frozenset({"roh", "frisch", "ganz", "unzubereitet", "durchschnitt", "ungeschält"}),
    "fr-CH": frozenset(
        {"cru", "crue", "frais", "fraîche", "entier", "entière", "non préparé", "moyenne"}
    ),
}

#: Which unit a cook measures this in (UC-6.2). Deliberately coarse — it picks a unit, not
#: a taxonomy. Anything unmatched is solid, which is what a kitchen scale assumes.
POWDERS = ("Flour and starch", "Sugar and sweeteners", "Salt, spices and flavours")
LIQUIDS = (
    "beverages",
    "Oils",
    "Milk and dairy products/Milk",
    "Fruit juices",
    "Vegetable juices",
    "Plant based drinks",
    "Cream",
    "Sauces",
    "Salad dressings",
)
COUNTABLE = ("Eggs",)


#: British spellings for rows the table names in Swiss or American English.
#:
#: Keyed by published row id, like `swiss.py`'s mapping and for the same reason: a row id
#: is stable across a name, and saying which row answers for "aubergine" is a judgement
#: somebody should make on purpose. Quookly's source locale is `en-GB`, so without these a
#: British cook types the word they use and the registry has never heard of it — the exact
#: failure the whole import is meant to end.
#:
#: Additive: the published name stays, and these are alternative spellings for it.
BRITISH: dict[int, list[str]] = {
    367: ["courgette", "courgettes"],  # Zucchini, raw
    349: ["aubergine", "aubergines"],  # Eggplant, raw
    766: ["prawn", "prawns", "king prawns"],  # Shrimp, peeled, raw
    482: ["parmesan"],  # Parmesan cheese
    468: ["rocket"],  # Rocket, raw — already British, kept for the salad-leaf spelling
    14237: ["minced beef", "beef mince", "ground beef"],  # Beef, minced, raw
    22: ["chicken breast", "chicken breasts"],  # Chicken, breast, without skin, raw
    52: ["yoghurt", "natural yoghurt"],  # Yogurt natural
    439: ["chickpeas"],  # Chickpea, dried
    427: ["white rice"],  # Rice polished, raw
    451: ["beetroots"],  # Beetroot, raw
    194: ["salmon"],  # Salmon, cultured, raw — farmed is what a shop sells
    663: ["paprika"],  # Paprika (spice)
    762: ["table salt"],  # Table salt iodized
    539: ["feta"],  # Feta, cow milk — the ewe/goat one is a separate row
    756: ["tuna"],  # Fish, tuna, raw — filed under "Fish", so the bare word went unclaimed
    13437: ["tofu"],  # Tofu, firm, plain (average)
    432: ["sweetcorn", "sweet corn"],  # Sweet corn, raw
}


class Entry(NamedTuple):
    row: int
    slug: str
    kind: str
    density: str | None
    allergens: list[str] | None
    names: dict[str, list[str]]
    amounts: dict[str, str]
    reference: str


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _table(locale: str) -> tuple[dict[str, tuple[Any, ...]], list[Any]]:
    """One edition, by row id, with its header."""
    name, sheet, expected = EDITIONS[locale]
    path = REFERENCE / name
    if not path.exists():
        raise SystemExit(f"{path} is missing. See reference/README.md.")
    found = _digest(path)
    if found != expected:
        raise SystemExit(
            f"{name} is not the edition these rules were written against.\n"
            f"  expected {expected}\n  found    {found}\n"
            "Check the rules still hold, then update EDITIONS here and reference/README.md."
        )
    workbook = openpyxl.load_workbook(path, read_only=True)
    rows = workbook[sheet].iter_rows(values_only=True)
    for _ in range(2):
        next(rows)
    header = list(next(rows))
    return {str(row[ID]): row for row in rows if row[NAME]}, header


def _amount(value: Any) -> str | None:
    """A published figure, or nothing where the table did not measure one.

    Traces are written "<0.1" and gaps are blank. Neither is a number, and turning either
    into zero would say a food contains none of something nobody looked for.
    """
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text or text.startswith("<") or text in {"-", "n.a.", "tr"}:
        return None
    try:
        float(text)
    except ValueError:
        return None
    return text


def _parts(name: str) -> list[str]:
    """A published name split on its commas — but not the ones inside brackets.

    "Lamb (sheep), leg, raw (Switzerland, New Zealand)" is three parts, not five. Splitting
    naively produced "new zealand) raw (switzerland leg lamb (sheep)", which is how this
    function came to exist.
    """
    out, depth, current = [], 0, ""
    for character in str(name):
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        if character == "," and depth == 0:
            out.append(current.strip())
            current = ""
        else:
            current += character
    out.append(current.strip())
    return [part for part in out if part]


def _without_asides(text: str) -> str:
    """Drop bracketed asides. They qualify a figure, not the food: "(without addition of
    fat and salt)" is a note about how it was measured."""
    return re.sub(r"\s*\([^)]*\)", "", text).strip()


def _readable(name: str, locale: str = "en-GB") -> str:
    """The published name as a cook would say it.

    The table writes "Bell pepper, green" so it sorts under B. A cook types "green bell
    pepper", so the qualifiers move in front of the head and the handling words go.
    """
    parts = [_without_asides(part) for part in _parts(name)]
    parts = [part for part in parts if part]
    if not parts:
        return _without_asides(str(name)).strip()
    state = STATE.get(locale, STATE["en-GB"])
    head, rest = parts[0], [p for p in parts[1:] if p.lower() not in state]
    return " ".join([*reversed(rest), head]).strip().lower()


def _slug(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", folded.lower())).strip("-")


def _kind(category: str, density: Any) -> str:
    if any(one in category for one in COUNTABLE):
        return "countable"
    if any(one in category for one in POWDERS):
        return "powder"
    if any(one in category for one in LIQUIDS):
        return "liquid"
    # A published density is only meaningful for something pourable, so the table having
    # one is itself evidence.
    return "liquid" if density not in (None, "") else "solid"


def _is_dish(category: str) -> bool:
    return any(part.strip().startswith(DISHES) for part in category.split(";"))


def _head(name: str) -> str:
    """What a row is a variant *of*, for deciding whether a cooked one is worth keeping."""
    return _without_asides(_parts(name)[0]).lower()


def _spelled_alike(heads: list[str]) -> list[tuple[str, str]]:
    """Pairs of heads that are one head written two ways.

    Uses the application's own `MatchingEngine`, which is the same judgement made in the
    same place: it ranks names that look like one thing and refuses opposites, and here it
    is asked only to say which heads to treat as one before deciding who may claim a bare
    name. Nothing is merged — the two rows stay two ingredients, they simply both stop
    being "the plain one".
    """
    named = [Named(slug=head, names=(head,)) for head in heads]
    return [(pair.slug, pair.other) for pair in matching.duplicates(named, limit=10_000)]


def _starter_claims() -> tuple[set[str], dict[str, set[str]]]:
    """The slugs and names the hand-written starter set already owns.

    Those entries are better than anything derived here: somebody chose which of four wheat
    flours answers for "plain flour", and they carry densities and piece weights this table
    does not publish. So the starter wins every collision, and this file is built around it
    rather than over it — otherwise seeding would hit the registry's unique index and lose,
    silently, whichever entry happened to arrive second.
    """
    here = Path(__file__).parent
    starter = json.loads((here / "starter.en-GB.json").read_text(encoding="utf8"))
    slugs = {entry["slug"] for entry in starter["ingredients"]}
    names: dict[str, set[str]] = {locale: set() for locale in EDITIONS}
    for entry in starter["ingredients"]:
        names["en-GB"].update(one.strip().lower() for one in entry["names"])
    for locale in ("de-CH", "fr-CH"):
        path = here / f"names.{locale}.json"
        if path.exists():
            translated = json.loads(path.read_text(encoding="utf8"))["names"]
            for spellings in translated.values():
                names[locale].update(one.strip().lower() for one in spellings)
    return slugs, names


def _plainness(name: str) -> int:
    """How many qualifiers a published name carries.

    Used to order the build so the plainest variant of a food claims the short name: a
    recipe line says "potato", and it should reach the potato rather than whichever
    potato sorts first alphabetically.
    """
    return len([one for one in _parts(name)[1:] if one.lower() not in STATE["en-GB"]])


def main() -> None:
    tables, headers = {}, {}
    for locale in EDITIONS:
        tables[locale], headers[locale] = _table(locale)

    english = tables["en-GB"]
    at = {key: headers["en-GB"].index(column) for key, column in NUTRIENTS.items()}

    considered = {
        row_id: row for row_id, row in english.items() if not _is_dish(str(row[CATEGORY] or ""))
    }
    # A cooked variant is worth keeping only where the food appears no other way. A recipe
    # line says "carrot"; it never says "carrot, steamed, without addition of salt".
    plain = {_head(row[NAME]) for row in considered.values() if not COOKED.search(str(row[NAME]))}
    chosen = {
        row_id: row
        for row_id, row in considered.items()
        if not COOKED.search(str(row[NAME])) or _head(row[NAME]) not in plain
    }

    # First claim wins, so a name means one ingredient per language. The registry enforces
    # this with a unique index and would silently drop the loser; deciding it here means
    # the file says what will happen.
    slugs, claimed = _starter_claims()
    entries: list[Entry] = []

    # Which rows may claim the bare head of their name — "potato" from "Potato, peeled,
    # raw". Only where one row is unambiguously the plainest for that head. Three salmons
    # and four chickens are a genuine ambiguity, and handing "yogurt" to whichever
    # flavoured yogurt sorted first is how a cook ends up with chocolate in a tzatziki.
    plainest: dict[str, list[tuple[int, str]]] = {}
    for row_id, row in chosen.items():
        plainest.setdefault(_head(row[NAME]), []).append((_plainness(row[NAME]), row_id))

    # Heads the table spells more than one way are one head here. It writes `Soy drink,
    # chocolate` beside `Soya drink, plain`, `Pizza dough ..., baked` beside `Pizza doug
    # ..., raw`, and `Brussels sprouts, raw` beside `Brussel sprouts, steamed`. Compared
    # literally each spelling looks like the only row for its head, so *both* rows claim a
    # bare name — and "soy drink" then means the chocolate one. That is the exact failure
    # the check below exists to prevent, arriving through a spelling rather than a variant.
    for head, other in _spelled_alike(sorted(plainest)):
        plainest[head] = plainest[other] = sorted({*plainest[head], *plainest[other]})

    unambiguous = {
        head: rows[0][1]
        for head, variants in plainest.items()
        if len(rows := sorted(variants)) == 1 or rows[0][0] < rows[1][0]
    }

    # Plainest first, so the short names go to the plain foods. Alphabetical within that,
    # so the build is reproducible.
    ordered = sorted(
        chosen.items(), key=lambda pair: (_plainness(pair[1][NAME]), str(pair[1][NAME]))
    )
    for row_id, row in ordered:
        english_name = str(row[NAME])
        category = str(row[CATEGORY] or "")

        slug = _slug(_readable(english_name)) or _slug(english_name)
        if slug in slugs:
            slug = f"{slug}-{row_id}"
        slugs.add(slug)

        names: dict[str, list[str]] = {}
        for locale, table in tables.items():
            published = str(table[row_id][NAME])
            wanted = [_readable(published, locale), published.lower()]
            # The bare head too — "potato" from "Potato, peeled, raw" — because an imported
            # recipe line resolves by exact name and never says "peeled potato".
            if unambiguous.get(_head(row[NAME])) == row_id:
                wanted.insert(1, _without_asides(_parts(published)[0]).lower())
            if locale == "en-GB":
                wanted += BRITISH.get(int(row_id), [])
            synonyms = table[row_id][SYNONYMS]
            if synonyms:
                wanted += [one.strip().lower() for one in str(synonyms).split(";") if one.strip()]
            kept = []
            for spelling in wanted:
                folded = re.sub(r"\s+", " ", spelling.strip())
                if folded and folded not in claimed[locale]:
                    claimed[locale].add(folded)
                    kept.append(folded)
            if kept:
                names[locale] = kept
        if "en-GB" not in names:
            # Every spelling this row would use is already another row's. Nothing here to
            # add: the ingredient exists, under the name that claimed it first.
            continue

        verdict = allergen_rules.of(english_name, category)
        entries.append(
            Entry(
                row=int(row_id),
                slug=slug,
                kind=_kind(category, row[DENSITY]),
                density=str(row[DENSITY]) if row[DENSITY] not in (None, "") else None,
                allergens=(
                    sorted(one.value for one in verdict.allergens) if verdict.classified else None
                ),
                names=names,
                amounts={
                    nutrient: value
                    for nutrient, position in at.items()
                    if (value := _amount(row[position])) is not None
                },
                reference=f"{row_id} {english_name}",
            )
        )

    OUT.write_text(
        json.dumps(
            {
                "quookly": 1,
                "source": "swiss",
                "retrieved": datetime.now(UTC).date().isoformat(),
                "note": (
                    "Generated by seed/generic.py from the Swiss Food Composition Database. "
                    "Do not edit by hand: re-run the builder."
                ),
                "ingredients": [entry._asdict() for entry in entries],
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    classified = sum(1 for entry in entries if entry.allergens is not None)
    print(f"{len(entries)} ingredients -> {OUT}")
    print(
        f"  {classified} answered completely for allergens, {len(entries) - classified} left "
        "unclassified"
    )
    print(f"  {sum(1 for e in entries if e.density)} carry a density")
    print(f"  {sum(1 for e in entries if e.amounts)} carry nutrition")


if __name__ == "__main__":
    main()
