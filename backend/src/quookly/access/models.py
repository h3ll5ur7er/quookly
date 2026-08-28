"""SQLModel table definitions.

These types never leave the access layer — an import-linter contract enforces it
(ADR-008, ADR-018). Resource access services translate them into `quookly.contracts`.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import DDL, UniqueConstraint, event
from sqlmodel import Field, SQLModel

from quookly.contracts.academy import PageKind
from quookly.contracts.cook import Standing
from quookly.contracts.cooking import SessionOutcome
from quookly.contracts.eater import AgeBand, Severity
from quookly.contracts.execution import Attention
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.measure import Unit
from quookly.contracts.nutrition import Nutrient, NutritionSource
from quookly.contracts.onboarding import SetupStep
from quookly.contracts.pantry import WasteReason
from quookly.contracts.plan import Meal
from quookly.contracts.recipe import Provenance, Visibility


def _now() -> datetime:
    return datetime.now(UTC)


class CookRow(SQLModel, table=True):
    """A cook account as stored."""

    __tablename__ = "cook"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    display_name: str
    password_hash: str
    is_admin: bool = Field(default=False)
    # Whether this account has been let in. Defaults to `APPLIED`: forgetting to set it
    # locks somebody out, which is recoverable, rather than letting a stranger in.
    standing: Standing = Field(default=Standing.APPLIED)
    registered_at: datetime = Field(default_factory=_now)
    # The language this cook chose, as opposed to the one their browser happens to ask
    # for. Absent until they choose, which is what the locale setup step is asking.
    locale: str | None = Field(default=None)


class IngredientRow(SQLModel, table=True):
    """A registry entry. Identity is the slug; names live in `IngredientNameRow`."""

    __tablename__ = "ingredient"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    kind: IngredientKind
    # Grams per millilitre. Absent where converting mass to volume is meaningless.
    density: Decimal | None = Field(default=None, max_digits=8, decimal_places=4)
    origin: Origin = Field(default=Origin.USER)
    # Whether anybody has classified this ingredient's allergens. Absent rows in
    # `ingredient_allergen` mean "contains none" only when this is true.
    allergens_classified: bool = Field(default=False)
    # Whether anybody has reviewed this *entry*. Not the same question as the one above:
    # more than half the shipped registry is unclassified because the published table
    # could not answer, and those rows need no review at all (ADR-051).
    approved: bool = Field(default=False, index=True)
    # What one of them weighs, for the countable ones. Composition tables publish per
    # 100 g, so without this a recipe's eggs cannot be counted towards its nutrition.
    # Absent rather than assumed: eggs come in four sizes, and no table Quookly reads
    # publishes a portion weight.
    piece_grams: Decimal | None = Field(default=None, max_digits=8, decimal_places=2)


class NutrientProfileRow(SQLModel, table=True):
    """One published figure: what 100 g of one ingredient contains, per one table.

    A row per nutrient rather than a column each, so a nutrient a table did not measure is
    a **missing row** rather than a null somebody has to remember to check. That is the
    same distinction the allergen classification makes, and for the same reason: a food
    with no fibre figure is not a food without fibre.

    Several sources can hold the same ingredient at once. Which one answers is decided at
    read time against the instance's configured order, so changing that order is a setting
    rather than a re-import (ADR-045).
    """

    __tablename__ = "nutrient_profile"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "source", "nutrient", name="uq_nutrient_profile"),
    )

    id: int | None = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    source: NutritionSource = Field(index=True)
    nutrient: Nutrient
    # Four places, because a table publishes tenths of a gram and dividing by servings
    # needs somewhere to land.
    amount: Decimal = Field(max_digits=12, decimal_places=4)
    # The published row this came from, so a number on a screen can be traced back to one
    # in a book. Kept per row so a re-import that changes a mapping is visible.
    reference: str


class IngredientNameRow(SQLModel, table=True):
    """What an ingredient is called, in one locale.

    Several rows per ingredient per locale: recipes say cornflour or cornstarch and mean
    one thing, and an import has to resolve either. `normalised` is what lookups match
    on, so a cook typing into a form is not typing a database key.
    """

    __tablename__ = "ingredient_name"
    __table_args__ = (UniqueConstraint("locale", "normalised", name="uq_ingredient_name"),)

    id: int | None = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    locale: str = Field(index=True)
    name: str
    normalised: str = Field(index=True)
    is_canonical: bool = Field(default=False)


class RecipeRow(SQLModel, table=True):
    """A recipe's identity and yield. Its contents are lines and steps."""

    __tablename__ = "recipe"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    title: str
    summary: str | None = Field(default=None)
    yield_magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    yield_unit: Unit
    # How many standard portions this makes, where the yield does not already say. "Makes
    # 12 pancakes" says nothing about how many pancakes feed one person, and without this
    # such a recipe can be scaled to a number of pancakes but never to a table.
    #
    # Absent when `yield_unit` is servings: the yield answers, and storing it twice would
    # be two numbers for one fact.
    serves: Decimal | None = Field(default=None, max_digits=8, decimal_places=2)
    provenance: Provenance
    # The recipe this one is a version of. Nullable and self-referencing: most recipes are
    # not versions of anything, and a version of a version is a perfectly ordinary thing
    # for a cook to make.
    derived_from: int | None = Field(default=None, foreign_key="recipe.id", index=True)
    visibility: Visibility = Field(default=Visibility.PRIVATE)
    origin: Origin = Field(default=Origin.USER)
    # What the prose is written in, as a bare code — `de`, not `de-CH`. Absent where
    # nobody knows: an import from a page with no `<html lang>`, or a recipe stored before
    # this column existed. Nothing can translate out of a language nobody knows, which is
    # a better answer than translating out of a guess (ADR-032).
    language: str | None = Field(default=None)
    # One picture of the dish, as two columns rather than a table: the Academy needs several
    # per page because a technique is shown in stages, and a dish is one photograph. Both
    # or neither — a media id without alt text is a picture some readers do not get.
    picture_media_id: str | None = Field(default=None)
    picture_description: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_now)
    # When this recipe was put away, if it was. Archived rather than deleted because plans,
    # cooked meals and shopping ticks point at it, and a cooked meal that lost its recipe
    # is a hole in a history nobody can fill back in (ADR-059). A timestamp rather than a
    # boolean: it records *when* for the same cost.
    archived_at: datetime | None = Field(default=None, index=True)


