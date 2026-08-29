"""The tools themselves.

Grouped the way an evening goes: what could I cook, what is in the kitchen, what does this
word mean, and — once the agent knows the vocabulary — write it down.

Every tool resolves the caller from the same bearer token the API takes, verified by the
same utility. One token is one cook: on a household instance the agent sees what its cook
sees, which is what makes "look at my pantry" a sentence that means something.
"""

from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from pydantic import Field

from quookly.contracts.errors import (
    IngredientNotRegistered,
    UnknownUnit,
    UnsuitableForTheTable,
    YieldUnknown,
)
from quookly.contracts.recipe import IngredientLineInput, RecipeInput, StepInput
from quookly.contracts.security import Principal
from quookly.managers import academy as academy_manager
from quookly.managers import ingredient as ingredient_manager
from quookly.managers import pantry as pantry_manager
from quookly.managers import plan as plan_manager
from quookly.managers import recipe as recipe_manager
from quookly.utilities.security import read_token

_SCHEME = "Bearer"

#: Every refusal below is a `ToolError` rather than a bare exception, and the difference
#: is what the agent is told. A `ToolError` carries its message to the model; anything else
#: reads as "Error executing tool", which cannot be told apart from the kitchen being
#: broken. Half of these refusals exist to say *why* — a recipe somebody cannot eat is
#: refused **with its reasons**, and "no" without a reason is not an answer.
kitchen = MCPServer(
    name="quookly",
    title="Quookly",
    instructions=(
        "This is one household's kitchen: its recipes, its pantry, its meal plan, and a "
        "registry of foods with allergen and nutrition data behind it.\n\n"
        "Two rules matter more than the rest.\n\n"
        "Never work out for yourself whether a recipe suits somebody. Whether a food "
        "contains milk or gluten is computed here from structured data, and this server "
        "will tell you. Reading an ingredient list and concluding 'this is dairy-free' is "
        "the one mistake that can hurt somebody, and a list that looks clear is often a "
        "list nobody has checked.\n\n"
        "When writing a recipe, look every ingredient up with `find_a_food` first and use "
        "the id it gives you. Ingredients are shared across this whole kitchen: reusing "
        "the entry that is already there is what keeps the pantry, the shopping list and "
        "the allergen warnings working. Only add a new food when the search really has "
        "nothing, and know that a new one arrives unexamined — no recipe using it can be "
        "judged for allergens until somebody looks at it."
    ),
)


async def _cook(context: Context[Any, Any]) -> Principal:
    """Who is asking, or a refusal.

    The API's token, read from the API's header, verified by the API's utility — an agent
    is a cook holding one. Every failure is the same refusal, for the same reason it is on
    the HTTP side: missing, malformed, expired and forged tell the caller nothing apart.
    """
    header = (context.headers or {}).get("authorization", "")
    scheme, _, token = header.partition(" ")
    principal = read_token(token) if scheme.lower() == _SCHEME.lower() and token else None
    if principal is None:
        raise ToolError(
            "No usable token. Set an Authorization header of 'Bearer <token>' from a "
            "Quookly sign-in."
        )
    return principal


# --- what is worth cooking ---------------------------------------------------------------


@kitchen.tool(
    description=(
        "What this cook could cook, best first, and why each one is here.\n\n"
        "With words, it searches. Without them, it suggests: what would use up food that "
        "is about to go off, then what needs no shopping trip. Each answer carries its "
        "reasons, what is pressing, and what is missing from the kitchen — so 'we have "
        "everything for this' is something you can say truthfully rather than guess."
    ),
)
async def what_could_i_cook(
    context: Context[Any, Any],
    about: Annotated[
        str | None,
        Field(default=None, description="Words to search for. Leave empty to be suggested to."),
    ] = None,
) -> list[dict[str, Any]]:
    cook = await _cook(context)
    found = await recipe_manager.suggest(cook.cook_id, about)
    return [
        {
            "id": one.recipe.id,
            "title": one.recipe.title,
            "summary": one.recipe.summary,
            "makes": one.recipe.yield_quantity.display,
            "why": [reason.value for reason in one.reasons],
            "uses_up": list(one.pressing),
            # A count, not a list: "nothing to buy" is the sentence that decides an
            # evening, and it is `still_to_buy == 0`.
            "still_to_buy": one.missing,
        }
        for one in found
    ]


