"""Turning recipes into a portable document, and back (FR-11, ADR-012).

A pure transformation. Resolving what a document *refers to* — matching slugs against
this instance's registry, creating what is missing — is sequencing, and belongs to the
manager.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from quookly.contracts.errors import UnknownUnit, UnsupportedDocument
from quookly.contracts.exchange import (
    ExchangeDocument,
    ExchangeIngredient,
    ExchangeLine,
    ExchangeRecipe,
    ExchangeStep,
)
from quookly.contracts.execution import Attention
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.recipe import (
    IngredientLineDraft,
    Provenance,
    Recipe,
    RecipeDraft,
    StepDraft,
)
from quookly.engines import measure

#: What this build writes.
FORMAT_VERSION = 3

#: What this build reads. Format 2 added a recipe's `serves`; format 3 added each step's
#: `attention`. Nothing else changed, and an older document is a complete recipe that
#: simply does not say those things. Reading them all is what keeps every document a
#: self-hoster has already exported valid.
#:
#: The version is bumped rather than the field quietly added to the older format, because
#: an older build reading a document with an unknown field would drop it in silence —
#: which is the partial honouring this check exists to prevent. Refusing outright tells
#: them why.
READABLE_VERSIONS = frozenset({1, 2, FORMAT_VERSION})


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
    #: Hands-on in every document written before format 3, which is the reading that does
    #: not make anybody late.
    attention: Attention = Attention.HANDS_ON


@dataclass(frozen=True, slots=True)
class ReadRecipe:
    title: str
    summary: str | None
    yield_quantity: Quantity
    provenance: Provenance
    lines: list[ReadLine]
    steps: list[ReadStep]
    #: Absent in every format 1 document, and absent is a real answer: such a recipe can
    #: be scaled to a number of pancakes but not to a table.
    serves: Decimal | None = None


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
                serves=recipe.serves,
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
                        attention=step.attention,
                    )
                    for step in recipe.steps
                ],
            )
            for recipe in recipes
        ],
    )


def to_draft(
    recipe: ReadRecipe,
    *,
    ingredient_ids: Mapping[str, int],
    provenance: Provenance,
    origin: Origin = Origin.USER,
) -> RecipeDraft:
    """A recipe read from a document, as a draft this instance can store.

    Here rather than in each manager. Two of them build this — importing a document and
    installing the starter set — and while they were separate copies, adding a field to
    the format meant remembering both. One of them was not remembered, and the starter
    recipes silently lost how many people they feed.

    `ingredient_ids` maps the document's slugs to this instance's ids: a document refers
    by slug because ids belong to the instance that issued them.
    """
    return RecipeDraft(
        title=recipe.title,
        summary=recipe.summary,
        yield_quantity=recipe.yield_quantity,
        serves=recipe.serves,
        provenance=provenance,
        origin=origin,
        lines=[
            IngredientLineDraft(
                ingredient_id=ingredient_ids[line.slug],
                quantity=line.quantity,
                preparation=line.preparation,
                optional=line.optional,
            )
            for line in recipe.lines
        ],
        steps=[
            StepDraft(
                instruction=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
                attention=step.attention,
            )
            for step in recipe.steps
        ],
    )


def _unit(symbol: str) -> Unit:
    """The unit a document names.

    Resolving the symbol is `MeasureEngine`'s — an engine may call an engine, and one
    table is what stops two of them learning about different units. The *refusal* is this
    engine's own: a document naming a unit this build has never heard of is a document
    from a newer Quookly, and saying that is more useful than naming the symbol.
    """
    try:
        return measure.unit_for(symbol)
    except UnknownUnit:
        raise UnsupportedDocument(f"unknown unit: {symbol}") from None


def from_document(raw: dict[str, Any]) -> ReadDocument:
    """Read a document, or refuse it.

    A version this build does not know is refused rather than partially honoured: reading
    it would silently drop whatever the newer format added.
    """
    version = raw.get("quookly")
    if version not in READABLE_VERSIONS:
        raise UnsupportedDocument(
            f"this build reads formats {sorted(READABLE_VERSIONS)}; the document says {version!r}"
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
                serves=recipe.serves,
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
                        attention=step.attention,
                    )
                    for step in recipe.steps
                ],
            )
            for recipe in document.recipes
        ],
    )