class RecipeTranslationRow(SQLModel, table=True):
    """A recipe's prose in one other language.

    Prose only: quantities, durations and temperatures are columns rendered per cook, and
    ingredient names resolve through the registry per locale. A translation therefore
    cannot change what a recipe asks for, and no verdict is affected — no verdict has ever
    consulted prose (ADR-006, ADR-032).
    """

    __tablename__ = "recipe_translation"
    __table_args__ = (UniqueConstraint("recipe_id", "locale", name="uq_recipe_translation"),)

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    #: A bare language code — `de`, not `de-CH`. One translation per language, not per
    #: region: the region is a punctuation habit.
    locale: str = Field(index=True)
    title: str
    summary: str | None = Field(default=None)
    # What this was a translation *of*. A fingerprint of the source prose rather than a
    # `stale` flag: a flag has to be set by everything that edits a recipe, and the one
    # somebody forgets shows a German cook instructions for a step that was rewritten.
    # Compared on read, so editing a recipe needs to know nothing about translations
    # (ADR-064).
    source_fingerprint: str = Field(index=True)
    # Whether a person wrote it. A model's is dropped and derived again when the recipe
    # moves; a person's is kept and stopped being shown, because a model silently
    # overwriting somebody's correction is worse than no correction.
    by_hand: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_now)


class RecipeTranslationStepRow(SQLModel, table=True):
    """One step of a translation. `position` pairs it with the recipe's own step."""

    __tablename__ = "recipe_translation_step"
    __table_args__ = (
        UniqueConstraint("translation_id", "position", name="uq_recipe_translation_step"),
    )

    id: int | None = Field(default=None, primary_key=True)
    translation_id: int = Field(foreign_key="recipe_translation.id", index=True)
    position: int
    instruction: str