@kitchen.tool(
    description=(
        "One recipe in full: its ingredients with quantities, its method, how long it "
        "takes, and — where the household is recorded — whether the people in it can eat "
        "it.\n\n"
        "`serves` rescales the whole thing. The suitability verdict is computed here from "
        "the ingredients; report it as given and do not derive one of your own."
    ),
)
async def read_a_recipe(
    context: Context[Any, Any],
    recipe_id: Annotated[int, Field(description="From what_could_i_cook.")],
    serves: Annotated[
        str | None,
        Field(default=None, description="Rescale to this much of what the recipe makes."),
    ] = None,
) -> dict[str, Any]:
    cook = await _cook(context)
    try:
        wanted = None if serves is None else Decimal(serves)
    except InvalidOperation:
        raise ToolError(f"{serves!r} is not a number.") from None

    shown = await recipe_manager.present(recipe_id, cook.cook_id, servings=wanted)
    if shown is None:
        raise ToolError("No such recipe in this kitchen.")

    return {
        "id": shown.id,
        "title": shown.title,
        "summary": shown.summary,
        "makes": shown.yield_quantity.display,
        "serves": shown.serves,
        "takes": None
        if shown.timing is None
        else {
            "hands_on": shown.timing.hands_on,
            "total": shown.timing.total,
            "start_ahead": shown.timing.ahead,
        },
        "ingredients": [
            {
                "ingredient": line.ingredient,
                "quantity": None if line.quantity is None else line.quantity.display,
                "preparation": line.preparation,
                "optional": line.optional,
            }
            for line in shown.lines
        ],
        "method": [step.instruction for step in shown.steps],
        # The computed answer, not the evidence for one (ADR-006).
        "suits_the_household": None
        if shown.suitability is None
        else {
            "verdict": shown.suitability.outcome.value,
            "because": [
                {
                    "eater": one.eater,
                    "ingredient": one.ingredient,
                    "allergen": None if one.allergen is None else one.allergen.value,
                    "severity": None if one.severity is None else one.severity.value,
                    # A finding nobody has checked is not a finding of nothing. Said out
                    # loud because this is the sentence an agent will paraphrase.
                    "nobody_has_checked": one.unknown,
                    "could_be_left_out": one.avoidable,
                }
                for one in shown.suitability.findings
            ],
        },
        "translated": shown.translated,
        "translated_by_a_person": shown.translated_by_hand,
    }


# --- what is in the kitchen ---------------------------------------------------------------


@kitchen.tool(
    description=(
        "Everything on this cook's shelves: how much of each food, how much of it is "
        "already promised to a planned meal, and the individual packets with their dates."
    ),
)
async def what_is_in_the_pantry(context: Context[Any, Any]) -> list[dict[str, Any]]:
    cook = await _cook(context)
    return [_shelved(entry) for entry in await pantry_manager.present(cook.cook_id)]


@kitchen.tool(
    description=(
        "What wants eating, soonest first — including what is already past its date, "
        "which is the most urgent case rather than one that has stopped mattering.\n\n"
        "This is what to build a suggestion around when somebody wants something made "
        "tonight: the food that gets thrown away is the food nobody remembered."
    ),
)
async def what_needs_using_soon(context: Context[Any, Any]) -> list[dict[str, Any]]:
    cook = await _cook(context)
    return [_shelved(entry) for entry in await pantry_manager.using_soon(cook.cook_id)]


def _shelved(entry: Any) -> dict[str, Any]:
    """One shelf entry, as an agent reads it.

    `spoken_for` travels because the total is what is in the cupboard and not what is free:
    a cook who uses the lot because the number said 800 g leaves Thursday short.
    """
    return {
        "ingredient_id": entry.ingredient_id,
        "name": entry.name,
        "total": entry.total,
        "promised_to_a_meal": entry.spoken_for,
        "packets": [
            {
                "quantity": lot.quantity,
                "use_by": lot.expires_on.isoformat() if lot.expires_on else None,
                "days_left": lot.days_remaining,
                "freshness": lot.freshness.value,
            }
            for lot in entry.lots
        ],
    }


# --- the vocabulary -----------------------------------------------------------------------


