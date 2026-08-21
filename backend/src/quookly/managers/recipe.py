"""The recipe use case family: authoring, listing, and presenting (UC-1.1, UC-2.1, UC-2.2).

Sequences the steps and owns none of the rules. Storage is `RecipeAccess`, preferences are
`PreferenceAccess`, and every quantity decision belongs to `MeasureEngine`.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from quookly.access import cook as cook_access
from quookly.access import eater as eater_access
from quookly.access import ingredient as registry
from quookly.access import preferences as preference_access
from quookly.access import recipe as recipe_access
from quookly.access import web
from quookly.contracts.errors import UnsupportedDocument, YieldUnknown
from quookly.contracts.exchange import ExchangeDocument
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.contracts.interpretation import InterpretedLine
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.preferences import UnitPreferences
from quookly.contracts.recipe import (
    ImportedRecipe,
    IngredientLineDraft,
    PresentedLine,
    PresentedRecipe,
    PresentedStep,
    Provenance,
    QuantityView,
    Recipe,
    RecipeDraft,
    RecipeInput,
    RecipeSummaryView,
    StepDraft,
)
from quookly.contracts.suitability import JudgedLine, Outcome, VerdictView
from quookly.contracts.web import ReadableContent
from quookly.engines import exchange, interpretation, measure, suitability

#: Resolving a symbol lives in `MeasureEngine`, which owns units. Kept as a local name
#: because it reads better at the call sites than the qualified one.
_unit = measure.unit_for


def _servings(serves: Decimal | None, factor: Decimal) -> str | None:
    """How many this feeds, scaled and tidied — or nothing where the yield already says.

    Rendered as a plain number rather than a quantity: "serves 4", not "4 servings", and
    trailing zeros from the column are an artefact of storage rather than precision
    anybody should read into.
    """
    if serves is None:
        return None
    scaled = measure.round_for_display(Quantity(serves * factor, Unit.SERVING))
    text = f"{scaled.magnitude:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _view(quantity: Quantity) -> QuantityView:
    """A quantity as a client reads it.

    `magnitude` keeps the stored precision, for a client that computes with it.
    `display` is tidied here rather than at each call site: stored precision is not
    display precision, and a yield of "12.0000" is not a yield.
    """
    return QuantityView(
        magnitude=str(quantity.magnitude),
        unit=quantity.unit.symbol,
        display=str(measure.round_for_display(quantity)),
    )


async def author(
    submitted: RecipeInput, cook_id: int, locale: str | None = None
) -> PresentedRecipe:
    """Store a recipe and hand it back as the cook will read it."""
    locale = locale or await cook_access.locale_for(cook_id)
    draft = RecipeDraft(
        title=submitted.title,
        summary=submitted.summary,
        yield_quantity=Quantity(submitted.yield_magnitude, _unit(submitted.yield_unit)),
        serves=submitted.serves,
        provenance=Provenance.AUTHORED,
        lines=[
            IngredientLineDraft(
                ingredient_id=line.ingredient_id,
                # Both or neither: the input model already refuses one without the other.
                quantity=(
                    None
                    if line.magnitude is None or line.unit is None
                    else Quantity(line.magnitude, _unit(line.unit))
                ),
                preparation=line.preparation,
                optional=line.optional,
            )
            for line in submitted.lines
        ],
        steps=[
            StepDraft(
                instruction=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
            )
            for step in submitted.steps
        ],
    )
    stored = await recipe_access.store(draft, cook_id)
    return await _present(stored, await preference_access.for_cook(cook_id), None, cook_id)


def _facts(line: JudgedLine) -> suitability.IngredientFacts:
    return suitability.IngredientFacts(
        slug=line.slug,
        name=line.name,
        allergens=line.allergens,
        classified=line.classified,
        optional=line.optional,
    )


async def _outcomes_for(cook_id: int, locale: str) -> dict[int, Outcome]:
    """One outcome per recipe this cook owns, judged against their household.

    Judged here rather than per row so the whole list costs a fixed number of queries,
    and by the same engine the recipe page uses. A badge that disagrees with the page it
    leads to would teach a cook that the badge cannot be trusted, which is worse than
    having no badge at all.
    """
    household = await eater_access.list_for_cook(cook_id)
    if not household:
        return {}

    by_recipe: dict[int, list[suitability.IngredientFacts]] = {}
    for line in await recipe_access.lines_to_judge(cook_id, locale):
        by_recipe.setdefault(line.recipe_id, []).append(_facts(line))

    return {
        recipe_id: suitability.evaluate(facts, household).outcome
        for recipe_id, facts in by_recipe.items()
    }


async def list_for(cook_id: int, locale: str | None = None) -> list[RecipeSummaryView]:
    locale = locale or await cook_access.locale_for(cook_id)
    summaries = await recipe_access.list_for_cook(cook_id)
    outcomes = await _outcomes_for(cook_id, locale)
    return [
        RecipeSummaryView(
            id=summary.id,
            title=summary.title,
            summary=summary.summary,
            yield_quantity=_view(summary.yield_quantity),
            serves=_servings(summary.serves, Decimal(1)),
            visibility=summary.visibility,
            suitability=outcomes.get(summary.id),
        )
        for summary in summaries
    ]


async def present(
    recipe_id: int,
    cook_id: int,
    locale: str | None = None,
    servings: Decimal | None = None,
) -> PresentedRecipe | None:
    """A recipe at the requested yield, in this cook's units (UC-2.1, UC-2.2).

    `servings` is a magnitude in whatever the recipe itself yields: asking for 6 of a
    recipe that makes 12 biscuits halves it.
    """
    locale = locale or await cook_access.locale_for(cook_id)
    recipe = await recipe_access.fetch(recipe_id, locale)
    if recipe is None or recipe.cook_id != cook_id:
        # Someone else's private recipe is absent, not forbidden: saying "forbidden"
        # confirms it exists.
        return None
    return await _present(recipe, await preference_access.for_cook(cook_id), servings, cook_id)


async def _judge(recipe: Recipe, cook_id: int) -> VerdictView | None:
    """Whether this cook's household can eat this (V5, UC-2.4).

    Shown without being asked for, because the system already knows it and making
    somebody apply a filter to learn it would be a worse interface.

    Nobody described means no verdict, rather than *suitable*. An empty household
    satisfies every constraint there is, and reporting that as a clean bill of health
    would be a reassurance about a question nobody asked.
    """
    household = await eater_access.list_for_cook(cook_id)
    if not household:
        return None

    return VerdictView.of(suitability.evaluate(suitability.facts_for(recipe.lines), household))


async def _present(
    recipe: Recipe, preferences: UnitPreferences, servings: Decimal | None, cook_id: int
) -> PresentedRecipe:
    factor = Decimal(1) if servings is None else servings / recipe.yield_quantity.magnitude
    scaled_yield = measure.scale(recipe.yield_quantity, factor)

    lines = []
    for line in recipe.lines:
        # A line with no quantity is left alone. Twice as much "to taste" is still "to
        # taste", and rendering a zero there would read as an amount.
        rendered = (
            None
            if line.quantity is None
            else measure.render(
                measure.scale(line.quantity, factor),
                line.ingredient.kind,
                line.ingredient.density,
                preferences,
            )
        )
        lines.append(
            PresentedLine(
                ingredient=line.ingredient.name,
                quantity=None if rendered is None else _view(rendered),
                preparation=line.preparation,
                optional=line.optional,
            )
        )

    return PresentedRecipe(
        id=recipe.id,
        title=recipe.title,
        summary=recipe.summary,
        suitability=await _judge(recipe, cook_id),
        yield_quantity=_view(scaled_yield),
        # Scaled with everything else: a doubled batch of "makes 12, serves 4" makes 24
        # and serves 8, and a `serves` left at its written value would be the one number
        # on the page that no longer matched the rest.
        serves=_servings(recipe.serves, factor),
        visibility=recipe.visibility,
        provenance=recipe.provenance,
        lines=lines,
        steps=[
            PresentedStep(
                position=position,
                instruction=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
            )
            for position, step in enumerate(recipe.steps)
        ],
    )


@dataclass(frozen=True, slots=True)
class ImportResult:
    """What an import actually did."""

    recipes_added: int
    ingredients_added: int


async def export_for(cook_id: int, locale: str) -> ExchangeDocument:
    """Everything a cook owns, in the portable format (FR-11)."""
    recipes = await recipe_access.fetch_all_for_cook(cook_id, locale)
    return exchange.to_document(recipes, locale)


async def import_document(
    raw: dict[str, Any], cook_id: int, locale: str | None = None
) -> ImportResult:
    """Read a document into this instance (UC-1.2).

    Slugs are resolved against the local registry and whatever is missing is created, so a
    document is enough on its own. Where an entry already exists the **local** one wins: an
    instance's own densities are its business, and a document should not be able to rewrite
    them.

    The document is validated in full — format version, shape, units, and that every slug
    a recipe refers to is one the document itself defines — before anything is written. A
    half-finished import would leave a cook unable to tell what arrived.

    A recipe may not lean on an ingredient this instance happens to already hold, even
    though resolving it would succeed here. A document that only imports on the machine it
    came from is not portable, and portability is the point of the format (FR-11). Our own
    exporter always declares every ingredient its recipes name.

    That validation is not a transaction. Each write is its own, so a failure *during*
    writing could still leave part of a document imported. Making the whole import atomic
    needs a transaction spanning several access services, which this layer does not offer
    yet; the validation above is what keeps the realistic failures — a bad document — from
    ever reaching that point.
    """
    locale = locale or await cook_access.locale_for(cook_id)
    document = exchange.from_document(raw)

    known = await registry.slugs_present([entry.slug for entry in document.ingredients])
    missing = [entry for entry in document.ingredients if entry.slug not in known]

    referenced = {line.slug for recipe in document.recipes for line in recipe.lines}
    unresolvable = referenced - known - {entry.slug for entry in missing}
    if unresolvable:
        raise UnsupportedDocument(
            f"the document refers to ingredients it does not define: {sorted(unresolvable)}"
        )

    for entry in missing:
        # Imported entries are the importer's own. A document must not be able to forge a
        # seeded row, which an upgrade would then feel free to replace.
        await registry.register(
            slug=entry.slug,
            kind=entry.kind,
            density=entry.density,
            names={document.locale: entry.names},
            allergens=entry.allergens,
        )

    ids = await registry.ids_by_slug(sorted(referenced))
    for recipe in document.recipes:
        await recipe_access.store(
            exchange.to_draft(recipe, ingredient_ids=ids, provenance=Provenance.IMPORTED_JSON),
            cook_id,
        )

    return ImportResult(recipes_added=len(document.recipes), ingredients_added=len(missing))


def _slug_for(name: str) -> str:
    """A registry key for a name nobody has registered yet."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "unnamed"


