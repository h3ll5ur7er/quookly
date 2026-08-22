"""Plans through the API (UC-4.1 to UC-4.4).

The boundary rather than the arithmetic: that a week belongs to exactly one cook, that
stating a meal returns the whole plan because the shopping list moved with it, and that
deleting a plan gives its stock back rather than leaving it spoken for.
"""

from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access import pantry as pantry_access
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.events import MealCooked
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.managers import pantry as pantry_manager
from quookly.managers import plan as plan_manager
from quookly.utilities import events
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

PLANS = "/api/v1/plans"
MONDAY = "2026-08-24"
TUESDAY = "2026-08-25"
SUNDAY = "2026-08-30"


@pytest.fixture(autouse=True)
async def in_memory_database(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-test-signing-key-of-sufficient-length-01")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
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
    """A second ingredient, for asking about a line that is not on the list."""
    entry = await registry.register(
        slug="unsalted-butter",
        kind=IngredientKind.SOLID,
        density=Decimal("0.911"),
        names={"en-GB": ["unsalted butter"]},
    )
    return entry.id


async def a_recipe(client: AsyncClient, headers: dict[str, str], flour: int) -> int:
    """One that serves four, so every quantity follows from that."""
    created = await client.post(
        "/api/v1/recipes",
        json={
            "title": "Pancakes",
            "yield_magnitude": "4",
            "yield_unit": "serving",
            "lines": [{"ingredient_id": flour, "magnitude": "200", "unit": "g"}],
            "steps": [{"instruction": "Whisk."}],
        },
        headers=headers,
    )
    return int(created.json()["id"])


async def a_week(client: AsyncClient, headers: dict[str, str]) -> int:
    created = await client.post(
        PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=headers
    )
    return int(created.json()["id"])


def slot(**overrides: Any) -> dict[str, Any]:
    return {"on_date": MONDAY, "meal": "dinner", **overrides}


async def test_signing_in_is_required(client: AsyncClient) -> None:
    assert (await client.get(PLANS)).status_code == 401


async def test_a_week_opens_empty(client: AsyncClient, cook: dict[str, str]) -> None:
    created = await client.post(PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=cook)

    assert created.status_code == 201
    assert created.json()["slots"] == []
    assert created.json()["shopping"] == []


async def test_a_plan_that_ends_before_it_begins_is_refused(
    client: AsyncClient, cook: dict[str, str]
) -> None:
    response = await client.post(PLANS, json={"starts_on": SUNDAY, "ends_on": MONDAY}, headers=cook)

    assert response.status_code == 422


async def test_stating_a_meal_returns_the_whole_plan(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    """Because the shopping list moved with it, and a client that worked out how would be
    a second copy of the manager."""
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)

    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )

    assert placed.status_code == 200
    assert placed.json()["slots"][0]["recipe_title"] == "Pancakes"
    assert [line["quantity"] for line in placed.json()["shopping"]] == ["200 g"]


async def test_a_slot_is_stated_rather_than_repeated(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)

    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)
    again = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )

    assert len(again.json()["slots"]) == 1


async def test_reading_a_plan_does_not_change_it(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )

    read = await client.get(f"{PLANS}/{plan_id}", headers=cook)

    assert read.status_code == 200
    assert read.json() == placed.json()


async def test_clearing_a_meal_hands_back_the_plan_without_it(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )
    slot_id = placed.json()["slots"][0]["id"]

    cleared = await client.delete(f"{PLANS}/{plan_id}/slots/{slot_id}", headers=cook)

    assert cleared.status_code == 200
    assert cleared.json()["slots"] == []
    assert cleared.json()["shopping"] == []


async def test_a_plan_can_be_forgotten(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)

    assert (await client.delete(f"{PLANS}/{plan_id}", headers=cook)).status_code == 204
    assert (await client.get(f"{PLANS}/{plan_id}", headers=cook)).status_code == 404


async def test_a_plan_is_listed_with_how_much_of_it_is_planned(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)
    await client.put(f"{PLANS}/{plan_id}/slots", json=slot(meal="lunch"), headers=cook)

    listed = await client.get(PLANS, headers=cook)

    assert listed.json() == [{"id": plan_id, "starts_on": MONDAY, "ends_on": SUNDAY, "planned": 1}]


async def test_one_cooks_week_is_not_anothers(
    client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
) -> None:
    plan_id = await a_week(client, cook)

    assert (await client.get(PLANS, headers=neighbour)).json() == []
    assert (await client.get(f"{PLANS}/{plan_id}", headers=neighbour)).status_code == 404
    assert (
        await client.put(f"{PLANS}/{plan_id}/slots", json=slot(), headers=neighbour)
    ).status_code == 404
    assert (await client.delete(f"{PLANS}/{plan_id}", headers=neighbour)).status_code == 404


