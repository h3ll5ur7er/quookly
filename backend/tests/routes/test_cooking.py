"""Cooking mode through the API (UC-9.*).

The whole of Phase 5's promise runs through here: a cook starts a session, prepares from
the mise-en-place, runs a timer, puts the phone down, picks the session up somewhere else,
finishes, and finds the pantry updated.

So these tests are mostly about continuity and about the two ways a session can end. The
stock arithmetic is the pantry's and is tested there; what is checked here is that
finishing reaches it and abandoning does not.
"""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app, wire_subscriptions
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.managers import cooking as cooking_manager
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

PLANS = "/api/v1/plans"
SESSIONS = "/api/v1/cooking/sessions"
MONDAY = "2026-08-24"
SUNDAY = "2026-08-30"
AT = datetime(2026, 8, 24, 18, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-test-signing-key-of-sufficient-length-01")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    # The pantry listens for a cooked meal. Without this the sessions would complete and
    # the stock would stay held — which is the failure the subscription exists to prevent.
    wire_subscriptions()
    yield
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def cook(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "chef@example.com")


@pytest.fixture
async def neighbour(client: AsyncClient) -> dict[str, str]:
    return await sign_up(client, "neighbour@example.com")


@pytest.fixture
async def flour() -> int:
    entry = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=Decimal("0.53"),
        names={"en-GB": ["plain flour"]},
    )
    return entry.id


@pytest.fixture
async def butter() -> int:
    entry = await registry.register(
        slug="unsalted-butter",
        kind=IngredientKind.SOLID,
        density=Decimal("0.911"),
        names={"en-GB": ["unsalted butter"]},
    )
    return entry.id


async def a_recipe(client: AsyncClient, headers: dict[str, str], flour: int, butter: int) -> int:
    """Shortbread-shaped: something to soften, something to weigh, and a bake to wait for."""
    created = await client.post(
        "/api/v1/recipes",
        json={
            "title": "Shortbread",
            "yield_magnitude": "4",
            "yield_unit": "serving",
            "lines": [
                {
                    "ingredient_id": butter,
                    "magnitude": "200",
                    "unit": "g",
                    "preparation": "softened",
                },
                {"ingredient_id": flour, "magnitude": "300", "unit": "g"},
            ],
            "steps": [
                {"instruction": "Cream the butter.", "duration_seconds": 300},
                {"instruction": "Work in the flour.", "duration_seconds": 180},
                {
                    "instruction": "Bake until pale gold.",
                    "duration_seconds": 2400,
                    "temperature_celsius": 160,
                    "attention": "waiting",
                },
            ],
        },
        headers=headers,
    )
    return int(created.json()["id"])


async def a_planned_meal(
    client: AsyncClient, headers: dict[str, str], flour: int, butter: int, **overrides: Any
) -> int:
    """A meal on Monday, and the id of the slot holding it."""
    recipe_id = await a_recipe(client, headers, flour, butter)
    plan = await client.post(PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=headers)
    plan_id = plan.json()["id"]
    placed = await client.put(
        f"{PLANS}/{plan_id}/slots",
        json={"on_date": MONDAY, "meal": "dinner", "recipe_id": recipe_id, **overrides},
        headers=headers,
    )
    return int(placed.json()["slots"][0]["id"])


async def a_session(
    client: AsyncClient, headers: dict[str, str], flour: int, butter: int
) -> dict[str, Any]:
    slot_id = await a_planned_meal(client, headers, flour, butter)
    started = await client.post(SESSIONS, json={"plan_slot_id": slot_id}, headers=headers)
    assert started.status_code == 201, started.text
    return dict(started.json())