class IngredientLineRow(SQLModel, table=True):
    """One ingredient as used in one recipe. `position` is the order it is written in."""

    __tablename__ = "ingredient_line"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    position: int
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    # Absent together for a line the cook judges themselves — salt to taste, oil for
    # frying. Absent is not zero: a stored zero would scale, render and shop as nothing.
    magnitude: Decimal | None = Field(default=None, max_digits=12, decimal_places=4)
    unit: Unit | None = Field(default=None)
    preparation: str | None = Field(default=None)
    optional: bool = Field(default=False)


class StepRow(SQLModel, table=True):
    """One action, in order.

    Duration and temperature are columns rather than numbers inside the instruction, so a
    timer can be offered without parsing prose.
    """

    __tablename__ = "step"

    id: int | None = Field(default=None, primary_key=True)
    recipe_id: int = Field(foreign_key="recipe.id", index=True)
    position: int
    instruction: str
    duration_seconds: int | None = Field(default=None)
    temperature_celsius: int | None = Field(default=None)
    # How much of the cook this step asks for, which is what turns a pile of durations
    # into hands-on and total time (ADR-037). Defaulted rather than nullable: every step
    # asks *something* of the cook, and hands-on is the reading that does not make anybody
    # late. Existing rows take the default, which is right for most of them.
    attention: Attention = Field(default=Attention.HANDS_ON)


class UnitPreferenceRow(SQLModel, table=True):
    """One cook's preferred unit for one kind of ingredient (UC-6.2)."""

    __tablename__ = "unit_preference"
    __table_args__ = (UniqueConstraint("cook_id", "kind", name="uq_unit_preference"),)

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    kind: IngredientKind
    unit: Unit


class IngredientAllergenRow(SQLModel, table=True):
    """One allergen an ingredient contains."""

    __tablename__ = "ingredient_allergen"
    __table_args__ = (UniqueConstraint("ingredient_id", "allergen", name="uq_ingredient_allergen"),)

    id: int | None = Field(default=None, primary_key=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    allergen: Allergen


class EaterRow(SQLModel, table=True):
    """One of the people a cook cooks for.

    Hangs off a cook rather than off an account: most people cooked for never sign in, and
    requiring a login to record a guest's allergy would make the feature useless (ADR-005).
    """

    __tablename__ = "eater"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    name: str
    age_band: AgeBand
    # A multiplier against a standard portion. Decimal, because these are summed and then
    # applied to every quantity in a recipe (FR-18).
    appetite: Decimal = Field(default=Decimal("1"), max_digits=4, decimal_places=2)
    created_at: datetime = Field(default_factory=_now)


class EaterConstraintRow(SQLModel, table=True):
    """One thing an eater avoids, and how seriously.

    `ingredient_slug` is text rather than a foreign key on purpose: somebody avoids
    coriander whether or not the registry has heard of it, and a constraint that waits on
    a registry entry is a constraint that is silently not applied.
    """

    __tablename__ = "eater_constraint"

    id: int | None = Field(default=None, primary_key=True)
    eater_id: int = Field(foreign_key="eater.id", index=True)
    allergen: Allergen | None = Field(default=None)
    ingredient_slug: str | None = Field(default=None)
    severity: Severity


class SetupDeclarationRow(SQLModel, table=True):
    """One setup question this cook has answered with "none" or "the defaults are fine".

    The only stored part of onboarding (ADR-014). Everything else is derived from the
    profile; this exists because no amount of derivation can tell a household where
    nobody has a dietary restriction from one nobody has been asked about (FR-15).
    """

    __tablename__ = "setup_declaration"
    __table_args__ = (UniqueConstraint("cook_id", "step", name="uq_setup_declaration"),)

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    step: SetupStep


class StockItemRow(SQLModel, table=True):
    """One lot in the pantry: some of an ingredient, arrived at one time.

    Lots rather than a running total per ingredient, because expiry belongs to a packet
    and not to an ingredient. Depleted lots keep their row with a magnitude of zero:
    deleting them would break the waste records that point at them, and those are the
    history the product is trying to help a cook shrink.
    """

    __tablename__ = "stock_item"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    unit: Unit
    # A day, not an instant. Nothing in a kitchen goes off at 14:32, and a timestamp
    # would raise a timezone question with no correct answer for a carton of milk.
    expires_on: date | None = Field(default=None, index=True)
    note: str | None = Field(default=None)
    received_at: datetime = Field(default_factory=_now)


class WasteRow(SQLModel, table=True):
    """Something that left the kitchen without being eaten (UC-5.4).

    Its own fact rather than a subtraction from stock. Waste inferred from a falling
    number cannot be told apart from waste that was eaten, and "what did we throw away,
    and why" is a question this product exists to answer.

    The ingredient, magnitude and unit are held here as well as on the lot, so the record
    still reads once the lot behind it is empty — or, later, when waste is recorded for
    something cooked rather than something stocked.
    """

    __tablename__ = "waste"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    stock_item_id: int | None = Field(default=None, foreign_key="stock_item.id", index=True)
    magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    unit: Unit
    reason: WasteReason
    note: str | None = Field(default=None)
    recorded_at: datetime = Field(default_factory=_now)


class MealPlanRow(SQLModel, table=True):
    """A period a cook has planned, or means to.

    Both dates inclusive. A plan for one day starts and ends on that day, which is the
    reading that does not need explaining at every call site.
    """

    __tablename__ = "meal_plan"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    starts_on: date = Field(index=True)
    ends_on: date
    created_at: datetime = Field(default_factory=_now)


class ShoppingTickRow(SQLModel, table=True):
    """One line of a shopping list, marked as already in the basket.

    The quantity is stored alongside, and a tick counts only while the list still asks for
    that much. A cook who ticks 500 g of flour and then plans another loaf needs to see
    flour again — carrying the tick across the change would hide 300 g they have not
    bought. Stale reads as unticked rather than as bought, for the same reason an
    unmeasured line reads as unknown rather than as zero.
    """

    __tablename__ = "shopping_tick"
    __table_args__ = (UniqueConstraint("plan_id", "ingredient_id", name="uq_shopping_tick"),)

    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="meal_plan.id", index=True)
    ingredient_id: int = Field(foreign_key="ingredient.id", index=True)
    magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    unit: Unit
    ticked_at: datetime