async def _resolve(lines: list[InterpretedLine], locale: str) -> tuple[dict[str, int], list[str]]:
    """Match each ingredient name against the registry, recording what was new.

    Resolution happens against the registry, never against what a model said (UC-1.3) —
    that is what makes a recipe's allergens knowable at all.

    A name the registry has never seen is **recorded and reported**, not invented and not
    fatal. Refusing a whole import over one unknown word would make the feature useless;
    adding it silently would leave a cook unaware that something needs checking. The new
    entry carries no density and no allergen classification, because nothing is known
    about it — which is why a recipe using one reads as *unknown* rather than as safe.
    """
    resolved: dict[str, int] = {}
    added: list[str] = []
    for line in lines:
        if line.ingredient in resolved:
            continue
        # Most specific first: "large free-range eggs", then "eggs", then "egg". Without
        # this the registry gains a second entry for eggs which nobody has classified,
        # and an egg allergy stops firing on a recipe the registry could have judged.
        found = None
        for candidate in interpretation.candidate_names(line.ingredient):
            found = await registry.resolve(candidate, locale)
            if found is not None:
                break
        if found is not None:
            resolved[line.ingredient] = found.id
            continue
        created = await registry.register(
            slug=_slug_for(line.ingredient),
            kind=IngredientKind.SOLID,
            density=None,
            names={locale: [line.ingredient]},
            origin=Origin.USER,
            # Deliberately not `frozenset()`. Nobody has looked, and examined-and-clear is
            # not the same fact as unexamined (ADR-006).
            allergens=None,
        )
        resolved[line.ingredient] = created.id
        added.append(line.ingredient)
    return resolved, added


