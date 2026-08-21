"""How long a recipe takes (V15, UC-2.6, FR-23, ADR-037).

A rule engine: steps arrive as arguments, so every case here is a table row rather than a
fixture. The cases that matter are the ones about absence — a step with no duration must
not contribute zero, because zero is a lie in the direction that makes every recipe look
quicker than it is.
"""

from datetime import UTC, datetime, timedelta

from quookly.contracts.cooking import Timer
from quookly.contracts.execution import Attention, PrepGroup, Span
from quookly.contracts.ingredient import Ingredient, IngredientKind, Origin
from quookly.contracts.recipe import IngredientLine, Step
from quookly.engines import execution

AT = datetime(2026, 8, 21, 18, 0, tzinfo=UTC)


def step(
    seconds: int | None,
    attention: Attention = Attention.HANDS_ON,
    instruction: str = "Do the thing",
) -> Step:
    return Step(
        id=1,
        instruction=instruction,
        duration_seconds=seconds,
        temperature_celsius=None,
        attention=attention,
    )


def test_work_counts_towards_both_numbers() -> None:
    timing = execution.timing([step(300), step(600)])

    assert timing is not None
    assert timing.hands_on == Span(900, at_least=False)
    assert timing.total == Span(900, at_least=False)


def test_waiting_counts_towards_the_total_only() -> None:
    """The whole reason for two numbers. Bread is half an hour of work and a day of
    waiting, and either figure alone sends somebody to the wrong conclusion."""
    timing = execution.timing([step(600), step(5400, Attention.WAITING)])

    assert timing is not None
    assert timing.hands_on == Span(600, at_least=False)
    assert timing.total == Span(6000, at_least=False)


def test_work_done_in_advance_counts_towards_neither() -> None:
    timing = execution.timing([step(28800, Attention.AHEAD), step(600)])

    assert timing is not None
    assert timing.hands_on == Span(600, at_least=False)
    assert timing.total == Span(600, at_least=False)
    assert timing.ahead == Span(28800, at_least=False)


def test_nothing_is_done_in_advance_reads_as_absent() -> None:
    timing = execution.timing([step(600)])

    assert timing is not None
    assert timing.ahead is None


def test_an_untimed_step_makes_its_numbers_a_floor() -> None:
    """Not zero. A recipe of ten steps where one says nothing is *at least* what the
    other nine say, and reporting the sum as exact would be an invention."""
    timing = execution.timing([step(600), step(None)])

    assert timing is not None
    assert timing.hands_on == Span(600, at_least=True)
    assert timing.total == Span(600, at_least=True)


def test_an_untimed_wait_leaves_the_work_exact() -> None:
    """The two numbers are floors separately. A cook who knows the work is twenty minutes
    can decide to start; how long the oven takes is a different question."""
    timing = execution.timing([step(1200), step(None, Attention.WAITING)])

    assert timing is not None
    assert timing.hands_on == Span(1200, at_least=False)
    assert timing.total == Span(1200, at_least=True)


def test_a_recipe_that_says_nothing_about_time_says_nothing() -> None:
    """Absent, not "at least 0 min" — which reads as a fact and is not one."""
    assert execution.timing([step(None), step(None, Attention.WAITING)]) is None


def test_work_nobody_timed_is_absent_rather_than_zero() -> None:
    """Only the baking is timed. "At least 0 min hands-on" would tell a cook the cake
    makes itself."""
    timing = execution.timing([step(None), step(2700, Attention.WAITING)])

    assert timing is not None
    assert timing.hands_on is None
    assert timing.total == Span(2700, at_least=True)


def test_no_steps_at_all() -> None:
    assert execution.timing([]) is None


def test_a_step_says_hands_on_unless_it_says_otherwise() -> None:
    """The safe default (ADR-037): over-reporting the work is the failure that does not
    make anybody late for dinner."""
    assert step(600).attention is Attention.HANDS_ON


def line(name: str, preparation: str | None = None, optional: bool = False) -> IngredientLine:
    return IngredientLine(
        id=1,
        ingredient=Ingredient(
            id=1,
            slug=name.replace(" ", "-"),
            kind=IngredientKind.POWDER,
            name=name,
            density=None,
            origin=Origin.USER,
        ),
        quantity=None,
        preparation=preparation,
        optional=optional,
    )


