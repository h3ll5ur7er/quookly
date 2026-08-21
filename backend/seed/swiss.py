"""Build the Swiss nutrition seed from the published workbook.

Run by hand, not by the test suite — the suite must not need the network, and the seed it
produces is a fixed point that a change to the reader is measured against.

    cd backend && uv run --with openpyxl python seed/swiss.py

The workbook is kept in `reference/`, not downloaded. Its published URL contains the month
it was released, so a build step that fetched it would work until the FSVO put out the next
edition. Its terms permit commercial use "subject to acknowledgment of the source", and
opendata.swiss records the dataset as "Open use. Must provide the source." — which is why
every profile carries its credit and why FR-20 exists (ADR-007).

**The mapping is by hand and that is the point.** Which published row answers for
"plain flour" is a judgement, not something to infer from a name: the table has four wheat
flours by ash content, and picking one is a decision somebody should have made on purpose.
Each is recorded with the row it came from, so any number can be traced back.

Where the table has nothing — baking powder, bicarbonate of soda, wholemeal flour — the
slug is simply absent. That is the cascade working: a later source answers, or the recipe
says so.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = ROOT / "reference" / "swiss-food-composition-database.xlsx"
OUT = Path(__file__).parent / "nutrition.swiss.json"

#: The edition these figures were read from. Checked before anything is read, so the seed
#: says which *document* it came from rather than merely which kind of document — and so a
#: refreshed table is something somebody did on purpose rather than something that
#: happened. Update it here and in `reference/README.md` together.
DIGEST = "323bae2eecd639d2c3b3bf3797d30b1426ccb0253fb62810f522778b38089196"

#: This instance's ingredient slug, and the published row that answers for it.
#:
#: A few are deliberate substitutions rather than exact matches, and they are marked. Icing
#: sugar is white sugar ground finer; the table has one sugar and grinding does not change
#: sucrose. Vegetable oil is rapeseed, which is what "Öl" means on a Swiss shelf.
MAPPED: dict[str, int] = {
    "plain-flour": 205,  # Wheat flour, white, type 400
    "cornflour": 426,  # Maize starch — "cornflour" in British usage
    "caster-sugar": 470,  # Sugar, white
    "granulated-sugar": 470,  # Sugar, white — the same sucrose, ground coarser
    "icing-sugar": 470,  # Sugar, white — substitution: ground finer, same substance
    "brown-sugar": 471,  # Sugar, brown
    "fine-salt": 14086,  # Salt, sea salt, standard, white
    "cocoa-powder": 581,  # Cocoa powder, without sugar
    "ground-almonds": 273,  # Almond
    "rolled-oats": 198,  # Oat flakes
    "rice": 427,  # Rice polished, raw
    "water": 47,  # Drinking water (average Switzerland)
    "whole-milk": 62,  # Whole milk, pasteurized
    "double-cream": 798,  # Cream, at least 45 % milk fat — double cream is 48%
    "olive-oil": 591,  # Olive oil
    "vegetable-oil": 600,  # Rapeseed oil — substitution: what "oil" means on a Swiss shelf
    "honey": 472,  # Honey, from flowers
    "white-wine": 511,  # Wine white, 12.5 vol%
    "unsalted-butter": 49,  # Butter of choice — the salted one is a separate row
    "plain-yoghurt": 52,  # Yogurt natural
    "egg": 290,  # Egg, raw
    "egg-yolk": 410,  # Egg yolk, raw
    "egg-white": 411,  # Egg white, raw
    "onion": 368,  # Onion, raw
    "garlic-clove": 356,  # Garlic, raw
    "lemon": 398,  # Lemon, fresh
}

#: The workbook's column heading for each nutrient Quookly tracks. Salt rather than sodium,
#: because that is what a label in this part of the world declares and the table publishes
#: both.
COLUMNS: dict[str, str] = {
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


def _amount(value: Any) -> str | None:
    """A published figure, or nothing where the table did not measure one.

    The workbook writes traces as "<0.1" and gaps as blanks. Neither is a number, and
    turning either into zero would say the food contains none of something nobody looked
    for.
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


def _the_edition_we_read() -> None:
    """Refuse to build from a document this mapping was not written against.

    The mapping below picks one of four wheat flours by its row number. A different edition
    can renumber, rename or withdraw a row, and the failure would be silent: plausible
    figures against the wrong food.
    """
    if not WORKBOOK.exists():
        raise SystemExit(f"{WORKBOOK} is missing. See reference/README.md.")
    digest = hashlib.sha256(WORKBOOK.read_bytes()).hexdigest()
    if digest != DIGEST:
        raise SystemExit(
            f"{WORKBOOK.name} is not the edition this mapping was written against.\n"
            f"  expected {DIGEST}\n  found    {digest}\n"
            "Check the mapping still points at the right rows, then update DIGEST here "
            "and the digest in reference/README.md."
        )


def main() -> None:
    _the_edition_we_read()
    workbook = openpyxl.load_workbook(WORKBOOK, read_only=True)
    rows = workbook["Generic Foods"].iter_rows(values_only=True)
    for _ in range(2):
        next(rows)
    header = list(next(rows))
    at = {name: header.index(column) for name, column in COLUMNS.items()}
    published = {str(row[0]): row for row in rows if row[3]}

    profiles = []
    for slug, entry in sorted(MAPPED.items()):
        row = published.get(str(entry))
        if row is None:
            print(f"{slug}: NO SUCH ROW {entry}")
            continue
        amounts = {
            nutrient: value
            for nutrient, position in at.items()
            if (value := _amount(row[position])) is not None
        }
        profiles.append(
            {
                "slug": slug,
                # The row this came from, so any number can be traced to a published one.
                "reference": f"{entry} {row[3]}",
                "amounts": amounts,
            }
        )
        print(f"{slug:<20} {row[3][:52]:<54} {len(amounts)} nutrients")

    OUT.write_text(
        json.dumps(
            {
                "quookly": 1,
                "source": "swiss",
                "retrieved": datetime.now(UTC).date().isoformat(),
                "profiles": profiles,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(profiles)} profiles -> {OUT}")


if __name__ == "__main__":
    main()