class PlanSlotRow(SQLModel, table=True):
    """One meal on one day inside a plan.

    `recipe_id` is nullable because a week is planned in passes: "Thursday, dinner, the
    four of us, something quick" is a real state and has to be storable, or the plan
    cannot be built up the way anybody actually builds one.
    """

    __tablename__ = "plan_slot"
    __table_args__ = (UniqueConstraint("plan_id", "on_date", "meal", name="uq_plan_slot"),)

    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="meal_plan.id", index=True)
    on_date: date = Field(index=True)
    meal: Meal
    recipe_id: int | None = Field(default=None, foreign_key="recipe.id", index=True)
    # How much of the recipe to make, in the recipe's own yield unit. Nullable because
    # most slots are never sized by hand: absent means the rule that applied before
    # anybody could say otherwise — one batch, or as many as the table wants.
    servings: Decimal | None = Field(default=None, max_digits=12, decimal_places=4)
    # When this meal was cooked, if it was. One way: the food is eaten, and un-marking it
    # would mean re-adding stock that never came back — the bug-prone path ADR-004 was
    # written to avoid. A mistake is corrected in the pantry, where quantities are
    # restated anyway.
    cooked_at: datetime | None = Field(default=None)


class SlotAttendeeRow(SQLModel, table=True):
    """One person expected at one planned meal.

    Rows rather than a count: who is coming decides both the portions and the verdict, and
    a number can answer neither (FR-18, UC-4.3).
    """

    __tablename__ = "slot_attendee"
    __table_args__ = (UniqueConstraint("slot_id", "eater_id", name="uq_slot_attendee"),)

    id: int | None = Field(default=None, primary_key=True)
    slot_id: int = Field(foreign_key="plan_slot.id", index=True)
    eater_id: int = Field(foreign_key="eater.id", index=True)


