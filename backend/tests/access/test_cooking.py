"""Cooking sessions, as stored (UC-9.1, UC-9.3, UC-9.4, UC-9.7).

The one stateful thing in the system, and the one whose failure mode is a cook losing
their place. So the tests here are mostly about interruption: that progress survives being
put down, that a timer counts across a pause, and that a session that ended stays ended.
"""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import cooking as cooking_access
from quookly.access import ingredient as registry
from quookly.access import plan as plan_access
from quookly.access import recipe as recipe_access
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.cooking import SessionOutcome, Timer
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.plan import Meal
from quookly.contracts.recipe import IngredientLineDraft, Provenance, RecipeDraft, StepDraft
from quookly.utilities.configuration import get_settings

MONDAY = date(2026, 8, 24)
AT = datetime(2026, 8, 24, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def cook_id() -> int:
    cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
    return cook.id


@pytest.fixture
async def slot_id(cook_id: int) -> int:
    entry = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=None,
        names={"en-GB": ["plain flour"]},
    )
    recipe = await recipe_access.store(
        RecipeDraft(
            title="Pancakes",
            yield_quantity=Quantity(Decimal("4"), Unit.SERVING),
            provenance=Provenance.AUTHORED,
            lines=[
                IngredientLineDraft(
                    ingredient_id=entry.id, quantity=Quantity(Decimal("250"), Unit.GRAM)
                )
            ],
            steps=[StepDraft(instruction="Whisk it.")],
        ),
        cook_id,
    )
    plan = await plan_access.create(cook_id=cook_id, starts_on=MONDAY, ends_on=MONDAY)
    slot = await plan_access.open_slot(plan.id, on_date=MONDAY, meal=Meal.DINNER)
    await plan_access.assign(slot.id, recipe.id)
    return slot.id


class TestStarting:
    async def test_a_session_begins_on_the_mise_en_place(self, cook_id: int, slot_id: int) -> None:
        """Not on step one. Getting things ready is where cooking starts, and a session
        that opened on the first instruction would have skipped it (UC-9.2)."""
        started = await cooking_access.open_session(cook_id, slot_id)
        assert started.at_step is None

    async def test_a_fresh_session_is_open_and_has_no_timers(
        self, cook_id: int, slot_id: int
    ) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        assert started.open
        assert started.outcome is None
        assert started.timers == []

    async def test_it_comes_back_by_id(self, cook_id: int, slot_id: int) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        assert await cooking_access.fetch(started.id) == started

    async def test_a_session_that_is_not_there(self) -> None:
        assert await cooking_access.fetch(404) is None


class TestFindingTheWayBack:
    """UC-9.7. Cooking is interrupted constantly, and a session nobody can find again is
    a session that died with the screen."""

    async def test_the_meal_being_cooked_finds_its_session(
        self, cook_id: int, slot_id: int
    ) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        assert await cooking_access.open_for_slot(slot_id) == started

    async def test_a_finished_session_is_not_still_being_cooked(
        self, cook_id: int, slot_id: int
    ) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        await cooking_access.close_session(started.id, SessionOutcome.COMPLETED)
        assert await cooking_access.open_for_slot(slot_id) is None

    async def test_a_cook_can_have_more_than_one_pan_on(self, cook_id: int, slot_id: int) -> None:
        """A kitchen has the oven going while something else simmers. A store that could
        hold only one session would have to choose between them."""
        plan = await plan_access.fetch_slot(slot_id)
        assert plan is not None
        other = await plan_access.open_slot(plan.plan_id, on_date=MONDAY, meal=Meal.LUNCH)

        first = await cooking_access.open_session(cook_id, slot_id)
        second = await cooking_access.open_session(cook_id, other.id)

        assert {one.id for one in await cooking_access.open_for_cook(cook_id)} == {
            first.id,
            second.id,
        }

    async def test_another_cooks_session_is_not_in_the_answer(
        self, cook_id: int, slot_id: int
    ) -> None:
        await cooking_access.open_session(cook_id, slot_id)
        other = await cook_access.register("neighbour@example.com", "Someone", "hash")
        assert await cooking_access.open_for_cook(other.id) == []