@kitchen.tool(
    description=(
        "Find a food in this kitchen's registry, by any name it answers to in any language "
        "this instance speaks.\n\n"
        "**Use this before writing a recipe.** A recipe line takes an `ingredient_id`, and "
        "reusing the entry that already exists is what keeps the pantry, the shopping list "
        "and the allergen warnings joined up. Several answers means several foods, not one "
        "with several names — pick the one you mean, and if none of them is it, say so "
        "rather than picking the nearest.\n\n"
        "Closest match first. The name shown is what this kitchen calls the entry, which "
        "is not always the name you searched for: `salt` answers `fine salt`, because "
        "`salt` is one of that entry's names."
    ),
)
async def find_a_food(
    context: Context[Any, Any],
    named: Annotated[str, Field(description="Part of a name: 'tomato', 'Mehl', 'crème'.")],
) -> list[dict[str, Any]]:
    cook = await _cook(context)
    found = await ingredient_manager.search(named, cook.cook_id)
    return [
        {
            "ingredient_id": one.id,
            "name": one.name,
            # The key `what_is_this_food` takes. Stable across languages, which the id is
            # too — but a slug is readable, and a model that has to hold one is better off
            # holding the readable one.
            "food": one.slug,
            "measured_as": one.kind.value,
        }
        for one in found
    ]


@kitchen.tool(
    description=(
        "What this kitchen knows about one food: what it is called, what it is measured "
        "in, whether anybody has classified its allergens and what they found.\n\n"
        "'Not checked' and 'contains none of the fourteen' are different answers and this "
        "says which. Do not report the first as the second."
    ),
)
async def what_is_this_food(
    context: Context[Any, Any],
    food: Annotated[str, Field(description="The `food` slug from find_a_food.")],
) -> dict[str, Any]:
    await _cook(context)
    detail = await ingredient_manager.detail(food)
    if detail is None:
        raise ToolError("No such food in this registry.")
    found = detail.entry
    return {
        "ingredient_id": found.id,
        "food": found.slug,
        "name": found.name,
        "measured_as": found.kind.value,
        "allergens": [one.value for one in found.allergens],
        # The distinction that matters. An empty list with this false means nobody has
        # looked, which is not the same fact as "contains none of the fourteen" — and
        # reading the first as the second is the failure ADR-006 exists to prevent.
        "anybody_has_checked_the_allergens": found.classified,
        "sits_in": found.category_slug,
        "known_as": detail.names,
    }


@kitchen.tool(
    description=(
        "What a cooking word means, from this instance's Academy — techniques like "
        "'blanch' and 'julienne', and pages about foods.\n\n"
        "Use it when writing a method, so the words are ones this kitchen already "
        "explains and a cook reading the recipe can look them up in place."
    ),
)
async def what_does_this_word_mean(
    context: Context[Any, Any],
    word: Annotated[str, Field(description="A single term: 'blanch', 'unterheben'.")],
) -> list[dict[str, Any]]:
    from quookly.contracts.academy import Reader

    cook = await _cook(context)
    claiming = await academy_manager.claimants(word, Reader(cook_id=cook.cook_id))
    return [{"page": one.slug, "name": one.name, "means": one.summary} for one in claiming]


@kitchen.tool(
    description=(
        "The techniques and terms this Academy explains, so a method can be written in "
        "words the kitchen already knows. Ask once and keep the list."
    ),
)
async def what_words_does_this_kitchen_explain(
    context: Context[Any, Any],
) -> list[dict[str, Any]]:
    from quookly.contracts.academy import Reader

    cook = await _cook(context)
    pages = await academy_manager.browse(Reader(cook_id=cook.cook_id), approved=True)
    return [{"page": one.slug, "name": one.name, "means": one.summary} for one in pages]


# --- writing one down -----------------------------------------------------------------------


