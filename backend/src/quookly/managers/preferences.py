"""A cook's unit preferences (UC-6.2).

Thin: read what they have chosen, merge the defaults over the top, and record a change.
It exists because a Client may not call Resource Access, and because "is this a choice or
a default" is a question the store answers in two calls and a caller should not have to
assemble.
"""

from quookly.access import preferences as preference_access
from quookly.contracts.errors import IncompatibleUnits, UnknownUnit
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Unit
from quookly.contracts.preferences import DEFAULT_UNITS, UnitPreferenceView

# What each kind is measured in. A countable is counted; showing eggs in grams is not a
# preference, it is a recipe that cannot render.
_MEASURED_AS = {
    IngredientKind.COUNTABLE: {Unit.PIECE},
}


def _unit(symbol: str) -> Unit:
    for unit in Unit:
        if unit.symbol == symbol:
            return unit
    raise UnknownUnit(symbol)


async def for_cook(cook_id: int) -> list[UnitPreferenceView]:
    """Every kind, with the unit this cook reads it in and whether they picked it.

    Every kind is listed rather than only the chosen ones: a kind missing from the list
    is one a cook can never set.
    """
    preferences = await preference_access.for_cook(cook_id)
    chosen = await preference_access.chosen_kinds(cook_id)
    return [
        UnitPreferenceView(
            kind=kind,
            unit=(preferences.for_kind(kind) or DEFAULT_UNITS[kind]).symbol,
            chosen=kind in chosen,
        )
        for kind in IngredientKind
    ]


async def choose(cook_id: int, kind: IngredientKind, symbol: str) -> list[UnitPreferenceView]:
    """Set the unit for one kind, and return the whole set as it now stands."""
    unit = _unit(symbol)
    allowed = _MEASURED_AS.get(kind)
    if allowed is not None and unit not in allowed:
        raise IncompatibleUnits(f"{kind.value} is counted, not measured in {unit.symbol}")
    await preference_access.choose(cook_id, kind, unit)
    return await for_cook(cook_id)
