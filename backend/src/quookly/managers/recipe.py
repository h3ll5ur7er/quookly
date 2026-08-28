"""The recipe use case family: authoring, listing, and presenting (UC-1.1, UC-2.1, UC-2.2).

Sequences the steps and owns none of the rules. Storage is `RecipeAccess`, preferences are
`PreferenceAccess`, and every quantity decision belongs to `MeasureEngine`.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from quookly.access import academy as academy_access
from quookly.access import cook as cook_access
from quookly.access import eater as eater_access
from quookly.access import ingredient as registry
from quookly.access import media, search, web
from quookly.access import pantry as pantry_access
from quookly.access import preferences as preference_access
from quookly.access import recipe as recipe_access
from quookly.access import translation as translation_access
from quookly.access.ingredient import SOURCE_LOCALE
from quookly.contracts.discovery import Candidate, SuggestionView
from quookly.contracts.eater import Eater
from quookly.contracts.errors import (
    InferenceNotConfigured,
    InferenceUnavailable,
    NothingToTranslate,
    UnsuitableForTheTable,
    UnsupportedDocument,
    YieldUnknown,
)
from quookly.contracts.exchange import ExchangeDocument
from quookly.contracts.execution import TimingView
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.contracts.interpretation import InterpretedLine, InterpretedRecipe
from quookly.contracts.matching import Mention, MentionView
from quookly.contracts.measure import Quantity
from quookly.contracts.nutrition import (
    CREDITS,
    Counted,
    CreditView,
    Nutrient,
    NutrientView,
    NutritionView,
)
from quookly.contracts.preferences import UnitPreferences
from quookly.contracts.recipe import (
    GenerationInput,
    ImportedRecipe,
    IngredientLine,
    IngredientLineDraft,
    PictureView,
    PresentedRecipe,
    PresentedStep,
    Provenance,
    Recipe,
    RecipeDraft,
    RecipeInput,
    RecipeSummary,
    RecipeSummaryView,
    Step,
    StepDraft,
    VariantInput,
)
from quookly.contracts.suitability import JudgedLine, Outcome, VerdictView
from quookly.contracts.translation import HeldTranslation, Translatable
from quookly.contracts.web import ReadableContent
from quookly.engines import (
    exchange,
    execution,
    generation,
    interpretation,
    matching,
    measure,
    nutrition,
    ranking,
    suitability,
    translation,
)
from quookly.utilities.configuration import preferred_sources
from quookly.utilities.diagnostics import get_logger

log = get_logger("recipe")

#: Resolving a symbol lives in `MeasureEngine`, which owns units. Kept as a local name
#: because it reads better at the call sites than the qualified one.
_unit = measure.unit_for


async def illustrate(
    recipe_id: int, cook_id: int, upload: bytes | None, description: str | None
) -> PresentedRecipe | None:
    """Put a picture on a recipe, or take the one it has off.

    One picture, so a second replaces the first rather than joining it — a card wants a
    thumbnail and a page wants a hero, and the Academy's several-per-page is for a
    technique shown in stages.

    The file is re-encoded and kept beside the database; the recipe holds the id it was
    given. Nothing deletes the previous file: a reference changing is not evidence that
    nobody wants the bytes, and collecting orphans is the CLI's (ADR-057).
    """
    media_id = None if upload is None else await media.store_image(upload)
    if not await recipe_access.illustrate(recipe_id, cook_id, media_id, description):
        return None
    return await present(recipe_id, cook_id)


async def _writing_in(cook_id: int) -> str:
    """The language this cook is writing in: theirs, as a bare code.

    Nobody is asked. Somebody typing a recipe into a German screen is writing German, and
    a form field for it would be a question with an obvious answer — and one more thing to
    get wrong on every recipe (ADR-032).
    """
    return (await cook_access.locale_for(cook_id)).split("-")[0]


def _drafted(
    submitted: RecipeInput, provenance: Provenance, language: str | None = None
) -> RecipeDraft:
    """A submitted recipe as a draft.

    Shared by authoring and by editing so the two cannot come to disagree about what a
    submission means — they take the same body and differ only in what happens to the
    result.
    """
    return RecipeDraft(
        title=submitted.title,
        summary=submitted.summary,
        yield_quantity=Quantity(submitted.yield_magnitude, _unit(submitted.yield_unit)),
        serves=submitted.serves,
        provenance=provenance,
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
                attention=step.attention,
            )
            for step in submitted.steps
        ],
        language=language,
    )


async def author(
    submitted: RecipeInput, cook_id: int, locale: str | None = None
) -> PresentedRecipe:
    """Store a recipe and hand it back as the cook will read it."""
    locale = locale or await cook_access.locale_for(cook_id)
    stored = await recipe_access.store(
        _drafted(submitted, Provenance.AUTHORED, await _writing_in(cook_id)), cook_id
    )
    return await _present(stored, await preference_access.for_cook(cook_id), None, cook_id)


async def restate(
    recipe_id: int, submitted: RecipeInput, cook_id: int, locale: str | None = None
) -> PresentedRecipe | None:
    """Replace a recipe with how it should now read (ADR-059).

    Everyone edits their own. There is no administrator override, because there is no
    account model yet that would make one mean anything — and a cook whose recipe somebody
    else could rewrite would have to be told about it.

    The submitted provenance is ignored: where a recipe came from is a fact about its
    arrival, and `RecipeAccess.restate` will not rewrite it.
    """
    locale = locale or await cook_access.locale_for(cook_id)
    restated = await recipe_access.restate(
        recipe_id,
        _drafted(submitted, Provenance.AUTHORED, await _writing_in(cook_id)),
        cook_id,
    )
    if restated is None:
        return None
    return await _present(restated, await preference_access.for_cook(cook_id), None, cook_id)


async def put_away(recipe_id: int, cook_id: int) -> bool:
    """Archive a recipe: out of the list and the index, still there for what points at it."""
    return await recipe_access.archive(recipe_id, cook_id)


async def bring_back(recipe_id: int, cook_id: int) -> bool:
    """Restore an archived recipe."""
    return await recipe_access.restore(recipe_id, cook_id)


#: How near a date has to be before a recipe using it is worth suggesting. The same
#: three days the pantry marks a packet at: one number for "soon", so the shelf and the
#: suggestion cannot come to disagree about which bag is urgent.
PRESSING_DAYS = 3


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


async def list_for(
    cook_id: int, locale: str | None = None, *, archived: bool = False
) -> list[RecipeSummaryView]:
    locale = locale or await cook_access.locale_for(cook_id)
    summaries = await recipe_access.list_for_cook(cook_id, archived=archived)
    outcomes = await _outcomes_for(cook_id, locale)
    steps = await recipe_access.steps_for_cook(cook_id)
    return [_summary_view(summary, outcomes, steps) for summary in summaries]


def _summary_view(
    summary: RecipeSummary,
    outcomes: Mapping[int, Outcome],
    steps: Mapping[int, list[Step]],
) -> RecipeSummaryView:
    """One row of a list, wherever the list came from.

    Shared by the plain listing and by discovery so a recipe reads the same in both. Two
    copies of this drifted apart the moment one of them learned about timing.
    """
    return RecipeSummaryView(
        id=summary.id,
        title=summary.title,
        summary=summary.summary,
        yield_quantity=measure.viewed(summary.yield_quantity),
        serves=measure.servings_of(summary.serves, Decimal(1)),
        visibility=summary.visibility,
        suitability=outcomes.get(summary.id),
        timing=TimingView.of(execution.timing(steps.get(summary.id, []))),
        picture=(
            None
            if summary.picture is None
            else PictureView(
                media_id=summary.picture.media_id, description=summary.picture.description
            )
        ),
    )


async def suggest(
    cook_id: int, written: str | None = None, locale: str | None = None
) -> list[SuggestionView]:
    """What to cook, best first, and why (UC-3.1, UC-3.3, UC-3.4).

    The read side of discovery, and the sequence it needs is the reason it lives in a
    manager rather than anywhere else: what the index matched, what the pantry holds, what
    is going off, and what the household can eat all have to be gathered before a rule
    engine can put them in an order.

    Discovery is here rather than in a manager of its own because finding a recipe does not
    vary independently of recipes. What *does* vary independently is the order, and that is
    `RankingEngine` (V10).
    """
    reading = locale or await cook_access.locale_for(cook_id)
    summaries = await recipe_access.list_for_cook(cook_id)
    by_id = {summary.id: summary for summary in summaries}

    matched: dict[int, Decimal] | None = None
    if written and written.strip():
        hits = await search.query(written, cook_id)
        matched = {hit.recipe_id: hit.score for hit in hits}
        # A search is a question with an answer set. Suggestions are not: with nothing
        # typed, every recipe is a candidate.
        by_id = {recipe_id: by_id[recipe_id] for recipe_id in matched if recipe_id in by_id}

    if not by_id:
        return []

    outcomes = await _outcomes_for(cook_id, reading)
    steps = await recipe_access.steps_for_cook(cook_id)
    lines = await recipe_access.lines_to_judge(cook_id, reading)
    stocked, pressing = await _what_the_kitchen_holds(cook_id)

    candidates = []
    for recipe_id in by_id:
        # Only the lines a cook has to have. An optional one missing is not a shopping
        # trip, and counting it would make every recipe look further out of reach than it
        # is — the same reading the shopping list takes.
        needed = {line.slug for line in lines if line.recipe_id == recipe_id and not line.optional}
        outcome = outcomes.get(recipe_id)
        candidates.append(
            Candidate(
                recipe_id=recipe_id,
                have=len(needed & stocked),
                needs=len(needed),
                pressing=sorted(name for slug, name in pressing.items() if slug in needed),
                suitable=None if outcome is None else outcome is Outcome.SUITABLE,
                relevance=None if matched is None else matched.get(recipe_id),
            )
        )

    return [
        SuggestionView(
            recipe=_summary_view(by_id[ranked.recipe_id], outcomes, steps),
            reasons=ranked.reasons,
            pressing=ranked.pressing,
            missing=ranked.missing,
        )
        for ranked in ranking.rank(candidates)
    ]


async def _what_the_kitchen_holds(cook_id: int) -> tuple[set[str], dict[str, str]]:
    """Which ingredients are in the pantry, and which of those want eating.

    By slug rather than by id, because that is what a judged line carries — and the slug is
    the same thing in every language, which the name is not.
    """
    held = await pantry_access.list_for_cook(cook_id)
    if not held:
        return set(), {}

    entries = await registry.for_ids(sorted({lot.ingredient_id for lot in held}), SOURCE_LOCALE)
    stocked = {entries[lot.ingredient_id].slug for lot in held if lot.ingredient_id in entries}

    cutoff = _today() + timedelta(days=PRESSING_DAYS)
    soon = await pantry_access.expiring_before(cook_id, cutoff)
    return stocked, {
        entries[lot.ingredient_id].slug: entries[lot.ingredient_id].name
        for lot in soon
        if lot.ingredient_id in entries
    }


def _today() -> date:
    """Today, as a value the tests can hold still. What is pressing is a claim about now."""
    return date.today()


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
    return await _present(
        recipe, await preference_access.for_cook(cook_id), servings, cook_id, locale
    )


#: How much of a figure is worth showing. Energy is a whole number — nobody plates half a
#: kilojoule — and everything else goes to a tenth of a gram, which is the precision a
#: label in this part of the world prints and the precision the tables publish.
_WHOLE = Decimal(1)
_TENTH = Decimal("0.1")


def _shown(nutrient: Nutrient, amount: Decimal) -> str:
    places = _WHOLE if nutrient in {Nutrient.ENERGY_KJ, Nutrient.ENERGY_KCAL} else _TENTH
    rendered = amount.quantize(places, rounding=ROUND_HALF_UP)
    return f"{rendered:f}"


def _nutrients(counted: Counted) -> list[NutrientView]:
    """The figures in the order a label prints them, which is the order a reader expects."""
    return [
        NutrientView(
            nutrient=nutrient,
            amount=_shown(nutrient, counted.amounts[nutrient]),
            unit=nutrient.unit,
        )
        for nutrient in Nutrient
        if nutrient in counted.amounts
    ]


async def _nutrition(recipe: Recipe, factor: Decimal) -> NutritionView | None:
    """What this recipe contains, from whichever table this instance believes (UC-2.3).

    Scaled with everything else. Doubling a tray doubles what is in it, which is the one
    figure on this page where scaling is plain arithmetic rather than a judgement about
    ovens.
    """
    profiles = await registry.profiles_for(sorted({line.ingredient.id for line in recipe.lines}))
    scaled = [
        replace(
            line, quantity=None if line.quantity is None else measure.scale(line.quantity, factor)
        )
        for line in recipe.lines
    ]
    counted = nutrition.count(scaled, profiles, preferred_sources())
    if counted is None:
        return None

    each = nutrition.per_serving(counted, _scaled_servings(recipe, factor))
    return NutritionView(
        per_serving=None if each is None else _nutrients(each),
        per_recipe=_nutrients(counted),
        at_least=counted.at_least,
        uncounted=counted.uncounted,
        credits=[
            CreditView(
                name=CREDITS[source].name,
                publisher=CREDITS[source].publisher,
                licence=CREDITS[source].licence,
                url=CREDITS[source].url,
            )
            for source in counted.sources
        ],
    )


def _scaled_servings(recipe: Recipe, factor: Decimal) -> Decimal | None:
    servings = recipe.servings
    return None if servings is None else servings * factor


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


async def _read_in(recipe: Recipe, locale: str) -> tuple[Recipe, bool]:
    """The same recipe with its prose in the reader's language, where one is wanted.

    Returns it untouched where the recipe is already in that language, where nobody knows
    what language it is in, or where this instance has no model — the last of which is
    what it does today and is not a failure.

    Lazy and kept: derived on first request for a language and stored, rather than eagerly
    at import. Eager translation spends round trips on content nobody may read, and makes
    adding a fourth language a migration over every recipe ever stored instead of a no-op.
    """
    wanted = locale.split("-")[0]
    if recipe.language is None or recipe.language == wanted:
        return recipe, False

    original = Translatable(
        title=recipe.title,
        summary=recipe.summary,
        steps=[step.instruction for step in recipe.steps],
    )
    held = await translation_access.held(recipe.id, wanted, of=original)
    if held is None:
        try:
            said = await translation.render(original, recipe.language, wanted)
        except (InferenceNotConfigured, InferenceUnavailable, NothingToTranslate):
            # Reading the original is a worse answer than reading a translation and a much
            # better one than an error. Logged rather than raised: nothing the cook asked
            # for has failed.
            log.info(
                "no translation of recipe %s into %s; showing it as written", recipe.id, wanted
            )
            return recipe, False
        await translation_access.keep(recipe.id, wanted, said, of=original)
        held = HeldTranslation(words=said, by_hand=False)

    return (
        replace(
            recipe,
            title=held.words.title,
            summary=held.words.summary,
            steps=[
                replace(step, instruction=said_step)
                for step, said_step in zip(recipe.steps, held.words.steps, strict=True)
            ],
        ),
        True,
    )


async def _present(
    recipe: Recipe,
    preferences: UnitPreferences,
    servings: Decimal | None,
    cook_id: int,
    locale: str | None = None,
) -> PresentedRecipe:
    locale = locale or await cook_access.locale_for(cook_id)
    # The prose in the reader's language, where that is not the language it was written
    # in. Everything else on this page is already language-neutral: quantities are columns
    # rendered per cook and ingredient names resolve through the registry (ADR-032).
    recipe, translated = await _read_in(recipe, locale)
    factor = Decimal(1) if servings is None else servings / recipe.yield_quantity.magnitude
    scaled_yield = measure.scale(recipe.yield_quantity, factor)

    lines = measure.rendered_lines(recipe.lines, preferences, factor)

    # Once for the whole recipe rather than once per step: the vocabulary is the same for
    # every step, and a page is a handful of terms. Simple until measurement says otherwise.
    vocabulary, names = await academy_access.vocabulary(locale)
    # Once for the recipe rather than once per step: preparing the vocabulary is most of
    # the cost, and a recipe has one vocabulary and many steps.
    read = matching.read_all([step.instruction for step in recipe.steps], vocabulary)

    return PresentedRecipe(
        id=recipe.id,
        title=recipe.title,
        summary=recipe.summary,
        suitability=await _judge(recipe, cook_id),
        yield_quantity=measure.viewed(scaled_yield),
        # Scaled with everything else: a doubled batch of "makes 12, serves 4" makes 24
        # and serves 8, and a `serves` left at its written value would be the one number
        # on the page that no longer matched the rest.
        serves=measure.servings_of(recipe.serves, factor),
        visibility=recipe.visibility,
        provenance=recipe.provenance,
        language=recipe.language,
        translated=translated,
        picture=(
            None
            if recipe.picture is None
            else PictureView(
                media_id=recipe.picture.media_id, description=recipe.picture.description
            )
        ),
        derived_from=recipe.derived_from,
        derived_from_title=(
            None
            if recipe.derived_from is None
            else (await recipe_access.titles_of([recipe.derived_from])).get(recipe.derived_from)
        ),
        lines=lines,
        steps=[
            PresentedStep(
                position=position,
                instruction=read[position].text,
                written=step.instruction,
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
                attention=step.attention,
                mentions=_marked(read[position].mentions, names),
            )
            for position, step in enumerate(recipe.steps)
        ],
        # Not scaled with the rest. Doubling a tray does not double the time in the oven,
        # and it barely touches the chopping — a factor applied here would be arithmetic
        # producing a number nobody could have measured.
        timing=TimingView.of(execution.timing(recipe.steps)),
        nutrition=await _nutrition(recipe, factor),
    )


def _marked(found: list[Mention], names: dict[str, str]) -> list[MentionView]:
    """The words of one step a cook can look up, as a client reads them.

    Read out of the instruction rather than tagged onto it (ADR-040, ADR-055). The name
    travels with the offsets so a client can label the link without a second request.
    """
    return [
        MentionView(
            slug=one.slug,
            name=names.get(one.slug, one.slug),
            start=one.start,
            end=one.end,
        )
        for one in found
    ]


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


def _draft_from(
    read: InterpretedRecipe,
    resolved: Mapping[str, int],
    provenance: Provenance,
    language: str | None = None,
) -> RecipeDraft:
    """A recipe a model produced, as a draft this instance can store.

    Here rather than in each caller, because two of them build it now — a page that was
    read and a recipe that was asked for — and the last time two places built a draft from
    the same shape, one of them was not remembered when a field was added and the starter
    recipes silently lost how many people they feed (ADR-012).

    The caller has already checked that the yield is readable; a recipe without one cannot
    be scaled and is refused before it gets here.
    """
    assert read.yield_magnitude is not None and read.yield_unit is not None
    return RecipeDraft(
        title=read.title,
        summary=read.summary,
        yield_quantity=Quantity(read.yield_magnitude, read.yield_unit),
        serves=read.serves,
        provenance=provenance,
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
                # Stripped, not stored as written: this instruction came off a page or out
                # of a model, and only a person may say a word means a particular
                # ingredient (ADR-059). A cook can add the link back by editing the step.
                instruction=matching.unlinked(step.instruction),
                duration_seconds=step.duration_seconds,
                temperature_celsius=step.temperature_celsius,
                attention=step.attention,
            )
            for step in read.steps
        ],
        language=language,
    )


def _to_avoid(household: Sequence[Eater]) -> list[str]:
    """What the people at this table cannot eat, in words a model can act on.

    Names rather than codes, because that is what the prompt is for. It changes the odds
    and nothing else: the guarantee is the verdict afterwards, taken from the resolved
    ingredients (ADR-006).
    """
    avoid: list[str] = []
    for eater in household:
        for constraint in eater.constraints:
            named = (
                constraint.allergen.value.replace("_", " ")
                if constraint.allergen is not None
                else (constraint.ingredient_slug or "").replace("-", " ")
            )
            if named and named not in avoid:
                avoid.append(named)
    return avoid


async def generate(
    submitted: GenerationInput, cook_id: int, locale: str | None = None
) -> PresentedRecipe:
    """Write a recipe that did not exist, and only keep it if the table can eat it.

    UC-1.4 and UC-1.5 are one sequence: a description, some ingredients to use up, or both.
    "From my pantry" is this with the pantry filled in, which is a thing the caller does
    rather than a second flow.

    **The safety rule, mechanically.** The household's constraints go into the prompt to
    improve the odds, and the result is then judged independently by `SuitabilityEngine`
    against its *resolved* ingredients. A model asserting "this is dairy-free" carries no
    weight. Where the verdict is anything but suitable the recipe is refused with its
    reasons and nothing is stored — unlike an imported recipe, which exists in the world
    whatever it contains, a generated one was asked for on these people's behalf and
    producing something they cannot eat is a failure of the request.
    """
    reading = locale or await cook_access.locale_for(cook_id)
    household = await eater_access.list_for_cook(cook_id)

    written = await generation.compose(
        description=submitted.description,
        ingredients=await _named(submitted.ingredient_ids, reading),
        constraints=_to_avoid(household),
        serves=submitted.serves,
    )
    if written.yield_magnitude is None or written.yield_unit is None:
        raise YieldUnknown("the recipe that came back does not say how much it makes")

    written = replace(written, steps=await interpretation.tidy_steps(written.steps))
    resolved, _ = await _resolve(written.lines, reading)
    draft = _draft_from(written, resolved, Provenance.GENERATED, await _writing_in(cook_id))

    if household:
        # Judged before it is stored, from the ingredients as the registry knows them.
        # Generation and judgement are separate services precisely so that the judgement
        # cannot be talked out of its conclusion.
        verdict = suitability.evaluate(
            suitability.facts_for(await _lines_as_registered(draft, reading)), household
        )
        if verdict.outcome is not Outcome.SUITABLE:
            raise UnsuitableForTheTable(VerdictView.of(verdict))

    stored = await recipe_access.store(draft, cook_id)
    return await _present(stored, await preference_access.for_cook(cook_id), None, cook_id)


def _as_a_cookbook_prints_it(recipe: Recipe) -> tuple[list[str], list[str]]:
    """A stored recipe's lines and steps as words, for handing to a model.

    Back to text on purpose. A model adapts a recipe better when it is reading a recipe than
    when it is reading a data structure — and the answer comes back in the shape, so the
    question does not have to.
    """
    lines = []
    for line in recipe.lines:
        # Rounded for reading, not for storing. A column keeps 400.0000; a recipe says
        # 400 g, and handing a model the zeros invites it to hand them back.
        written = (
            line.ingredient.name
            if line.quantity is None
            else f"{measure.round_for_display(line.quantity)} {line.ingredient.name}"
        )
        if line.preparation:
            written = f"{written}, {line.preparation}"
        if line.optional:
            written = f"{written} (optional)"
        lines.append(written)
    return lines, [step.instruction for step in recipe.steps]


async def vary(
    recipe_id: int, submitted: VariantInput, cook_id: int, locale: str | None = None
) -> PresentedRecipe | None:
    """Make a version of a recipe the cook already has (UC-1.7).

    The same sequence as writing one outright, with one thing added and one thing changed:
    the original goes into the asking, and what comes back records which recipe it came
    from. A cook looking at a dairy-free shortbread should be one tap from the shortbread.

    Judged the same way and refused the same way. Somebody asking for a *dairy-free* version
    and being handed one with cream in it is the case this rule was written for.
    """
    reading = locale or await cook_access.locale_for(cook_id)
    original = await recipe_access.fetch(recipe_id, reading)
    if original is None or original.cook_id != cook_id:
        return None

    household = await eater_access.list_for_cook(cook_id)
    lines, steps = _as_a_cookbook_prints_it(original)
    written = await generation.vary(
        title=original.title,
        made=str(measure.round_for_display(original.yield_quantity)),
        lines=lines,
        steps=steps,
        change=submitted.change,
        constraints=_to_avoid(household),
    )
    if written.yield_magnitude is None or written.yield_unit is None:
        raise YieldUnknown("the version that came back does not say how much it makes")

    written = replace(written, steps=await interpretation.tidy_steps(written.steps))
    resolved, _ = await _resolve(written.lines, reading)
    draft = replace(
        _draft_from(written, resolved, Provenance.DERIVED, await _writing_in(cook_id)),
        derived_from=original.id,
    )

    if household:
        verdict = suitability.evaluate(
            suitability.facts_for(await _lines_as_registered(draft, reading)), household
        )
        if verdict.outcome is not Outcome.SUITABLE:
            raise UnsuitableForTheTable(VerdictView.of(verdict))

    stored = await recipe_access.store(draft, cook_id)
    return await _present(stored, await preference_access.for_cook(cook_id), None, cook_id)


async def _named(ingredient_ids: Sequence[int], locale: str) -> list[str]:
    """The registry's own names for these ingredients, so the ask is in the cook's words."""
    if not ingredient_ids:
        return []
    entries = await registry.for_ids(sorted(set(ingredient_ids)), locale)
    return [entries[one].name for one in ingredient_ids if one in entries]


async def _lines_as_registered(draft: RecipeDraft, locale: str) -> list[IngredientLine]:
    """A draft's lines with their registry entries attached, ready to be judged.

    The point of the round trip: what gets evaluated is what the *registry* says these
    ingredients are, not what the model called them.
    """
    entries = await registry.for_ids(sorted({line.ingredient_id for line in draft.lines}), locale)
    return [
        IngredientLine(
            id=0,
            ingredient=entries[line.ingredient_id],
            quantity=line.quantity,
            preparation=line.preparation,
            optional=line.optional,
        )
        for line in draft.lines
        if line.ingredient_id in entries
    ]


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
    stored = await recipe_access.store(
        _draft_from(read, resolved, Provenance.IMPORTED_URL, read.language), cook_id
    )
    return ImportedRecipe(
        recipe=await _present(stored, await preference_access.for_cook(cook_id), None, cook_id),
        read_from=read.source,
        source_url=content.url,
        ingredients_added=added,
    )
