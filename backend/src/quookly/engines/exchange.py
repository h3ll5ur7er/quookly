"""Turning recipes into a portable document, and back (FR-11, ADR-012).

A pure transformation. Resolving what a document *refers to* — matching slugs against
this instance's registry, creating what is missing — is sequencing, and belongs to the
manager.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    ExchangeTranslation,
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
from quookly.contracts.translation import Rendered, Translatable
from quookly.engines import measure

#: What this build writes.
FORMAT_VERSION = 5

#: What this build reads. Format 2 added a recipe's `serves`; format 3 added each step's
#: `attention`; format 4 added `derived` to the provenances a recipe can carry; format 5
#: added the language a recipe is written in, the translations somebody here wrote, and
#: every language the registry names an ingredient in (ADR-012, ADR-064). Nothing
#: else changed, and an older document is a complete recipe that simply does not say those
#: things. Reading them all is what keeps every document a self-hoster has already
#: exported valid.
#:
#: Format 4 is the one bump that is not about a *missing* field. An older build reading
#: `"provenance": "derived"` would refuse the whole document over one recipe, with a
#: validation error rather than an explanation — so the version says why first.
#:
#: The version is bumped rather than the field quietly added to the older format, because
#: an older build reading a document with an unknown field would drop it in silence —
#: which is the partial honouring this check exists to prevent. Refusing outright tells
#: them why.
READABLE_VERSIONS = frozenset({1, 2, 3, 4, FORMAT_VERSION})


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
    #: What the prose is written in. Absent before format 5 and absent where nobody knew.
    language: str | None = None
    #: Translations a person wrote, ready to store. Empty before format 5.
    translations: list[Rendered] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReadIngredient:
    slug: str
    kind: IngredientKind
    density: Decimal | None
    names: list[str]
    allergens: frozenset[Allergen] | None
    #: Every language the exporting registry named it in. Before format 5 there was one,
    #: and it is filled in here from the document's own locale so that no caller has to
    #: know which format it came from.
    names_by_locale: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReadDocument:
    locale: str
    ingredients: list[ReadIngredient]
    recipes: list[ReadRecipe]


def to_document(
    recipes: list[Recipe],
    locale: str,
    translations: Mapping[int, Sequence[Rendered]] | None = None,
    names: Mapping[str, Mapping[str, list[str]]] | None = None,
) -> ExchangeDocument:
    """Build a portable document from recipes fetched whole.

    Quantities are carried as written rather than as rendered: an export is the recipe,
    not one cook's view of it.

    `translations` are the ones a **person** wrote, by recipe id, and `names` is every
    language the registry knows an ingredient by. Both are passed in rather than fetched:
    this is a rule engine, and what it does is a table of inputs to one document.
    """
    by_recipe = translations or {}
    known = names or {}
    used: dict[str, ExchangeIngredient] = {}
    for recipe in recipes:
        for line in recipe.lines:
            entry = line.ingredient
            spellings = known.get(entry.slug, {})
            used.setdefault(
                entry.slug,
                ExchangeIngredient(
                    slug=entry.slug,
                    kind=entry.kind,
                    density=entry.density,
                    # The document's own locale first, so a build reading format 4 gets the
                    # name it would have got before.
                    names=list(spellings.get(locale, [entry.name])) or [entry.name],
                    names_by_locale={one: list(said) for one, said in spellings.items() if said},
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
                language=recipe.language,
                translations=[
                    ExchangeTranslation(
                        locale=one.locale,
                        title=one.words.title,
                        summary=one.words.summary,
                        steps=list(one.words.steps),
                    )
                    for one in by_recipe.get(recipe.id, [])
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

    The translations a document carries are *not* here. A draft is what `RecipeAccess`
    stores as one recipe, and a translation is stored against the recipe id that comes
    back from it — so it belongs to the caller, after the store.
    """
    return RecipeDraft(
        title=recipe.title,
        summary=recipe.summary,
        yield_quantity=recipe.yield_quantity,
        serves=recipe.serves,
        provenance=provenance,
        origin=origin,
        # Carried across, and absent where the document did not say. Without it a German
        # recipe arrives on a fresh instance with nothing to say it is German, so nothing
        # can translate it and the translations that travelled with it cannot be used
        # (ADR-032, format 5).
        language=recipe.language,
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
                # Filled in from the document's own locale where it said nothing, so that
                # no caller has to know which format it came from.
                names_by_locale={
                    one: list(said) for one, said in entry.names_by_locale.items() if said
                }
                or {document.locale: list(entry.names)},
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
                language=recipe.language,
                translations=[
                    Rendered(
                        locale=one.locale,
                        words=Translatable(
                            title=one.title, summary=one.summary, steps=list(one.steps)
                        ),
                    )
                    for one in recipe.translations
                ],
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