async def test_a_period_longer_than_a_month_is_refused(
    client: AsyncClient, cook: dict[str, str]
) -> None:
    """Beyond about a month it is a calendar rather than a plan — nobody knows who is
    coming to dinner in November — and it is what stops a screen laying out a row per day
    for a period somebody typed by accident."""
    response = await client.post(
        PLANS, json={"starts_on": MONDAY, "ends_on": "2027-08-30"}, headers=cook
    )

    assert response.status_code == 422


async def test_cooking_a_meal_consumes_what_it_held(
    client: AsyncClient, cook: dict[str, str], flour: int
) -> None:
    """UC-4.5 through the API, with the bus wired the way the running application wires
    it: the route knows nothing about the pantry, and the stock goes down anyway."""
    events.forget_everything()
    events.subscribe(MealCooked, pantry_manager.on_meal_cooked)
    lot = await pantry_access.receive(
        cook_id=1, ingredient_id=flour, quantity=Quantity(Decimal("500"), Unit.GRAM)
    )
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )
    slot_id = placed.json()["slots"][0]["id"]

    cooked = await client.post(f"{PLANS}/{plan_id}/slots/{slot_id}/cooked", headers=cook)

    assert cooked.status_code == 200
    assert cooked.json()["slots"][0]["cooked"] is True
    assert cooked.json()["shopping"] == []
    remaining = await pantry_access.fetch(lot.id)
    assert remaining is not None
    assert remaining.quantity.magnitude == Decimal("300.0000")
    events.forget_everything()


async def test_a_meal_that_is_not_yours_cannot_be_cooked(
    client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str], flour: int
) -> None:
    recipe_id = await a_recipe(client, cook, flour)
    plan_id = await a_week(client, cook)
    placed = await client.put(
        f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook
    )
    slot_id = placed.json()["slots"][0]["id"]

    response = await client.post(f"{PLANS}/{plan_id}/slots/{slot_id}/cooked", headers=neighbour)

    assert response.status_code == 404


class TestTickingItOff:
    """UC-4.4, the half that was missing. A list you cannot mark is a list a cook reads
    once and then keeps in their head, which is the thing this app exists to stop."""

    async def a_list(self, client: AsyncClient, headers: dict[str, str], flour: int) -> int:
        """A week with one meal on it, so there is exactly one thing to buy."""
        recipe_id = await a_recipe(client, headers, flour)
        plan_id = await a_week(client, headers)
        await client.put(
            f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=headers
        )
        return plan_id

    async def tick(
        self, client: AsyncClient, headers: dict[str, str], plan_id: int, flour: int, bought: bool
    ) -> Any:
        return await client.put(
            f"{PLANS}/{plan_id}/shopping/{flour}", json={"bought": bought}, headers=headers
        )

    async def test_a_line_starts_unbought(
        self, client: AsyncClient, cook: dict[str, str], flour: int
    ) -> None:
        plan_id = await self.a_list(client, cook, flour)
        plan = (await client.get(f"{PLANS}/{plan_id}", headers=cook)).json()
        assert plan["shopping"][0]["bought"] is False

    async def test_ticking_marks_it(
        self, client: AsyncClient, cook: dict[str, str], flour: int
    ) -> None:
        plan_id = await self.a_list(client, cook, flour)
        ticked = await self.tick(client, cook, plan_id, flour, True)
        assert ticked.status_code == 200
        assert ticked.json()["shopping"][0]["bought"] is True

    async def test_it_stays_on_the_list(
        self, client: AsyncClient, cook: dict[str, str], flour: int
    ) -> None:
        """Marked, not removed. A cook rereads the list at the till to check what they
        picked up, and a line that vanished cannot be checked."""
        plan_id = await self.a_list(client, cook, flour)
        await self.tick(client, cook, plan_id, flour, True)
        plan = (await client.get(f"{PLANS}/{plan_id}", headers=cook)).json()
        assert len(plan["shopping"]) == 1

    async def test_it_can_be_put_back(
        self, client: AsyncClient, cook: dict[str, str], flour: int
    ) -> None:
        plan_id = await self.a_list(client, cook, flour)
        await self.tick(client, cook, plan_id, flour, True)
        back = await self.tick(client, cook, plan_id, flour, False)
        assert back.json()["shopping"][0]["bought"] is False

    async def test_ticking_twice_is_ticking_once(
        self, client: AsyncClient, cook: dict[str, str], flour: int
    ) -> None:
        """A request that arrives again from a phone with one bar of signal in a shop."""
        plan_id = await self.a_list(client, cook, flour)
        await self.tick(client, cook, plan_id, flour, True)
        again = await self.tick(client, cook, plan_id, flour, True)
        assert again.json()["shopping"][0]["bought"] is True

    async def test_needing_more_puts_it_back_on_the_list(
        self, client: AsyncClient, cook: dict[str, str], flour: int
    ) -> None:
        """The reason a tick carries its quantity. A cook who ticked 200 g of flour and
        then planned a second night of pancakes needs 400 g, and has bought half of it.
        Carrying the tick across would hide 200 g they have not got.
        """
        recipe_id = await a_recipe(client, cook, flour)
        plan_id = await a_week(client, cook)
        await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)
        await self.tick(client, cook, plan_id, flour, True)

        added = await client.put(
            f"{PLANS}/{plan_id}/slots",
            json=slot(on_date=TUESDAY, recipe_id=recipe_id),
            headers=cook,
        )
        line = added.json()["shopping"][0]
        assert line["quantity"] == "400 g"
        assert line["bought"] is False

    async def test_needing_less_also_puts_it_back(
        self, client: AsyncClient, cook: dict[str, str], flour: int
    ) -> None:
        """The same rule from the other side. What was ticked answered a different
        question, and a stale yes is no better than a stale no."""
        recipe_id = await a_recipe(client, cook, flour)
        plan_id = await a_week(client, cook)
        await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)
        await client.put(
            f"{PLANS}/{plan_id}/slots",
            json=slot(on_date=TUESDAY, recipe_id=recipe_id),
            headers=cook,
        )
        await self.tick(client, cook, plan_id, flour, True)

        plan = (await client.get(f"{PLANS}/{plan_id}", headers=cook)).json()
        assert plan["shopping"][0]["bought"] is True

        cleared = await client.delete(
            f"{PLANS}/{plan_id}/slots/{plan['slots'][1]['id']}", headers=cook
        )
        assert cleared.json()["shopping"][0]["bought"] is False

    async def test_ticking_something_that_is_not_on_the_list_does_nothing(
        self, client: AsyncClient, cook: dict[str, str], flour: int, butter: int
    ) -> None:
        """No line to tick. Recording one anyway would leave a tick no screen could clear."""
        plan_id = await self.a_list(client, cook, flour)
        marked = await self.tick(client, cook, plan_id, butter, True)
        assert marked.status_code == 200
        assert [line["ingredient_id"] for line in marked.json()["shopping"]] == [flour]

    async def test_another_cooks_list_is_absent_rather_than_forbidden(
        self, client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str], flour: int
    ) -> None:
        plan_id = await self.a_list(client, cook, flour)
        assert (await self.tick(client, neighbour, plan_id, flour, True)).status_code == 404

    async def test_signing_in_is_required(self, client: AsyncClient) -> None:
        assert (await client.put(f"{PLANS}/1/shopping/1", json={"bought": True})).status_code == 401