class ReservationRow(SQLModel, table=True):
    """Some of one lot, held aside for one planned meal (ADR-004).

    The row exists exactly while the claim is held: releasing deletes it, and cooking
    decrements the lot and deletes it. No status column, deliberately. A status is a
    second thing to get right, and getting it wrong leaves stock that is neither free nor
    gone — which is the invisible-forever failure ADR-004 exists to avoid.
    """

    __tablename__ = "reservation"

    id: int | None = Field(default=None, primary_key=True)
    stock_item_id: int = Field(foreign_key="stock_item.id", index=True)
    plan_slot_id: int = Field(foreign_key="plan_slot.id", index=True)
    # In the lot's own unit. Nothing here converts, so this is the one unit in which
    # "how much of that packet is still free" is answerable without arithmetic.
    magnitude: Decimal = Field(max_digits=12, decimal_places=4)
    unit: Unit
    created_at: datetime = Field(default_factory=_now)


class CookingSessionRow(SQLModel, table=True):
    """One meal being cooked, and where the cook has got to (ADR-013).

    On the server rather than in the tab, which is the whole of UC-9.7: a phone locks, a
    tablet sleeps, and a cook picks the recipe up in the other room. Client-held progress
    dies with the screen.

    `at_step` is null while the cook is still on the mise-en-place, which is where every
    session begins. Null is not step zero — "getting things ready" and "doing the first
    thing" are different places to come back to.
    """

    __tablename__ = "cooking_session"

    id: int | None = Field(default=None, primary_key=True)
    cook_id: int = Field(foreign_key="cook.id", index=True)
    plan_slot_id: int = Field(foreign_key="plan_slot.id", index=True)
    started_at: datetime = Field(default_factory=_now)
    at_step: int | None = Field(default=None)
    # Both null while the session is open. Set together, and never unset: a session that
    # ended is a record of what happened, and reopening it would be a second history of
    # one meal.
    finished_at: datetime | None = Field(default=None)
    outcome: SessionOutcome | None = Field(default=None)


class CookingTimerRow(SQLModel, table=True):
    """A timer belonging to one step of one session (UC-9.4).

    Instants, never a countdown. `running_since` is when it was last started and is null
    while paused; `elapsed_seconds` is what it had counted before that. Storing *remaining
    seconds* instead goes wrong the moment anything pauses, disconnects or resumes on
    another device, and a reduction that quietly loses four minutes is worse than no timer
    at all.

    A row per step rather than one per session, because a real kitchen has the oven on
    while something else simmers.
    """

    __tablename__ = "cooking_timer"
    __table_args__ = (UniqueConstraint("session_id", "step_position", name="uq_cooking_timer"),)

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="cooking_session.id", index=True)
    step_position: int
    running_since: datetime | None = Field(default=None)
    elapsed_seconds: int = Field(default=0)


#: The full-text index over recipes, as SQLite FTS5 (V10, ADR-009).
#:
#: A virtual table, so SQLModel cannot declare it and alembic cannot autogenerate it. It is
#: written twice on purpose: the migration records what the schema was at that revision, and
#: this records what it is now — which is the same division every other table already has.
#:
#: Hung off `after_create` so that anything building a schema from this metadata gets it.
#: Without that, every test that makes its tables from the models would have an application
#: that indexes into a table which is not there.
SEARCH_INDEX = """
CREATE VIRTUAL TABLE IF NOT EXISTS recipe_search USING fts5(
    recipe_id UNINDEXED,
    cook_id UNINDEXED,
    title,
    ingredients,
    summary,
    tokenize = 'unicode61 remove_diacritics 2'
)
"""

event.listen(SQLModel.metadata, "after_create", DDL(SEARCH_INDEX))  # type: ignore[no-untyped-call]

#: The index and the shadow tables FTS5 keeps beside it. Alembic must be told to leave them
#: alone: they are not in the metadata, so autogenerate would offer to drop them — and a
#: migration that drops the search index every time somebody adds a column is a trap that
#: goes off later, quietly, in production.
SEARCH_TABLES = "recipe_search"