class TestMiseEnPlace:
    """What to have ready before starting, grouped by the work it wants (UC-9.2)."""

    def test_lines_that_want_the_same_work_are_grouped(self) -> None:
        plan = execution.plan(
            [line("carrot", "finely chopped"), line("onion", "finely chopped")],
            [step(60)],
        )
        assert plan.mise_en_place == [PrepGroup(preparation="finely chopped", lines=[0, 1])]

    def test_different_work_makes_different_groups(self) -> None:
        plan = execution.plan(
            [line("butter", "softened"), line("carrot", "finely chopped")],
            [step(60)],
        )
        assert [group.preparation for group in plan.mise_en_place] == [
            "softened",
            "finely chopped",
        ]

    def test_groups_come_in_the_order_the_recipe_introduces_them(self) -> None:
        """A cook reading down the list should meet them in the order they were written,
        not in whatever order a dictionary happened to hold."""
        plan = execution.plan(
            [line("butter", "softened"), line("carrot", "chopped"), line("shallot", "softened")],
            [step(60)],
        )
        assert plan.mise_en_place == [
            PrepGroup(preparation="softened", lines=[0, 2]),
            PrepGroup(preparation="chopped", lines=[1]),
        ]

    def test_what_wants_nothing_doing_comes_last(self) -> None:
        """The work is what takes the time, so it goes first. Weighing out flour is a
        moment, and putting it at the top would bury the thing worth starting on."""
        plan = execution.plan(
            [line("plain flour"), line("carrot", "chopped")],
            [step(60)],
        )
        assert plan.mise_en_place == [
            PrepGroup(preparation="chopped", lines=[1]),
            PrepGroup(preparation=None, lines=[0]),
        ]

    def test_a_recipe_that_asks_for_no_preparation_still_has_a_list(self) -> None:
        plan = execution.plan([line("plain flour"), line("milk")], [step(60)])
        assert plan.mise_en_place == [PrepGroup(preparation=None, lines=[0, 1])]

    def test_an_optional_line_is_still_something_to_have_ready(self) -> None:
        """Whether to use it is the cook's call, made at the step. Leaving it off the
        bench means going back to the cupboard mid-recipe."""
        plan = execution.plan([line("nutmeg", optional=True)], [step(60)])
        assert plan.mise_en_place == [PrepGroup(preparation=None, lines=[0])]


class TestWhatEachStepNames:
    """Which ingredient lines a step is talking about, derived rather than authored.

    Nobody writing a recipe wants to tag every step with its ingredients, and a recipe
    imported from a page carries no tags at all. The names are already in the instruction;
    matching them is judgement about steps, which is what this engine is for.
    """

    def test_a_step_names_the_ingredient_it_uses(self) -> None:
        plan = execution.plan(
            [line("plain flour"), line("milk")],
            [step(60, instruction="Whisk the plain flour with a little water.")],
        )
        assert plan.steps[0].lines == [0]

    def test_the_word_a_cook_actually_writes_is_matched(self) -> None:
        """Recipes say "the flour", not "the plain flour". A rule that only matched the
        registry's full name would match almost nothing."""
        plan = execution.plan(
            [line("plain flour"), line("whole milk")],
            [step(60, instruction="Beat the flour into the milk.")],
        )
        assert plan.steps[0].lines == [0, 1]

    def test_a_word_two_ingredients_share_matches_neither(self) -> None:
        """ "The flour" in a recipe with plain flour and rye flour is genuinely ambiguous.
        Showing the wrong one at the hob is worse than showing none."""
        plan = execution.plan(
            [line("plain flour"), line("rye flour")],
            [step(60, instruction="Sift the flour.")],
        )
        assert plan.steps[0].lines == []

    def test_naming_one_of_them_in_full_settles_it(self) -> None:
        plan = execution.plan(
            [line("plain flour"), line("rye flour")],
            [step(60, instruction="Sift the rye flour.")],
        )
        assert plan.steps[0].lines == [1]

    def test_a_plural_is_the_same_ingredient(self) -> None:
        plan = execution.plan([line("egg")], [step(60, instruction="Beat the eggs until pale.")])
        assert plan.steps[0].lines == [0]

    def test_a_word_inside_another_word_is_not_a_mention(self) -> None:
        """ "Buttered" is not butter, and "a buttered pan" is not an ingredient line."""
        plan = execution.plan(
            [line("unsalted butter")],
            [step(60, instruction="Fry in a buttered pan.")],
        )
        assert plan.steps[0].lines == []

    def test_a_step_that_names_nothing_names_nothing(self) -> None:
        plan = execution.plan([line("plain flour")], [step(60, instruction="Rest.")])
        assert plan.steps[0].lines == []

    def test_case_is_not_a_difference(self) -> None:
        plan = execution.plan([line("plain flour")], [step(60, instruction="Flour the surface.")])
        assert plan.steps[0].lines == [0]