class TestTheWeekBeingCookedNow:
    """What a cook standing in a shop asks for, and what a home screen shows without
    making anybody choose a week first."""

    async def test_nothing_planned_is_an_empty_answer_rather_than_an_error(
        self, client: AsyncClient, cook: dict[str, str]
    ) -> None:
        """Having no plan is an ordinary state, not a failure."""
        answered = await client.get(f"{PLANS}/current", headers=cook)
        assert answered.status_code == 200
        assert answered.json() is None

    async def test_the_week_containing_today(
        self, client: AsyncClient, cook: dict[str, str], flour: int, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(plan_manager, "_today", lambda: date(2026, 8, 26))
        await client.post(PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=cook)
        await client.post(
            PLANS, json={"starts_on": "2027-01-04", "ends_on": "2027-01-10"}, headers=cook
        )

        running = await client.get(f"{PLANS}/current", headers=cook)
        assert running.json()["starts_on"] == MONDAY

    async def test_between_weeks_the_last_one_stands(
        self, client: AsyncClient, cook: dict[str, str], monkeypatch: MonkeyPatch
    ) -> None:
        """The shopping for a plan that ended yesterday is still shopping the cook has not
        done. An empty screen would be the app forgetting on their behalf."""
        monkeypatch.setattr(plan_manager, "_today", lambda: date(2026, 9, 30))
        await client.post(PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=cook)

        running = await client.get(f"{PLANS}/current", headers=cook)
        assert running.json()["starts_on"] == MONDAY

    async def test_it_carries_the_shopping_list(
        self, client: AsyncClient, cook: dict[str, str], flour: int, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setattr(plan_manager, "_today", lambda: date(2026, 8, 26))
        recipe_id = await a_recipe(client, cook, flour)
        plan_id = await a_week(client, cook)
        await client.put(f"{PLANS}/{plan_id}/slots", json=slot(recipe_id=recipe_id), headers=cook)

        running = await client.get(f"{PLANS}/current", headers=cook)
        assert [line["quantity"] for line in running.json()["shopping"]] == ["200 g"]

    async def test_another_cooks_week_is_not_it(
        self, client: AsyncClient, cook: dict[str, str], neighbour: dict[str, str]
    ) -> None:
        await client.post(PLANS, json={"starts_on": MONDAY, "ends_on": SUNDAY}, headers=cook)
        assert (await client.get(f"{PLANS}/current", headers=neighbour)).json() is None