#: Which of Quookly's locales a page's declared language maps to. A page saying `de` is
#: German whether it was written in Zurich or Hamburg, and the registry's German names are
#: the ones worth asking with.
_LOCALE_FOR_LANGUAGE = {"de": "de-CH", "fr": "fr-CH", "en": "en-GB"}


async def _reading_locale(content: ReadableContent, cook_id: int, fallback: str) -> str:
    """Which language to resolve this page's ingredients in.

    The page's own declaration first: it knows, and a guess from a short ingredient list
    would be a coin toss. Then the cook's own language, because somebody who reads
    Quookly in German is likely importing German recipes even from a page that does not
    say. English last, which is where the registry is defined.

    Getting this wrong is not a cosmetic failure. "Mehl" asked for in English resolves to
    nothing, becomes a new entry nobody has classified, and the recipe loses the gluten
    the registry knew about.
    """
    if content.language and content.language in _LOCALE_FOR_LANGUAGE:
        return _LOCALE_FOR_LANGUAGE[content.language]
    account = await cook_access.fetch(cook_id)
    if account is not None and account.locale:
        return account.locale
    return fallback


async def import_from_url(url: str, cook_id: int, locale: str | None = None) -> ImportedRecipe:
    """Read a recipe off a page and store it (UC-1.3) — the founding use case.

    The sequence, and only the sequence: fetch, interpret, resolve, store. Each of those
    belongs to a service that knows nothing about the others, which is what lets the
    quality of interpretation change constantly without the shape of importing changing
    at all.
    """
    content = await web.fetch_readable(url)
    read = await interpretation.read_page(content)
    resolve_in = await _reading_locale(
        content, cook_id, locale or await cook_access.locale_for(cook_id)
    )

    if read.yield_magnitude is None or read.yield_unit is None:
        raise YieldUnknown(f"{content.url} does not say how much this makes")

    resolved, added = await _resolve(read.lines, resolve_in)
    draft = RecipeDraft(
        title=read.title,
        summary=read.summary,
        yield_quantity=Quantity(read.yield_magnitude, read.yield_unit),
        serves=read.serves,
        provenance=Provenance.IMPORTED_URL,
        lines=[
            IngredientLineDraft(
                ingredient_id=resolved[line.ingredient],
                quantity=(
                    None
                    if line.magnitude is None or line.unit is None
                    else Quantity(line.magnitude, line.unit)
                ),
                preparation=line.preparation,
                optional=line.optional,
            )
            for line in read.lines
        ],
        steps=[
            StepDraft(
                instruction=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
            )
            for step in read.steps
        ],
    )
    stored = await recipe_access.store(draft, cook_id)
    return ImportedRecipe(
        recipe=await _present(stored, await preference_access.for_cook(cook_id), None, cook_id),
        read_from=read.source,
        source_url=content.url,
        ingredients_added=added,
    )