class TestWorkDoneBeforeStarting:
    """The lead a cook has to know about before tonight (V15, ADR-037)."""

    def test_soaking_overnight_is_lifted_out_of_the_method(self) -> None:
        plan = execution.plan(
            [line("beans")],
            [
                step(28800, Attention.AHEAD, "Soak the beans overnight."),
                step(600, instruction="Drain and rinse."),
            ],
        )
        assert [ahead.position for ahead in plan.ahead] == [0]
        assert [tonight.position for tonight in plan.steps] == [1]

    def test_every_leading_step_that_waits_on_a_day_is_lifted(self) -> None:
        plan = execution.plan(
            [line("beans")],
            [
                step(28800, Attention.AHEAD, "Soak the beans."),
                step(3600, Attention.AHEAD, "Then marinate."),
                step(600, instruction="Cook."),
            ],
        )
        assert [ahead.position for ahead in plan.ahead] == [0, 1]

    def test_chilling_in_the_middle_stays_where_it_is(self) -> None:
        """You cannot chill dough you have not made. Pulling this to the front would
        produce an order nobody could follow."""
        plan = execution.plan(
            [line("plain flour")],
            [
                step(600, instruction="Work the dough."),
                step(28800, Attention.AHEAD, "Chill overnight."),
                step(1200, instruction="Roll and bake."),
            ],
        )
        assert plan.ahead == []
        assert [tonight.position for tonight in plan.steps] == [0, 1, 2]

    def test_a_recipe_with_no_lead_has_none(self) -> None:
        plan = execution.plan([line("plain flour")], [step(600)])
        assert plan.ahead == []

    def test_positions_are_the_recipe_s_own(self) -> None:
        """So a cook can be told "step 4" and find step 4, and so a session resumed on
        another device points at the same instruction."""
        plan = execution.plan(
            [line("beans")],
            [step(60, Attention.AHEAD), step(60), step(60)],
        )
        assert [one.position for one in plan.steps] == [1, 2]


class TestTimers:
    """Instants in, instants out (ADR-013, UC-9.4).

    The rule this has to get right is that no interruption loses time. A cook pauses to
    answer the door, the phone locks, the tablet sleeps, and the reduction is still where
    it was — that is the whole reason the server holds instants rather than a countdown.
    """

    def test_starting_a_timer_records_when(self) -> None:
        running = execution.started(execution.reset(2), AT)
        assert running.running_since == AT
        assert running.elapsed_seconds == 0

    def test_pausing_keeps_what_it_counted(self) -> None:
        running = execution.started(execution.reset(2), AT)
        held = execution.paused(running, AT + timedelta(minutes=4))
        assert held.running_since is None
        assert held.elapsed_seconds == 240

    def test_time_accumulates_across_pauses(self) -> None:
        """The door, then the phone. Four minutes plus three is seven, not three."""
        timer = execution.started(execution.reset(2), AT)
        timer = execution.paused(timer, AT + timedelta(minutes=4))
        timer = execution.started(timer, AT + timedelta(minutes=10))
        timer = execution.paused(timer, AT + timedelta(minutes=13))
        assert timer.elapsed_seconds == 420

    def test_starting_a_running_timer_changes_nothing(self) -> None:
        """A double tap, or a request the client retried. Moving `running_since` forward
        would throw away everything since it was last started."""
        running = execution.started(execution.reset(2), AT)
        assert execution.started(running, AT + timedelta(minutes=4)) == running

    def test_pausing_a_paused_timer_changes_nothing(self) -> None:
        held = execution.paused(execution.started(execution.reset(2), AT), AT)
        assert execution.paused(held, AT + timedelta(minutes=4)) == held

    def test_resetting_puts_it_back_to_nothing(self) -> None:
        timer = execution.paused(
            execution.started(execution.reset(2), AT), AT + timedelta(minutes=4)
        )
        assert execution.reset(timer.step_position) == Timer(
            step_position=2, running_since=None, elapsed_seconds=0
        )

    def test_a_clock_that_runs_backwards_does_not_run_the_timer_backwards(self) -> None:
        """A client's clock can be ahead of the server's. A timer that goes *up* when you
        pause it is a timer nobody believes again."""
        running = execution.started(execution.reset(2), AT)
        held = execution.paused(running, AT - timedelta(minutes=4))
        assert held.elapsed_seconds == 0

    def test_a_running_timer_counts_from_when_it_started(self) -> None:
        running = execution.started(execution.reset(2), AT)
        assert execution.counted(running, AT + timedelta(minutes=4)) == 240

    def test_a_paused_timer_counts_what_it_had(self) -> None:
        held = execution.paused(
            execution.started(execution.reset(2), AT), AT + timedelta(minutes=4)
        )
        assert execution.counted(held, AT + timedelta(hours=3)) == 240