class TestProgress:
    async def test_the_cook_moves_to_a_step(self, cook_id: int, slot_id: int) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        moved = await cooking_access.advance_step(started.id, 2)
        assert moved is not None
        assert moved.at_step == 2

    async def test_progress_survives_being_put_down(self, cook_id: int, slot_id: int) -> None:
        """The whole of UC-9.7. Read back cold, as another device would."""
        started = await cooking_access.open_session(cook_id, slot_id)
        await cooking_access.advance_step(started.id, 3)
        reread = await cooking_access.fetch(started.id)
        assert reread is not None
        assert reread.at_step == 3

    async def test_the_cook_can_go_back(self, cook_id: int, slot_id: int) -> None:
        """Set rather than incremented: a cook re-reads the step before all the time."""
        started = await cooking_access.open_session(cook_id, slot_id)
        await cooking_access.advance_step(started.id, 3)
        moved = await cooking_access.advance_step(started.id, 1)
        assert moved is not None
        assert moved.at_step == 1

    async def test_the_cook_can_go_back_to_the_prep_list(self, cook_id: int, slot_id: int) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        await cooking_access.advance_step(started.id, 3)
        moved = await cooking_access.advance_step(started.id, None)
        assert moved is not None
        assert moved.at_step is None


class TestTimers:
    async def test_a_timer_is_written_down(self, cook_id: int, slot_id: int) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        held = await cooking_access.record_timer(
            started.id, Timer(step_position=1, running_since=AT, elapsed_seconds=0)
        )
        assert held is not None
        assert held.timers == [Timer(step_position=1, running_since=AT, elapsed_seconds=0)]

    async def test_recording_it_again_replaces_rather_than_adds(
        self, cook_id: int, slot_id: int
    ) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        await cooking_access.record_timer(
            started.id, Timer(step_position=1, running_since=AT, elapsed_seconds=0)
        )
        held = await cooking_access.record_timer(
            started.id, Timer(step_position=1, running_since=None, elapsed_seconds=240)
        )
        assert held is not None
        assert held.timers == [Timer(step_position=1, running_since=None, elapsed_seconds=240)]

    async def test_an_instant_comes_back_as_an_instant(self, cook_id: int, slot_id: int) -> None:
        """Read back with its timezone. A naive datetime out of storage would subtract
        against an aware "now" and raise — a timer that fails on the second tick."""
        started = await cooking_access.open_session(cook_id, slot_id)
        await cooking_access.record_timer(
            started.id, Timer(step_position=0, running_since=AT, elapsed_seconds=0)
        )
        timer = await cooking_access.timer_for(started.id, 0)
        assert timer is not None
        assert timer.running_since is not None
        assert (AT + timedelta(minutes=4) - timer.running_since).total_seconds() == 240

    async def test_each_step_has_its_own(self, cook_id: int, slot_id: int) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        await cooking_access.record_timer(
            started.id, Timer(step_position=0, running_since=AT, elapsed_seconds=0)
        )
        await cooking_access.record_timer(
            started.id, Timer(step_position=2, running_since=None, elapsed_seconds=60)
        )
        held = await cooking_access.fetch(started.id)
        assert held is not None
        assert [timer.step_position for timer in held.timers] == [0, 2]

    async def test_a_step_nobody_timed_has_no_timer(self, cook_id: int, slot_id: int) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        assert await cooking_access.timer_for(started.id, 0) is None


class TestEnding:
    async def test_a_completed_session_says_so(self, cook_id: int, slot_id: int) -> None:
        started = await cooking_access.open_session(cook_id, slot_id)
        ended = await cooking_access.close_session(started.id, SessionOutcome.COMPLETED)
        assert ended is not None
        assert ended.outcome is SessionOutcome.COMPLETED
        assert ended.finished_at is not None
        assert not ended.open

    async def test_an_abandoned_one_is_a_different_fact(self, cook_id: int, slot_id: int) -> None:
        """Not a timeout. The difference between food that was eaten and food that was
        not is the difference this outcome exists to record."""
        started = await cooking_access.open_session(cook_id, slot_id)
        ended = await cooking_access.close_session(started.id, SessionOutcome.ABANDONED)
        assert ended is not None
        assert ended.outcome is SessionOutcome.ABANDONED

    async def test_ending_it_twice_keeps_the_first_ending(self, cook_id: int, slot_id: int) -> None:
        """A retried request must not turn a meal that was eaten into one that was not."""
        started = await cooking_access.open_session(cook_id, slot_id)
        first = await cooking_access.close_session(started.id, SessionOutcome.COMPLETED)
        again = await cooking_access.close_session(started.id, SessionOutcome.ABANDONED)
        assert first is not None
        assert again is not None
        assert again.outcome is SessionOutcome.COMPLETED
        assert again.finished_at == first.finished_at
