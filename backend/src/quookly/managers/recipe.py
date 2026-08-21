"""The recipe use case family: authoring, listing, and presenting (UC-1.1, UC-2.1, UC-2.2).

Sequences the steps and owns none of the rules. Storage is `RecipeAccess`, preferences are
`PreferenceAccess`, and every quantity decision belongs to `MeasureEngine`.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from quookly.access import eater as eater_access
from quookly.access import ingredient as registry
from quookly.access import preferences as preference_access
from quookly.access import recipe as recipe_access
from quookly.contracts.errors import UnknownUnit, UnsupportedDocument
from quookly.contracts.exchange import ExchangeDocument
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.preferences import UnitPreferences
from quookly.contracts.recipe import (
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
from quookly.contracts.suitability import FindingView, JudgedLine, Outcome, VerdictView
from quookly.engines import exchange, measure, suitability

_UNITS_BY_SYMBOL = {unit.symbol: unit for unit in Unit}


def _unit(symbol: str) -> Unit:
    try:
        return _UNITS_BY_SYMBOL[symbol]
    except KeyError:
        raise UnknownUnit(symbol) from None


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


async def author(submitted: RecipeInput, cook_id: int, locale: str) -> PresentedRecipe:
    """Store a recipe and hand it back as the cook will read it."""
    draft = RecipeDraft(
        title=submitted.title,
        summary=submitted.summary,
        yield_quantity=Quantity(submitted.yield_magnitude, _unit(submitted.yield_unit)),
        provenance=Provenance.AUTHORED,
        lines=[
            IngredientLineDraft(
                ingredient_id=line.ingredient_id,
                quantity=Quantity(line.magnitude, _unit(line.unit)),
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


async def list_for(cook_id: int, locale: str = "en-GB") -> list[RecipeSummaryView]:
    summaries = await recipe_access.list_for_cook(cook_id)
    outcomes = await _outcomes_for(cook_id, locale)
    return [
        RecipeSummaryView(
            id=summary.id,
            title=summary.title,
            summary=summary.summary,
            yield_quantity=_view(summary.yield_quantity),
            visibility=summary.visibility,
            suitability=outcomes.get(summary.id),
        )
        for summary in summaries
    ]


async def present(
    recipe_id: int, cook_id: int, locale: str, servings: Decimal | None = None
) -> PresentedRecipe | None:
    """A recipe at the requested yield, in this cook's units (UC-2.1, UC-2.2).

    `servings` is a magnitude in whatever the recipe itself yields: asking for 6 of a
    recipe that makes 12 biscuits halves it.
    """
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

    facts = [
        suitability.IngredientFacts(
            slug=line.ingredient.slug,
            name=line.ingredient.name,
            allergens=line.ingredient.allergens,
            classified=line.ingredient.classified,
            optional=line.optional,
        )
        for line in recipe.lines
    ]
    verdict = suitability.evaluate(facts, household)
    return VerdictView(
        outcome=verdict.outcome,
        findings=[
            FindingView(
                eater=finding.eater,
                ingredient=finding.ingredient,
                severity=finding.severity,
                allergen=finding.allergen,
                avoidable=finding.avoidable,
                unknown=finding.unknown,
            )
            for finding in verdict.findings
        ],
    )


async def _present(
    recipe: Recipe, preferences: UnitPreferences, servings: Decimal | None, cook_id: int
) -> PresentedRecipe:
    factor = Decimal(1) if servings is None else servings / recipe.yield_quantity.magnitude
    scaled_yield = measure.scale(recipe.yield_quantity, factor)

    lines = []
    for line in recipe.lines:
        scaled = measure.scale(line.quantity, factor)
        rendered = measure.render(
            scaled, line.ingredient.kind, line.ingredient.density, preferences
        )
        lines.append(
            PresentedLine(
                ingredient=line.ingredient.name,
                quantity=_view(rendered),
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


async def import_document(raw: dict[str, Any], cook_id: int, locale: str) -> ImportResult:
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
            RecipeDraft(
                title=recipe.title,
                summary=recipe.summary,
                yield_quantity=recipe.yield_quantity,
                provenance=Provenance.IMPORTED_JSON,
                lines=[
                    IngredientLineDraft(
                        ingredient_id=ids[line.slug],
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
                    )
                    for step in recipe.steps
                ],
            ),
            cook_id,
        )

    return ImportResult(recipes_added=len(document.recipes), ingredients_added=len(missing))
