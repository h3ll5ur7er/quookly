"""The recipe use case family: authoring, listing, and presenting (UC-1.1, UC-2.1, UC-2.2).

Sequences the steps and owns none of the rules. Storage is `RecipeAccess`, preferences are
`PreferenceAccess`, and every quantity decision belongs to `MeasureEngine`.
"""

from decimal import Decimal

from quookly.access import preferences as preference_access
from quookly.access import recipe as recipe_access
from quookly.contracts.errors import UnknownUnit
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
from quookly.engines import measure

_UNITS_BY_SYMBOL = {unit.symbol: unit for unit in Unit}


def _unit(symbol: str) -> Unit:
    try:
        return _UNITS_BY_SYMBOL[symbol]
    except KeyError:
        raise UnknownUnit(symbol) from None


def _view(quantity: Quantity) -> QuantityView:
    return QuantityView(
        magnitude=str(quantity.magnitude), unit=quantity.unit.symbol, display=str(quantity)
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
    return await _present(stored, await preference_access.for_cook(cook_id), None)


async def list_for(cook_id: int) -> list[RecipeSummaryView]:
    summaries = await recipe_access.list_for_cook(cook_id)
    return [
        RecipeSummaryView(
            id=summary.id,
            title=summary.title,
            summary=summary.summary,
            yield_quantity=_view(summary.yield_quantity),
            visibility=summary.visibility,
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
    return await _present(recipe, await preference_access.for_cook(cook_id), servings)


async def _present(
    recipe: Recipe, preferences: UnitPreferences, servings: Decimal | None
) -> PresentedRecipe:
    factor = (
        Decimal(1) if servings is None else servings / recipe.yield_quantity.magnitude
    )
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
        yield_quantity=_view(measure.round_for_display(scaled_yield)),
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