@kitchen.tool(
    description=(
        "Write a recipe into this kitchen.\n\n"
        "Every line names an `ingredient_id` from `find_a_food` — there is no way to spell "
        "an ingredient in by name, and that is deliberate: it is what keeps this recipe "
        "joined to the pantry, the shopping list and the allergen warnings. Look each food "
        "up first.\n\n"
        "It is kept as *generated* rather than as something the cook wrote, so they can "
        "tell the two apart, and it is theirs to edit or throw away afterwards.\n\n"
        "If somebody in the household cannot eat it, it is **refused and nothing is "
        "stored**, with the reason. That verdict is computed here from the foods you "
        "picked; do not try to work it out yourself, and do not talk it round."
    ),
)
async def write_a_recipe(
    context: Context[Any, Any],
    title: Annotated[str, Field(description="What the dish is called.")],
    yield_magnitude: Annotated[str, Field(description="How much it makes, as a number.")],
    yield_unit: Annotated[
        str, Field(description="The unit that goes with it: 'piece', 'serving', 'g', 'ml'.")
    ],
    lines: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "The ingredients. Each is {ingredient_id, magnitude, unit, preparation?, "
                "optional?}. Leave magnitude and unit out together for a line the cook "
                "judges — salt to taste, oil for frying."
            )
        ),
    ],
    steps: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "The method, in order. Each is {instruction, duration_seconds?, "
                "temperature_celsius?}. One thing to do per step."
            )
        ),
    ],
    summary: Annotated[str | None, Field(default=None, description="One line.")] = None,
    serves: Annotated[
        str | None,
        Field(default=None, description="How many people, where the yield does not say."),
    ] = None,
) -> dict[str, Any]:
    cook = await _cook(context)
    try:
        # Numbers arrive as strings and are parsed here, the same as on the HTTP side: a
        # JSON float is binary and 0.1 of a gram is not worth losing to that.
        submitted = RecipeInput(
            title=title,
            summary=summary,
            yield_magnitude=Decimal(yield_magnitude),
            yield_unit=yield_unit,
            serves=None if serves is None else Decimal(serves),
            lines=[IngredientLineInput(**line) for line in lines],
            steps=[StepInput(**step) for step in steps],
        )
    except (TypeError, ValueError, InvalidOperation) as wrong:
        raise ToolError(f"That is not a recipe this kitchen can store: {wrong}") from None

    try:
        written = await recipe_manager.accept_written(submitted, cook.cook_id)
    except UnsuitableForTheTable as refused:
        # The reasons, not a bare no. An agent told only "refused" will guess at why, and
        # guessing at why a recipe is unsuitable is the thing to prevent.
        raise ToolError(
            "Not kept: somebody in this household cannot eat it. "
            f"{[one.model_dump(mode='json') for one in refused.verdict.findings]}"
        ) from None
    except IngredientNotRegistered:
        raise ToolError(
            "One of those ingredient ids is not in this registry. Use find_a_food."
        ) from None
    except (UnknownUnit, YieldUnknown) as wrong:
        raise ToolError(str(wrong)) from None

    return {"id": written.id, "title": written.title, "makes": written.yield_quantity.display}


@kitchen.tool(
    description=(
        "Put a recipe on the plan for a day, so the kitchen holds the stock for it and it "
        "reaches the shopping list.\n\n"
        "Additive and reversible: it fills one meal on one day, and the cook can change it "
        "on the plan screen. `servings` says how much of the recipe to make."
    ),
)
async def plan_a_meal(
    context: Context[Any, Any],
    recipe_id: Annotated[int, Field(description="From what_could_i_cook.")],
    on_date: Annotated[str, Field(description="The day, as YYYY-MM-DD.")],
    meal: Annotated[str, Field(description="One of: breakfast, lunch, dinner.")],
    servings: Annotated[
        str | None,
        Field(default=None, description="How much of the recipe, in its own yield unit."),
    ] = None,
) -> dict[str, Any]:
    from datetime import date

    from quookly.contracts.plan import Meal, SlotInput

    cook = await _cook(context)
    try:
        day = date.fromisoformat(on_date)
        sitting = Meal(meal)
        wanted = None if servings is None else Decimal(servings)
    except (ValueError, InvalidOperation) as wrong:
        raise ToolError(str(wrong)) from None

    plan = await plan_manager.current(cook.cook_id)
    if plan is None:
        raise ToolError(
            "There is no week open to plan into. The cook starts one on the plan screen."
        )
    placed = await plan_manager.place(
        plan.id,
        SlotInput(on_date=day, meal=sitting, recipe_id=recipe_id, attendee_ids=[], servings=wanted),
        cook.cook_id,
    )
    if placed is None:
        raise ToolError("That meal could not be planned — it may already have been cooked.")
    return {"planned": True, "on": on_date, "meal": meal}


@kitchen.tool(
    description=(
        "What is still to buy for the week that is planned, and what is already ticked off."
    ),
)
async def what_is_still_to_buy(context: Context[Any, Any]) -> list[dict[str, Any]]:
    cook = await _cook(context)
    plan = await plan_manager.current(cook.cook_id)
    if plan is None:
        return []
    return [
        {"name": line.name, "quantity": line.quantity, "in_the_basket": line.bought}
        for line in plan.shopping
    ]