def hand_managed(name: str | None) -> bool:
    """Whether a table is one nothing derives from the models."""
    return name is not None and name.startswith(SEARCH_TABLES)


class AcademyPageRow(SQLModel, table=True):
    """One thing a cook might not know, and what it is. Identity is the slug."""

    __tablename__ = "academy_page"

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    kind: PageKind = Field(index=True)
    origin: Origin = Field(default=Origin.USER)
    # Whether a model wrote it, and separately whether anybody has checked it. Two columns
    # because they are two questions (ADR-051, ADR-056): a cook can write something nobody
    # has read, and an administrator can approve a paragraph a model composed.
    generated: bool = Field(default=False)
    approved: bool = Field(default=False, index=True)
    # Who wrote it, where anybody here did. Null for the pages this instance shipped with,
    # which is the truth rather than a gap: nobody on this instance wrote them. It is what
    # lets an author keep working on their own page before anybody has approved it
    # (ADR-060).
    written_by: int | None = Field(default=None, foreign_key="cook.id", index=True)
    # How an administrator declines one: put away rather than destroyed, the same choice a
    # recipe makes. Out of the Academy and out of the queue, and still there.
    archived_at: datetime | None = Field(default=None, index=True)
    # The registry entry a page of kind `ingredient` is about. Its facts are read from
    # there and never copied here: written twice they disagree, and a paragraph saying
    # "contains no gluten" would be believed by the reader and ignored by the suitability
    # engine (ADR-006, ADR-061). Not unique — several pages may be about one food, and
    # nothing computes on which (ADR-058).
    ingredient_id: int | None = Field(default=None, foreign_key="ingredient.id", index=True)
    created_at: datetime = Field(default_factory=_now)


class AcademyTextRow(SQLModel, table=True):
    """A page as one language writes it."""

    __tablename__ = "academy_text"
    __table_args__ = (UniqueConstraint("page_id", "locale", name="uq_academy_text"),)

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="academy_page.id", index=True)
    locale: str = Field(index=True)
    name: str
    summary: str
    explanation: str
    # Only where getting it wrong matters. Restraint is what keeps a warning worth reading.
    caution: str | None = Field(default=None)


class AcademyTermRow(SQLModel, table=True):
    """A word a page answers to, in one language.

    **Deliberately not unique on `(locale, normalised)`**, which is where this parts
    company with `ingredient_name`. The registry refuses a term a second entry claims,
    because a recipe line resolving to the wrong ingredient gets the wrong food's
    allergens. Nothing computes on a page, so several may claim a term and the page names
    the others at the top (ADR-058). Unique per page instead, so one page cannot list a
    spelling twice.
    """

    __tablename__ = "academy_term"
    __table_args__ = (UniqueConstraint("page_id", "locale", "normalised", name="uq_academy_term"),)

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="academy_page.id", index=True)
    locale: str = Field(index=True)
    spelling: str
    normalised: str = Field(index=True)
    is_canonical: bool = Field(default=False)
    # Whether this term may be spotted in a recipe step. Almost always yes; a canonical
    # name that is also an ordinary word is the exception — German `sieben` is *to sift*
    # and *seven*, and "sieben Minuten" is not about a sieve.
    matchable: bool = Field(default=True, index=True)


class AcademyPictureRow(SQLModel, table=True):
    """A picture on an Academy page.

    `media_id` refers to a file in the media directory rather than holding bytes: a
    database full of photographs is slow to copy and awkward to inspect. Removing this row
    leaves the file, by decision — collecting what is no longer referred to is a job for a
    CLI command, not for a delete somebody did not ask for.

    `description` is the alt text, which accessibility requires and which is therefore not
    optional. It is written in one language and read in every one, the same position a
    recipe is in before translation exists (ADR-032).
    """

    __tablename__ = "academy_picture"

    id: int | None = Field(default=None, primary_key=True)
    page_id: int = Field(foreign_key="academy_page.id", index=True)
    media_id: str = Field(index=True)
    description: str
    #: The language the description is written in, so a reader can be told when it is not
    #: theirs rather than being given English silently.
    locale: str
    position: int = Field(default=0)
