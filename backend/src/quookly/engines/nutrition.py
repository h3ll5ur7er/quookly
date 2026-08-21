"""Working out what a recipe contains (V6, UC-2.3).

A rule engine: profiles, the source order and the lines all arrive as arguments, so every
judgement here is a table of cases with nothing to fetch and nothing to mock.

Two of those judgements carry the weight.

**Which table answers.** Composition data is a measurement of a particular food supply, not
a fact about an ingredient — Swiss flour is unfortified and American flour is fortified with
folic acid and iron by law. Sources are tried in a configured order and the first that has
the ingredient answers for it, whole ([ADR-045](../../../doc/07-decisions.md)).

**What cannot be counted.** A line with no weight contributes nothing and says so. A total
that quietly leaves out the butter is worse than no total.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal

from quookly.contracts.errors import DensityRequired, IncompatibleUnits
from quookly.contracts.measure import Dimension, Unit
from quookly.contracts.nutrition import Counted, Nutrient, NutrientProfile, NutritionSource
from quookly.contracts.recipe import IngredientLine
from quookly.engines import measure

#: A hundred grams, which is what every composition table publishes against.
PER = Decimal(100)


def _grams(line: IngredientLine) -> Decimal | None:
    """What this line weighs, or nothing where it cannot be known.

    Three ways to arrive at grams and one way to fail at it. A mass converts directly. A
    volume goes through the registry's density, which is already there for unit conversion.
    A count goes through what one of them weighs — and an egg has no grams until somebody
    says so, which is why that is absent rather than assumed.
    """
    if line.quantity is None:
        return None

    if line.quantity.unit.dimension is Dimension.COUNT:
        each = line.ingredient.piece_grams
        return None if each is None else line.quantity.magnitude * each

    try:
        return measure.convert(line.quantity, Unit.GRAM, line.ingredient.density).magnitude
    except (IncompatibleUnits, DensityRequired):
        return None


def _answering(
    ingredient_id: int,
    profiles: Mapping[int, Mapping[NutritionSource, NutrientProfile]],
    order: Sequence[NutritionSource],
) -> NutrientProfile | None:
    """The first table in the order that has this ingredient.

    Whole, never merged. A value with its protein from Bern and its fibre from Beltsville
    is a number nobody measured, and it would be attributed to both.
    """
    held = profiles.get(ingredient_id, {})
    for source in order:
        if source in held:
            return held[source]
    return None


def _indexed(
    profiles: Sequence[NutrientProfile],
) -> dict[int, dict[NutritionSource, NutrientProfile]]:
    held: dict[int, dict[NutritionSource, NutrientProfile]] = {}
    for one in profiles:
        held.setdefault(one.ingredient_id, {})[one.source] = one
    return held


def count(
    lines: Sequence[IngredientLine],
    profiles: Sequence[NutrientProfile],
    order: Sequence[NutritionSource],
) -> Counted | None:
    """What these lines come to, and what could not be counted (UC-2.3).

    Optional lines are left out, which is the reading the shopping list already takes: a
    recipe without them is a real version of the dish, and two services disagreeing about
    what is being made would be worse than either answer.

    **Nothing to count and nothing countable are different answers.** A recipe with no
    lines has no nutrition. A recipe whose every line went uncounted has no *numbers* — but
    it has a reason, and naming the ingredients no table answered for is more use to a cook
    than silence, and far more use than a column of zeroes reading as a food made of air.
    """
    held = _indexed(profiles)
    amounts: dict[Nutrient, Decimal] = {}
    uncounted: list[str] = []
    sources: list[NutritionSource] = []

    for line in lines:
        if line.optional:
            continue

        weight = _grams(line)
        profile = _answering(line.ingredient.id, held, order)
        if weight is None or profile is None:
            uncounted.append(line.ingredient.name)
            continue

        if profile.source not in sources:
            sources.append(profile.source)
        share = weight / PER
        for nutrient, per_hundred in profile.amounts.items():
            amounts[nutrient] = amounts.get(nutrient, Decimal(0)) + per_hundred * share

    if not amounts and not uncounted:
        return None
    return Counted(amounts=amounts, at_least=bool(uncounted), uncounted=uncounted, sources=sources)


def per_serving(counted: Counted, servings: Decimal | None) -> Counted | None:
    """One plate's worth, or nothing where the recipe does not say how many it feeds.

    How much is in the tray is knowable even when how many it feeds is not (ADR-030), so
    the two are reported separately and only this one goes absent.
    """
    if servings is None or servings <= 0:
        return None
    return Counted(
        amounts={nutrient: amount / servings for nutrient, amount in counted.amounts.items()},
        # A floor divided is still a floor.
        at_least=counted.at_least,
        uncounted=counted.uncounted,
        sources=counted.sources,
    )