# --- what can be read rather than called ---------------------------------------------------
#
# A tool call is a question asked and answered; a resource is a thing with an address that
# a host can hold on to and hand to a model as context. An Academy page is the second: it
# is prose written for somebody who does not know a word, it does not change between one
# question and the next, and its address is its slug.
#
# `what_does_this_word_mean` stays a tool, because "which page is this word" is a question
# and not an address — and several pages may answer it (ADR-058).


@kitchen.resource(
    "quookly://academy/{slug}",
    description=(
        "One page of this kitchen's Academy: what a cooking word means, in the cook's language."
    ),
    mime_type="text/markdown",
)
async def academy_page(slug: str) -> str:
    """One page, as prose.

    Read for the instance rather than for a signed-in cook. A resource is fetched by the
    *host* and has no request of its own to carry a token, and what is behind this is what
    a stranger may already read: an approved page, which is a published thing (ADR-063).
    """
    from quookly.contracts.academy import Reader

    page = await academy_manager.read(slug, Reader(cook_id=None, locale=None))
    if page is None or not page.approved:
        raise ResourceError(f"No page called {slug!r} has been published here.")

    written = [f"# {page.name}", "", page.summary, "", page.explanation]
    if page.caution:
        written += ["", f"**Take care.** {page.caution}"]
    if page.spellings:
        written += ["", f"*Also written:* {', '.join(page.spellings)}"]
    return "\n".join(written)


# --- the questions worth having a name for -------------------------------------------------


@kitchen.prompt(
    description=(
        "Work out what to cook tonight from what this kitchen actually has, rather than "
        "from what a recipe site would suggest."
    ),
)
def whats_for_dinner(
    occasion: Annotated[
        str,
        Field(
            default="",
            description="Anything that shapes it: who is coming, how long there is, a mood.",
        ),
    ] = "",
) -> str:
    """The question this whole surface exists to answer, with the kitchen in it.

    A prompt that only said "suggest dinner" would be a prompt with no kitchen in it —
    the model would answer from what it knows about food rather than from what is on
    these shelves, which is the difference between an assistant and a search engine with
    opinions.

    It says *where to look*, not what to conclude. Deciding is the cook's, and the safety
    rules are in the server's own instructions, where they apply to every call rather than
    to the ones somebody happened to start from here.
    """
    asked = f"Tonight: {occasion}.\n\n" if occasion.strip() else ""
    return (
        f"{asked}"
        "Find something to cook from this kitchen, in this order.\n\n"
        "1. Call `what_needs_using_soon`. Food that is about to go off is the strongest "
        "reason to cook one thing rather than another, and it is the food that otherwise "
        "gets thrown away.\n"
        "2. Call `what_could_i_cook`. Each answer says why it is there and how much is "
        "still to buy — `still_to_buy: 0` means everything is already here, which is "
        "usually what decides it on a weeknight.\n"
        "3. Read the one or two that fit with `read_a_recipe` before recommending them, so "
        "what you say about the method is what the method says.\n\n"
        "Then suggest one, in a sentence, and say what makes it the right one — what it "
        "uses up, or that nothing needs buying. If nothing fits, say so and offer to write "
        "something new around what needs using."
    )


@kitchen.prompt(
    description="Write a new recipe around what this kitchen has, without inventing foods.",
)
def write_me_something(
    around: Annotated[
        str, Field(description="What it should be: a dish, a cuisine, a thing to use up.")
    ],
) -> str:
    """Writing one down, with the vocabulary step made explicit.

    The looking-up is not politeness. A line takes an `ingredient_id`, so a model that has
    not searched cannot write the recipe at all — and being told that before it starts is
    the difference between one round trip and several.
    """
    return (
        f"Write a recipe for this kitchen: {around}.\n\n"
        "1. Call `what_needs_using_soon` and `what_is_in_the_pantry` first, and build it "
        "around what is there.\n"
        "2. Call `find_a_food` for every single ingredient and keep the `ingredient_id`. "
        "A recipe line takes an id and cannot take a name, so this is not optional — and "
        "reusing the entry that already exists is what keeps the pantry, the shopping "
        "list and the allergen warnings working.\n"
        "3. Call `what_words_does_this_kitchen_explain` and prefer those words in the "
        "method, so a cook can look them up while reading it.\n"
        "4. Call `write_a_recipe`.\n\n"
        "If it is refused because somebody here cannot eat it, say what the reason was and "
        "offer a change — do not argue with the verdict, and do not work one out yourself."
    )
