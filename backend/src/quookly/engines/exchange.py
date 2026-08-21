"""Turning recipes into a portable document, and back (FR-11, ADR-012).

A pure transformation. Resolving what a document *refers to* — matching slugs against
this instance's registry, creating what is missing — is sequencing, and belongs to the
manager.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from quookly.contracts.errors import UnsupportedDocument
from quookly.contracts.exchange import (
    ExchangeDocument,
    ExchangeIngredient,
    ExchangeLine,
    ExchangeRecipe,
    ExchangeStep,
)
from quookly.contracts.ingredient import Allergen, IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.recipe import Provenance, Recipe

FORMAT_VERSION = 1

_UNITS_BY_SYMBOL = {unit.symbol: unit for unit in Unit}


@dataclass(frozen=True, slots=True)
class ReadLine:
    slug: str
    quantity: Quantity | None
    preparation: str | None
    optional: bool


@dataclass(frozen=True, slots=True)
class ReadStep:
    instruction: str
    duration_seconds: int | None
    temperature_celsius: int | None


@dataclass(frozen=True, slots=True)
class ReadRecipe:
    title: str
    summary: str | None
    yield_quantity: Quantity
    provenance: Provenance
    lines: list[ReadLine]
    steps: list[ReadStep]


@dataclass(frozen=True, slots=True)
class ReadIngredient:
    slug: str
    kind: IngredientKind
    density: Decimal | None
    names: list[str]
    allergens: frozenset[Allergen] | None


@dataclass(frozen=True, slots=True)
class ReadDocument:
    locale: str
    ingredients: list[ReadIngredient]
    recipes: list[ReadRecipe]


def to_document(recipes: list[Recipe], locale: str) -> ExchangeDocument:
    """Build a portable document from recipes fetched whole.

    Quantities are carried as written rather than as rendered: an export is the recipe,
    not one cook's view of it.
    """
    used: dict[str, ExchangeIngredient] = {}
    for recipe in recipes:
        for line in recipe.lines:
            entry = line.ingredient
            used.setdefault(
                entry.slug,
                ExchangeIngredient(
                    slug=entry.slug,
                    kind=entry.kind,
                    density=entry.density,
                    names=[entry.name],
                    allergens=sorted(entry.allergens, key=lambda a: a.value)
                    if entry.classified
                    else None,
                ),
            )

    return ExchangeDocument(
        quookly=FORMAT_VERSION,
        exported_at=datetime.now(UTC),
        locale=locale,
        ingredients=sorted(used.values(), key=lambda entry: entry.slug),
        recipes=[
            ExchangeRecipe(
                title=recipe.title,
                summary=recipe.summary,
                yield_magnitude=recipe.yield_quantity.magnitude,
                yield_unit=recipe.yield_quantity.unit.symbol,
                provenance=recipe.provenance,
                lines=[
                    ExchangeLine(
                        ingredient=line.ingredient.slug,
                        magnitude=(None if line.quantity is None else line.quantity.magnitude),
                        unit=(None if line.quantity is None else line.quantity.unit.symbol),
                        preparation=line.preparation,
                        optional=line.optional,
                    )
                    for line in recipe.lines
                ],
                steps=[
                    ExchangeStep(
                        instruction=step.instruction,
                        duration_seconds=step.duration_seconds,
                        temperature_celsius=step.temperature_celsius,
                    )
                    for step in recipe.steps
                ],
            )
            for recipe in recipes
        ],
    )


def _unit(symbol: str) -> Unit:
    try:
        return _UNITS_BY_SYMBOL[symbol]
    except KeyError:
        raise UnsupportedDocument(f"unknown unit: {symbol}") from None


def from_document(raw: dict[str, Any]) -> ReadDocument:
    """Read a document, or refuse it.

    A version this build does not know is refused rather than partially honoured: reading
    it would silently drop whatever the newer format added.
    """
    version = raw.get("quookly")
    if version != FORMAT_VERSION:
        raise UnsupportedDocument(
            f"this build reads format {FORMAT_VERSION}; the document says {version!r}"
        )

    try:
        document = ExchangeDocument.model_validate(raw)
    except ValidationError as invalid:
        raise UnsupportedDocument(str(invalid)) from None

    return ReadDocument(
        locale=document.locale,
        ingredients=[
            ReadIngredient(
                slug=entry.slug,
                kind=entry.kind,
                density=entry.density,
                names=list(entry.names),
                allergens=None if entry.allergens is None else frozenset(entry.allergens),
            )
            for entry in document.ingredients
        ],
        recipes=[
            ReadRecipe(
                title=recipe.title,
                summary=recipe.summary,
                yield_quantity=Quantity(recipe.yield_magnitude, _unit(recipe.yield_unit)),
                provenance=recipe.provenance,
                lines=[
                    ReadLine(
                        slug=line.ingredient,
                        quantity=(
                            None
                            if line.magnitude is None or line.unit is None
                            else Quantity(line.magnitude, _unit(line.unit))
                        ),
                        preparation=line.preparation,
                        optional=line.optional,
                    )
                    for line in recipe.lines
                ],
                steps=[
                    ReadStep(
                        instruction=step.instruction,
                        duration_seconds=step.duration_seconds,
                        temperature_celsius=step.temperature_celsius,
                    )
                    for step in recipe.steps
                ],
            )
            for recipe in document.recipes
        ],
    )