class TestStarting:
    async def test_signing_in_is_required(self, client: AsyncClient) -> None:
        assert (await client.get(SESSIONS)).status_code == 401

    async def test_a_planned_meal_can_be_cooked(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        assert session["title"] == "Shortbread"
        assert session["outcome"] is None

    async def test_it_begins_on_the_mise_en_place(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Not on step one. Getting things ready is where cooking starts (UC-9.2)."""
        session = await a_session(client, cook, flour, butter)
        assert session["at_step"] is None

    async def test_the_prep_list_groups_the_work_and_leaves_the_weighing_last(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        assert [group["preparation"] for group in session["mise_en_place"]] == ["softened", None]
        assert session["mise_en_place"][0]["lines"][0]["ingredient"] == "unsalted butter"

    async def test_the_prep_list_carries_quantities_a_cook_can_weigh(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        weighed = session["mise_en_place"][1]["lines"][0]
        assert weighed["quantity"]["display"] == "300 g"

    async def test_each_step_carries_the_ingredients_it_names(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """The point of the whole arrangement: no scrolling back at the hob (ADR-040)."""
        session = await a_session(client, cook, flour, butter)
        assert [line["ingredient"] for line in session["steps"][0]["lines"]] == ["unsalted butter"]
        assert [line["quantity"]["display"] for line in session["steps"][1]["lines"]] == ["300 g"]

    async def test_a_meal_with_no_dish_cannot_be_cooked(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """A slot holding nothing was not a meal; there is nothing to follow."""
        plan = await client.post(PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=cook)
        placed = await client.put(
            f"{PLANS}/{plan.json()['id']}/slots",
            json={"on_date": MONDAY, "meal": "dinner"},
            headers=cook,
        )
        slot_id = placed.json()["slots"][0]["id"]

        refused = await client.post(SESSIONS, json={"plan_slot_id": slot_id}, headers=cook)
        assert refused.status_code == 404

    async def test_another_cooks_meal_is_absent_rather_than_forbidden(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        neighbour: dict[str, str],
        flour: int,
        butter: int,
    ) -> None:
        slot_id = await a_planned_meal(client, cook, flour, butter)
        refused = await client.post(SESSIONS, json={"plan_slot_id": slot_id}, headers=neighbour)
        assert refused.status_code == 404

    async def test_a_meal_already_eaten_is_not_cooked_again(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """A second session would take stock for a meal nobody planned."""
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)

        again = await client.post(
            SESSIONS, json={"plan_slot_id": session["plan_slot_id"]}, headers=cook
        )
        assert again.status_code == 404


class TestPickingItUpAgain:
    """UC-9.7, which is not a nicety: phones lock and a session that dies with the screen
    is worse than a printed page."""

    async def test_starting_the_same_meal_returns_the_session_already_running(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        await client.put(f"{SESSIONS}/{session['id']}/step", json={"position": 2}, headers=cook)

        again = await client.post(
            SESSIONS, json={"plan_slot_id": session["plan_slot_id"]}, headers=cook
        )

        assert again.json()["id"] == session["id"]
        assert again.json()["at_step"] == 2

    async def test_what_is_on_the_go_is_findable(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        listed = await client.get(SESSIONS, headers=cook)
        assert [one["id"] for one in listed.json()] == [session["id"]]

    async def test_a_finished_session_is_not_on_the_go(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)
        assert (await client.get(SESSIONS, headers=cook)).json() == []

    async def test_another_cook_sees_none_of_it(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        neighbour: dict[str, str],
        flour: int,
        butter: int,
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        assert (await client.get(SESSIONS, headers=neighbour)).json() == []
        assert (
            await client.get(f"{SESSIONS}/{session['id']}", headers=neighbour)
        ).status_code == 404


class TestWorkingThrough:
    async def test_the_cook_moves_to_a_step(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        moved = await client.put(
            f"{SESSIONS}/{session['id']}/step", json={"position": 1}, headers=cook
        )
        assert moved.status_code == 200
        assert moved.json()["at_step"] == 1

    async def test_the_cook_goes_back_to_the_prep_list(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Absent is a real place rather than a missing answer: a cook returns to the prep
        list to check what else wants chopping."""
        session = await a_session(client, cook, flour, butter)
        await client.put(f"{SESSIONS}/{session['id']}/step", json={"position": 1}, headers=cook)
        moved = await client.put(f"{SESSIONS}/{session['id']}/step", json={}, headers=cook)
        assert moved.json()["at_step"] is None

    async def test_progress_is_there_on_the_other_device(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        await client.put(f"{SESSIONS}/{session['id']}/step", json={"position": 2}, headers=cook)

        reread = await client.get(f"{SESSIONS}/{session['id']}", headers=cook)
        assert reread.json()["at_step"] == 2

    async def test_a_finished_session_is_not_walked_through_again(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """It is a record. Moving through it would be editing history."""
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)

        refused = await client.put(
            f"{SESSIONS}/{session['id']}/step", json={"position": 1}, headers=cook
        )
        assert refused.status_code == 404


class TestTimers:
    """UC-9.4 and ADR-013. The server holds the instant; the client counts."""

    async def test_a_step_has_no_timer_until_one_is_started(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        assert all(step["timer"] is None for step in session["steps"])

    async def test_starting_one_records_when_rather_than_how_long_is_left(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Remaining seconds go wrong the moment anything pauses, disconnects, or resumes
        somewhere else. An instant survives every interruption a kitchen produces."""
        session = await a_session(client, cook, flour, butter)
        started = await client.post(f"{SESSIONS}/{session['id']}/timers/2/started", headers=cook)

        timer = started.json()["steps"][2]["timer"]
        assert timer["running_since"] is not None
        assert timer["elapsed_seconds"] == 0
        # The duration travels with the timer, so a client has one thing to look at.
        assert timer["duration_seconds"] == 2400

    async def test_pausing_keeps_what_it_counted(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        flour: int,
        butter: int,
        monkeypatch: MonkeyPatch,
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        monkeypatch.setattr(cooking_manager, "_now", lambda: AT)
        await client.post(f"{SESSIONS}/{session['id']}/timers/2/started", headers=cook)
        monkeypatch.setattr(cooking_manager, "_now", lambda: AT + timedelta(minutes=4))
        paused = await client.post(f"{SESSIONS}/{session['id']}/timers/2/paused", headers=cook)

        timer = paused.json()["steps"][2]["timer"]
        assert timer["running_since"] is None
        assert timer["elapsed_seconds"] == 240

    async def test_time_survives_the_phone_locking(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        flour: int,
        butter: int,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """The whole reason the session is on the server. Read back cold, as the tablet in
        the other room would."""
        session = await a_session(client, cook, flour, butter)
        monkeypatch.setattr(cooking_manager, "_now", lambda: AT)
        await client.post(f"{SESSIONS}/{session['id']}/timers/2/started", headers=cook)

        reread = await client.get(f"{SESSIONS}/{session['id']}", headers=cook)
        assert reread.json()["steps"][2]["timer"]["running_since"] is not None

    async def test_resetting_puts_it_back_to_nothing(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        flour: int,
        butter: int,
        monkeypatch: MonkeyPatch,
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        monkeypatch.setattr(cooking_manager, "_now", lambda: AT)
        await client.post(f"{SESSIONS}/{session['id']}/timers/2/started", headers=cook)
        monkeypatch.setattr(cooking_manager, "_now", lambda: AT + timedelta(minutes=4))
        reset = await client.post(f"{SESSIONS}/{session['id']}/timers/2/reset", headers=cook)

        timer = reset.json()["steps"][2]["timer"]
        assert timer["running_since"] is None
        assert timer["elapsed_seconds"] == 0

    async def test_a_second_tap_does_not_throw_away_the_first(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        flour: int,
        butter: int,
        monkeypatch: MonkeyPatch,
    ) -> None:
        """The failure mode of this design, arriving through a double tap or a retry."""
        session = await a_session(client, cook, flour, butter)
        monkeypatch.setattr(cooking_manager, "_now", lambda: AT)
        first = await client.post(f"{SESSIONS}/{session['id']}/timers/2/started", headers=cook)
        monkeypatch.setattr(cooking_manager, "_now", lambda: AT + timedelta(minutes=4))
        again = await client.post(f"{SESSIONS}/{session['id']}/timers/2/started", headers=cook)

        assert (
            again.json()["steps"][2]["timer"]["running_since"]
            == first.json()["steps"][2]["timer"]["running_since"]
        )

    async def test_another_cook_cannot_touch_it(
        self,
        client: AsyncClient,
        cook: dict[str, str],
        neighbour: dict[str, str],
        flour: int,
        butter: int,
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        refused = await client.post(
            f"{SESSIONS}/{session['id']}/timers/2/started", headers=neighbour
        )
        assert refused.status_code == 404


class TestFinishing:
    async def test_finishing_takes_what_the_meal_was_holding_out_of_the_pantry(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Phase 5's promise, end to end: cook a meal, and the stock is gone."""
        slot_id = await a_planned_meal(client, cook, flour, butter)
        # Planning already reserved against this. Cooking is what spends it.
        held = await pantry_access.list_for_cook(1)
        assert held == []

        await pantry_access.receive(
            cook_id=1,
            ingredient_id=flour,
            quantity=Quantity(Decimal("1000"), Unit.GRAM),
            expires_on=None,
            note=None,
        )
        # Re-state the meal so the plan reserves against the stock that now exists.
        plans = await client.get(PLANS, headers=cook)
        plan_id = plans.json()[0]["id"]
        plan = await client.get(f"{PLANS}/{plan_id}", headers=cook)
        recipe_id = plan.json()["slots"][0]["recipe_id"]
        await client.put(
            f"{PLANS}/{plan_id}/slots",
            json={"on_date": MONDAY, "meal": "dinner", "recipe_id": recipe_id},
            headers=cook,
        )

        started = await client.post(SESSIONS, json={"plan_slot_id": slot_id}, headers=cook)
        await client.post(f"{SESSIONS}/{started.json()['id']}/completed", headers=cook)

        remaining = await pantry_access.list_for_cook(1)
        assert [lot.quantity.magnitude for lot in remaining] == [Decimal("700")]

    async def test_finishing_marks_the_meal_cooked_on_the_plan(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """One record of a meal, whichever way the cook got there."""
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)

        plans = await client.get(PLANS, headers=cook)
        plan = await client.get(f"{PLANS}/{plans.json()[0]['id']}", headers=cook)
        assert plan.json()["slots"][0]["cooked"] is True

    async def test_a_finished_session_says_how_it_ended(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        finished = await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)
        assert finished.json()["outcome"] == "completed"
        assert finished.json()["finished_at"] is not None

    async def test_finishing_twice_is_the_same_meal(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """A retried request. Consuming none consumes nothing, so the second lands
        harmlessly (ADR-039)."""
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)
        again = await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)
        assert again.status_code == 200
        assert again.json()["outcome"] == "completed"


class TestGivingUp:
    async def test_abandoning_says_so(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        session = await a_session(client, cook, flour, butter)
        given_up = await client.post(f"{SESSIONS}/{session['id']}/abandoned", headers=cook)
        assert given_up.json()["outcome"] == "abandoned"

    async def test_the_meal_is_not_marked_cooked(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Nothing was eaten. Recording it as a meal would put food in the record that
        nobody ate."""
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/abandoned", headers=cook)

        plans = await client.get(PLANS, headers=cook)
        plan = await client.get(f"{PLANS}/{plans.json()[0]['id']}", headers=cook)
        assert plan.json()["slots"][0]["cooked"] is False

    async def test_the_meal_keeps_its_claim_on_the_stock(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Giving up on cooking does not un-plan Thursday's dinner. Releasing what it was
        holding would take it off the shopping list at the same time (ADR-038)."""
        await pantry_access.receive(
            cook_id=1,
            ingredient_id=flour,
            quantity=Quantity(Decimal("1000"), Unit.GRAM),
            expires_on=None,
            note=None,
        )
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/abandoned", headers=cook)

        remaining = await pantry_access.list_for_cook(1)
        assert [lot.quantity.magnitude for lot in remaining] == [Decimal("1000")]
        held = await pantry_access.held_for_slot(session["plan_slot_id"])
        assert [one.quantity.magnitude for one in held] == [Decimal("300")]

    async def test_the_meal_can_be_cooked_again_after_giving_up(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """A cook who stopped and came back later is cooking the same dinner."""
        session = await a_session(client, cook, flour, butter)
        await client.post(f"{SESSIONS}/{session['id']}/abandoned", headers=cook)

        again = await client.post(
            SESSIONS, json={"plan_slot_id": session["plan_slot_id"]}, headers=cook
        )
        assert again.status_code == 201
        assert again.json()["id"] != session["id"]


class TestCookingSomethingNobodyPlanned:
    """UC-9.1b. A cook opens a recipe and decides to make it now. There is no slot, and
    everything in cooking mode hangs off one.

    What happens instead of a special case: the meal is *put on the plan* and then cooked
    by the path that already exists. That is not a workaround. ADR-042 says the plan is
    where a meal is recorded and where "what did we eat on Tuesday" is answered, and a
    meal somebody actually cooked is the strongest example of one worth recording.
    """

    async def start(self, client: AsyncClient, headers: dict[str, str], recipe_id: int) -> Any:
        return await client.post(
            f"{SESSIONS}/for-recipe", json={"recipe_id": recipe_id}, headers=headers
        )

    async def test_a_recipe_can_be_cooked_without_planning_it_first(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        recipe_id = await a_recipe(client, cook, flour, butter)
        started = await self.start(client, cook, recipe_id)
        assert started.status_code == 201, started.text
        assert started.json()["title"] == "Shortbread"

    async def test_it_is_a_session_like_any_other(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """The prep list, the steps and the timers are the same ones. A second kind of
        session would be a second thing to keep working."""
        recipe_id = await a_recipe(client, cook, flour, butter)
        session = (await self.start(client, cook, recipe_id)).json()
        assert session["mise_en_place"]
        assert session["steps"]
        assert session["at_step"] is None

    async def test_the_meal_lands_on_the_plan(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """So that a week's record includes what was improvised in it, and so the stock it
        used comes out of the pantry by the path that already does that."""
        recipe_id = await a_recipe(client, cook, flour, butter)
        await self.start(client, cook, recipe_id)
        plan = (await client.get(f"{PLANS}/current", headers=cook)).json()
        assert [slot["recipe_id"] for slot in plan["slots"]] == [recipe_id]

    async def test_it_is_put_in_the_week_already_being_cooked(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Not in a plan of its own. A cook who improvises on a Wednesday of a planned week
        should find it in that week, beside everything else they meant to eat."""
        recipe_id = await a_recipe(client, cook, flour, butter)
        today = date.today()
        opened = await client.post(
            PLANS,
            json={
                "starts_on": (today - timedelta(days=2)).isoformat(),
                "ends_on": (today + timedelta(days=4)).isoformat(),
            },
            headers=cook,
        )
        await self.start(client, cook, recipe_id)
        plans = (await client.get(PLANS, headers=cook)).json()
        assert [plan["id"] for plan in plans] == [opened.json()["id"]]

    async def test_a_week_that_has_already_ended_is_not_written_into(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """A plan is a period. A meal cooked today does not belong in one that finished
        last month, whatever the plan screen happens to be showing."""
        recipe_id = await a_recipe(client, cook, flour, butter)
        stale = await client.post(
            PLANS, json={"starts_on": "2026-01-05", "ends_on": "2026-01-11"}, headers=cook
        )
        await self.start(client, cook, recipe_id)
        plans = (await client.get(PLANS, headers=cook)).json()
        assert len(plans) == 2
        placed = [plan for plan in plans if plan["id"] != stale.json()["id"]]
        assert len(placed) == 1

    async def test_cooking_two_things_in_one_evening_opens_one_plan_not_two(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        recipe_id = await a_recipe(client, cook, flour, butter)
        await self.start(client, cook, recipe_id)
        await self.start(client, cook, recipe_id)
        assert len((await client.get(PLANS, headers=cook)).json()) == 1

    async def test_starting_the_same_recipe_twice_resumes_rather_than_restarts(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """Same reason as a planned meal: a cook who reopened the app came back to what
        they were doing, and a second session throws away every timer."""
        recipe_id = await a_recipe(client, cook, flour, butter)
        first = (await self.start(client, cook, recipe_id)).json()
        again = (await self.start(client, cook, recipe_id)).json()
        assert again["id"] == first["id"]

    async def test_what_it_used_comes_out_of_the_pantry(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """The test that caught the first version of this.

        Cooking outright used to open the slot through the store directly. Everything
        looked right — the session ran, the meal appeared on the plan, it was marked
        cooked — and the flour never moved, because stock is consumed against a claim and
        nothing had claimed any. Going through `PlanManager.place` is what makes the
        claim, and this is the assertion that says so (ADR-042).
        """
        stocked = await client.post(
            "/api/v1/pantry",
            json={"ingredient_id": flour, "magnitude": "1", "unit": "kg"},
            headers=cook,
        )
        assert stocked.status_code == 201, stocked.text

        recipe_id = await a_recipe(client, cook, flour, butter)
        session = (await self.start(client, cook, recipe_id)).json()
        finished = await client.post(f"{SESSIONS}/{session['id']}/completed", headers=cook)
        assert finished.status_code == 200, finished.text

        shelf = (await client.get("/api/v1/pantry", headers=cook)).json()
        held = next(entry for entry in shelf if entry["ingredient_id"] == flour)
        # 1 kg less the 300 g the recipe asks for, at the yield it is written at.
        assert held["total"] == "700 g"

    async def test_a_recipe_that_is_not_there_is_not_cooked(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        assert (await self.start(client, cook, 9999)).status_code == 404

    async def test_signing_in_is_required(self, client: AsyncClient) -> None:
        assert (
            await client.post(f"{SESSIONS}/for-recipe", json={"recipe_id": 1})
        ).status_code == 401
