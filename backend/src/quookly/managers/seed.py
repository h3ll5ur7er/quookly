"""Stocking a fresh instance (UC-10.4, FR-17, ADR-016).

An empty instance is indistinguishable from a broken one, and a cook with nothing to look
at has no reason to return.

The seed file is an ordinary exchange document, so the format that carries a cook's
recipes out is the same one that brings the starter set in — one format to maintain, and
a self-hoster can supply their own.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from quookly.access import ingredient as registry
from quookly.access import recipe as recipe_access
from quookly.contracts.ingredient import Origin
from quookly.contracts.nutrition import Nutrient, NutrientProfile, NutritionSource
from quookly.contracts.recipe import Provenance
from quookly.engines import exchange
from quookly.utilities.diagnostics import get_logger

# Beside the package rather than inside it: seed content is data an operator may want to
# read, replace, or supply their own version of.
SEED_DIRECTORY = Path(__file__).resolve().parents[3] / "seed"
DEFAULT_SEED_LOCALE = "en-GB"

log = get_logger("seed")


def read_seed_file(locale: str = DEFAULT_SEED_LOCALE) -> dict[str, Any]:
    """The shipped starter document."""
    path = SEED_DIRECTORY / f"starter.{locale}.json"
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf8"))
    return document


#: The languages the shipped ingredients are named in, beyond the one they are defined in.
#: Without these a German recipe resolves nothing: every ingredient becomes a new entry
#: nobody has classified, and a recipe made of flour, milk and eggs loses its allergens
#: entirely — the registry knew the answer and was asked the wrong word (FR-10).
TRANSLATED_LOCALES = ("de-CH", "fr-CH")


def read_names_file(locale: str) -> dict[str, list[str]]:
    """What the seeded ingredients are called in one language."""
    path = SEED_DIRECTORY / f"names.{locale}.json"
    if not path.exists():
        return {}
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf8"))
    names: dict[str, list[str]] = document.get("names", {})
    return names


async def name_ingredients() -> int:
    """Teach the registry the other languages it ships in. Returns how many names were new.

    Runs at every start-up alongside stocking, and is additive: an entry keeps whatever
    names it already has. A translation is a name and nothing more — it never touches a
    density or an allergen classification.
    """
    added = 0
    for locale in TRANSLATED_LOCALES:
        for slug, spellings in read_names_file(locale).items():
            added += await registry.name_in(slug, locale, spellings)
    if added:
        log.info("named the registry in %s languages", len(TRANSLATED_LOCALES))
    return added


async def stock_registry(locale: str = DEFAULT_SEED_LOCALE) -> int:
    """Add the seeded ingredients this instance does not have. Returns how many.

    Safe to run repeatedly — every start-up does — and it never touches an entry that is
    already here. A cook's own density is their business, and an upgrade refreshing the
    seed set must not overwrite their work (ADR-016).
    """
    document = exchange.from_document(read_seed_file(locale))
    known = await registry.slugs_present([entry.slug for entry in document.ingredients])

    added = 0
    for entry in document.ingredients:
        if entry.slug in known:
            continue
        await registry.register(
            slug=entry.slug,
            kind=entry.kind,
            density=entry.density,
            names={document.locale: entry.names},
            origin=Origin.SEED,
            allergens=entry.allergens,
        )
        added += 1

    if added:
        log.info("stocked the registry with %s ingredients", added, extra={"added": added})
    await name_ingredients()
    return added


#: The composition tables shipped with the application, in the order they are installed.
#: Adding one is a file and a line, which is the point of holding profiles per source
#: rather than choosing at seed time (ADR-045).
SHIPPED_NUTRITION = (NutritionSource.SWISS,)


def read_nutrition_file(source: NutritionSource) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (SEED_DIRECTORY / f"nutrition.{source.value}.json").read_text(encoding="utf-8")
    )
    return document


async def stock_nutrition() -> int:
    """Install the published figures for the ingredients this registry has. Returns how many.

    Restated on every start-up rather than added once. A refreshed table is a corrected
    table, and a figure this instance holds that the publisher has since revised should
    move — these are somebody else's measurements, not a cook's own work, so the reasoning
    that protects a hand-set density (ADR-016) does not apply.

    Ingredients the table does not carry are simply absent. That is the cascade working:
    another source answers for them, or the recipe says it could not count them.
    """
    installed = 0
    for source in SHIPPED_NUTRITION:
        document = read_nutrition_file(source)
        profiles = document["profiles"]
        ids = await registry.ids_by_slug([one["slug"] for one in profiles])
        for one in profiles:
            ingredient_id = ids.get(one["slug"])
            if ingredient_id is None:
                # An instance whose registry does not have this ingredient. Nothing to
                # attach the figures to, and inventing the entry would be a different job.
                continue
            await registry.record_profile(
                NutrientProfile(
                    ingredient_id=ingredient_id,
                    source=source,
                    reference=one["reference"],
                    amounts={
                        Nutrient(name): Decimal(value) for name, value in one["amounts"].items()
                    },
                )
            )
            installed += 1

    if installed:
        log.info("stocked %s nutrient profiles", installed, extra={"profiles": installed})
    return installed


async def install_starter_recipes(cook_id: int, locale: str = DEFAULT_SEED_LOCALE) -> int:
    """Give a cook the starter recipes. Returns how many.

    Given to the cook rather than owned by the instance, so they are theirs to change —
    which is the point of a starter recipe, and avoids inventing a system account that
    nothing else needs.
    """
    # Make sure the ingredients these recipes point at exist. Stocking is idempotent, so
    # the operation is self-sufficient rather than relying on start-up having run first.
    await stock_registry(locale)

    document = exchange.from_document(read_seed_file(locale))
    ids = await registry.ids_by_slug(
        sorted({line.slug for recipe in document.recipes for line in recipe.lines})
    )

    for recipe in document.recipes:
        await recipe_access.store(
            exchange.to_draft(
                recipe,
                ingredient_ids=ids,
                provenance=Provenance.AUTHORED,
                origin=Origin.SEED,
            ),
            cook_id,
        )
    return len(document.recipes)
