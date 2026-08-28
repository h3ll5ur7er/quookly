"""Recipes through the API: authored, listed, scaled, and rendered in a cook's units."""

from collections.abc import AsyncIterator
from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access import preferences as preference_access
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.contracts.measure import Unit
from quookly.engines import exchange
from quookly.utilities.configuration import get_settings
from tests.support import sign_up

ENGLISH = "en-GB"


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
async def pantry() -> dict[str, int]:
    entries = {}
    for slug, name, kind, density in [
        ("plain-flour", "plain flour", IngredientKind.POWDER, Decimal("0.53")),
        ("milk", "milk", IngredientKind.LIQUID, Decimal("1.03")),
        ("egg", "egg", IngredientKind.COUNTABLE, None),
    ]:
        created = await registry.register(
            slug=slug, kind=kind, density=density, names={ENGLISH: [name]}, origin=Origin.SEED
        )
        entries[slug] = created.id
    return entries


def pancakes(pantry: dict[str, int]) -> dict[str, Any]:
    return {
        "title": "Pancakes",
        "summary": "Batter, pan, patience.",
        "yield_magnitude": "12",
        "yield_unit": "piece",
        "lines": [
            {"ingredient_id": pantry["plain-flour"], "magnitude": "1", "unit": "cup (US)"},
            {"ingredient_id": pantry["milk"], "magnitude": "300", "unit": "ml"},
            {"ingredient_id": pantry["egg"], "magnitude": "2", "unit": "piece"},
        ],
        "steps": [
            {"instruction": "Whisk everything together.", "duration_seconds": 300},
            {
                "instruction": "Rest the batter.",
                "duration_seconds": 1800,
                "attention": "waiting",
            },
            {
                "instruction": "Fry until golden.",
                "duration_seconds": 600,
                "temperature_celsius": 180,
            },
        ],
    }


class TestAuthoring:
    async def test_a_recipe_can_be_authored(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        response = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert response.status_code == 201
        assert response.json()["title"] == "Pancakes"

    async def test_a_recipe_needs_ingredients_and_steps(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        response = await client.post(
            "/api/v1/recipes", json={**pancakes(pantry), "lines": []}, headers=headers
        )
        assert response.status_code == 422

    async def test_an_unknown_unit_is_refused_rather_than_guessed(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe = pancakes(pantry)
        recipe["lines"][0]["unit"] = "handfuls"
        response = await client.post("/api/v1/recipes", json=recipe, headers=headers)
        assert response.status_code in (400, 422)


class TestReading:
    async def test_a_cook_lists_their_own_recipes(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        listed = await client.get("/api/v1/recipes", headers=headers)
        assert [item["title"] for item in listed.json()] == ["Pancakes"]

    async def test_another_cooks_recipe_is_absent_not_forbidden(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """A 403 would confirm the recipe exists. Private means invisible."""
        mine = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=mine)
        recipe_id = created.json()["id"]

        theirs = await sign_up(client, "other@example.com")
        response = await client.get(f"/api/v1/recipes/{recipe_id}", headers=theirs)
        assert response.status_code == 404

    async def test_an_unknown_recipe_is_not_found(self, client: AsyncClient) -> None:
        headers = await sign_up(client, "chef@example.com")
        assert (await client.get("/api/v1/recipes/9999", headers=headers)).status_code == 404


class TestRendering:
    async def test_a_cup_of_flour_is_shown_in_grams(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """The founding annoyance, fixed end to end."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        flour = created.json()["lines"][0]
        assert flour["ingredient"] == "plain flour"
        assert flour["quantity"]["display"] == "125 g"

    async def test_a_count_is_left_as_a_count(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert created.json()["lines"][2]["quantity"]["display"] == "2"

    async def test_quantities_follow_the_cooks_preference(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """A Swiss cook asked for decilitres, so 300 ml of milk reads as 3 dl."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        listed = await client.get("/api/v1/recipes", headers=headers)
        assert listed.status_code == 200
        cook_id = 1
        await preference_access.choose(cook_id, IngredientKind.LIQUID, Unit.DECILITRE)

        response = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        milk = response.json()["lines"][1]
        assert milk["quantity"]["display"] == "3 dl"

    async def test_a_quantity_is_a_string_not_a_json_number(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """A browser's JSON numbers are binary floats; a gram is not worth losing to that."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert isinstance(created.json()["lines"][0]["quantity"]["magnitude"], str)


class TestDisplayStrings:
    async def test_a_listed_yield_reads_as_a_number(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Stored precision is not display precision. "12.0000 pieces" is not a yield."""
        headers = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)

        listed = await client.get("/api/v1/recipes", headers=headers)
        assert listed.json()[0]["yield_quantity"]["display"] == "12"

    async def test_the_precise_magnitude_is_still_available(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Display is tidied; the value a client might compute with is not."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert created.json()["lines"][1]["quantity"]["magnitude"]


class TestScaling:
    async def test_halving_the_yield_halves_the_ingredients(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        response = await client.get(f"/api/v1/recipes/{recipe_id}?servings=6", headers=headers)
        body = response.json()
        assert body["yield_quantity"]["display"] == "6"
        assert body["lines"][0]["quantity"]["display"] == "62.7 g"
        assert body["lines"][1]["quantity"]["display"] == "150 ml"

    async def test_scaling_up_works_the_same_way(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        response = await client.get(f"/api/v1/recipes/{recipe_id}?servings=24", headers=headers)
        assert response.json()["lines"][1]["quantity"]["display"] == "600 ml"

    async def test_the_unscaled_recipe_is_unchanged_by_a_scaled_reading(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Scaling is a view. Reading a recipe for six must not edit it."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        await client.get(f"/api/v1/recipes/{recipe_id}?servings=6", headers=headers)
        again = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert again.json()["lines"][1]["quantity"]["display"] == "300 ml"

    async def test_a_yield_of_zero_is_refused(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]
        response = await client.get(f"/api/v1/recipes/{recipe_id}?servings=0", headers=headers)
        assert response.status_code == 422


class TestExchange:
    async def test_export_is_not_mistaken_for_a_recipe_id(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """`/recipes/export` and `/recipes/{id}` share a prefix; order decides which wins."""
        headers = await sign_up(client, "chef@example.com")
        response = await client.get("/api/v1/recipes/export", headers=headers)
        assert response.status_code == 200
        # A document, not a recipe. The version comes from the engine rather than a
        # literal, so bumping the format is not a change to a test about routing.
        assert response.json()["quookly"] == exchange.FORMAT_VERSION
        assert "recipes" in response.json()

    async def test_a_cook_can_take_their_recipes_with_them(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)

        exported = (await client.get("/api/v1/recipes/export", headers=headers)).json()
        assert [recipe["title"] for recipe in exported["recipes"]] == ["Pancakes"]
        assert {entry["slug"] for entry in exported["ingredients"]} == {
            "plain-flour",
            "milk",
            "egg",
        }

    async def test_what_was_exported_can_be_imported(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """FR-11 end to end: the export format is the import format."""
        mine = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=mine)
        exported = (await client.get("/api/v1/recipes/export", headers=mine)).json()

        theirs = await sign_up(client, "other@example.com")
        response = await client.post("/api/v1/recipes/import", json=exported, headers=theirs)
        assert response.status_code == 201
        assert response.json() == {"recipes_added": 1, "ingredients_added": 0}

        listed = await client.get("/api/v1/recipes", headers=theirs)
        assert [item["title"] for item in listed.json()] == ["Pancakes"]

    async def test_a_document_this_build_cannot_read_is_refused(self, client: AsyncClient) -> None:
        headers = await sign_up(client, "chef@example.com")
        response = await client.post(
            "/api/v1/recipes/import", json={"quookly": 99, "recipes": []}, headers=headers
        )
        assert response.status_code == 422

    async def test_export_requires_signing_in(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/recipes/export")).status_code == 401


class TestHowLongItTakes:
    """UC-2.6 and FR-23: two numbers, both derived from the steps (ADR-037)."""

    async def test_a_recipe_reports_its_work_and_its_clock_separately(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Fifteen minutes of work and forty-five before anybody eats. One figure
        covering both would describe neither."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)

        timing = created.json()["timing"]
        assert timing["hands_on"] == {"seconds": 900, "at_least": False}
        assert timing["total"] == {"seconds": 2700, "at_least": False}
        assert timing["ahead"] is None

    async def test_a_step_that_says_nothing_makes_the_numbers_a_floor(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Not zero. A step with no duration must not make the recipe look quicker."""
        headers = await sign_up(client, "chef@example.com")
        untimed = pancakes(pantry)
        untimed["steps"][0] = {"instruction": "Whisk everything together."}
        created = await client.post("/api/v1/recipes", json=untimed, headers=headers)

        timing = created.json()["timing"]
        assert timing["hands_on"] == {"seconds": 600, "at_least": True}
        assert timing["total"] == {"seconds": 2400, "at_least": True}

    async def test_a_recipe_that_says_nothing_about_time_says_nothing(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        untimed = pancakes(pantry)
        untimed["steps"] = [{"instruction": step["instruction"]} for step in untimed["steps"]]
        created = await client.post("/api/v1/recipes", json=untimed, headers=headers)

        assert created.json()["timing"] is None

    async def test_the_time_is_on_the_list_as_well_as_the_page(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """The question is asked before the tap, not after it."""
        headers = await sign_up(client, "chef@example.com")
        await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)

        listed = await client.get("/api/v1/recipes", headers=headers)
        assert listed.json()[0]["timing"]["hands_on"] == {"seconds": 900, "at_least": False}

    async def test_scaling_a_recipe_does_not_scale_its_time(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Doubling a tray does not double the oven, and it barely touches the chopping.
        A factor applied here would be arithmetic producing a number nobody measured."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        recipe_id = created.json()["id"]

        doubled = await client.get(f"/api/v1/recipes/{recipe_id}?servings=24", headers=headers)
        assert doubled.json()["timing"]["total"] == {"seconds": 2700, "at_least": False}

    async def test_work_done_the_day_before_is_neither_number(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Eight hours of soaking beans is not eight hours of cooking, and dropping it
        silently lets somebody start dinner at six."""
        headers = await sign_up(client, "chef@example.com")
        overnight = pancakes(pantry)
        overnight["steps"] = [
            {"instruction": "Soak overnight.", "duration_seconds": 28800, "attention": "ahead"},
            *overnight["steps"],
        ]
        created = await client.post("/api/v1/recipes", json=overnight, headers=headers)

        timing = created.json()["timing"]
        assert timing["total"] == {"seconds": 2700, "at_least": False}
        assert timing["ahead"] == {"seconds": 28800, "at_least": False}


class TestEditing:
    """A recipe could be created and never changed (ADR-059).

    No `PUT`, no `PATCH`, no `DELETE` — a typo in an imported recipe was permanent, a
    misread quantity was permanent, and a bad import could only be lived with.
    """

    async def mine(self, client: AsyncClient, pantry: dict[str, int]) -> tuple[dict[str, str], int]:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        return headers, int(created.json()["id"])

    async def test_a_recipe_can_be_corrected(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, recipe_id = await self.mine(client, pantry)
        amended = {**pancakes(pantry), "title": "Buttermilk Pancakes"}
        response = await client.put(f"/api/v1/recipes/{recipe_id}", json=amended, headers=headers)
        assert response.status_code == 200
        assert response.json()["title"] == "Buttermilk Pancakes"

    async def test_it_is_the_same_recipe_afterwards(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Plans, cooked meals and shopping ticks point at it by id."""
        headers, recipe_id = await self.mine(client, pantry)
        amended = {**pancakes(pantry), "title": "Buttermilk Pancakes"}
        body = (
            await client.put(f"/api/v1/recipes/{recipe_id}", json=amended, headers=headers)
        ).json()
        assert body["id"] == recipe_id

    async def test_a_step_can_be_rewritten(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, recipe_id = await self.mine(client, pantry)
        amended = {
            **pancakes(pantry),
            "steps": [{"instruction": "Whisk, rest, fry."}],
        }
        body = (
            await client.put(f"/api/v1/recipes/{recipe_id}", json=amended, headers=headers)
        ).json()
        assert [step["instruction"] for step in body["steps"]] == ["Whisk, rest, fry."]

    async def test_the_correction_is_what_is_read_back(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, recipe_id = await self.mine(client, pantry)
        await client.put(
            f"/api/v1/recipes/{recipe_id}",
            json={**pancakes(pantry), "title": "Buttermilk Pancakes"},
            headers=headers,
        )
        read = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert read.json()["title"] == "Buttermilk Pancakes"

    async def test_it_is_findable_by_its_new_title(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """The search index holds a recipe's title and ingredients. Editing changes what
        it should be findable by, and an index nobody updated is worse than none."""
        headers, recipe_id = await self.mine(client, pantry)
        await client.put(
            f"/api/v1/recipes/{recipe_id}",
            json={**pancakes(pantry), "title": "Blini"},
            headers=headers,
        )
        found = await client.get(
            "/api/v1/recipes/suggestions", params={"q": "Blini"}, headers=headers
        )
        assert recipe_id in [one["recipe"]["id"] for one in found.json()]

        # And no longer by the old one. This is the half that proves the index was
        # rewritten rather than added to: without it the test passes on a stale index.
        stale = await client.get(
            "/api/v1/recipes/suggestions", params={"q": "Pancakes"}, headers=headers
        )
        assert recipe_id not in [one["recipe"]["id"] for one in stale.json()]

    async def test_another_cooks_recipe_is_absent_not_forbidden(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Everyone edits their own. A 403 would confirm the recipe exists."""
        _, recipe_id = await self.mine(client, pantry)
        theirs = await sign_up(client, "other@example.com")
        response = await client.put(
            f"/api/v1/recipes/{recipe_id}", json=pancakes(pantry), headers=theirs
        )
        assert response.status_code == 404

    async def test_editing_something_that_is_not_there_is_a_404(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        response = await client.put("/api/v1/recipes/9999", json=pancakes(pantry), headers=headers)
        assert response.status_code == 404

    async def test_a_line_pointing_at_nothing_is_refused(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, recipe_id = await self.mine(client, pantry)
        amended = {
            **pancakes(pantry),
            "lines": [{"ingredient_id": 9999, "magnitude": "1", "unit": "cup (US)"}],
        }
        response = await client.put(f"/api/v1/recipes/{recipe_id}", json=amended, headers=headers)
        assert response.status_code == 422


class TestArchiving:
    """Put away rather than deleted, because things point at a recipe."""

    async def mine(self, client: AsyncClient, pantry: dict[str, int]) -> tuple[dict[str, str], int]:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        return headers, int(created.json()["id"])

    async def test_an_archived_recipe_leaves_the_list(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, recipe_id = await self.mine(client, pantry)
        assert (
            await client.post(f"/api/v1/recipes/{recipe_id}/archived", headers=headers)
        ).status_code == 204
        listed = (await client.get("/api/v1/recipes", headers=headers)).json()
        assert recipe_id not in [one["id"] for one in listed]

    async def test_it_is_still_there_when_something_points_at_it(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """The whole reason this is an archive: a plan holding it must still resolve."""
        headers, recipe_id = await self.mine(client, pantry)
        await client.post(f"/api/v1/recipes/{recipe_id}/archived", headers=headers)
        read = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert read.status_code == 200
        assert read.json()["title"] == "Pancakes"

    async def test_it_stops_being_findable(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """A hit on a recipe somebody put away is the same nuisance as one on a recipe
        that is gone."""
        headers, recipe_id = await self.mine(client, pantry)
        await client.post(f"/api/v1/recipes/{recipe_id}/archived", headers=headers)
        found = await client.get(
            "/api/v1/recipes/suggestions", params={"q": "Pancakes"}, headers=headers
        )
        assert recipe_id not in [one["recipe"]["id"] for one in found.json()]

    async def test_it_can_be_brought_back(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, recipe_id = await self.mine(client, pantry)
        await client.post(f"/api/v1/recipes/{recipe_id}/archived", headers=headers)
        assert (
            await client.post(f"/api/v1/recipes/{recipe_id}/restored", headers=headers)
        ).status_code == 204
        listed = (await client.get("/api/v1/recipes", headers=headers)).json()
        assert recipe_id in [one["id"] for one in listed]

    async def test_bringing_it_back_makes_it_findable_again(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, recipe_id = await self.mine(client, pantry)
        await client.post(f"/api/v1/recipes/{recipe_id}/archived", headers=headers)
        await client.post(f"/api/v1/recipes/{recipe_id}/restored", headers=headers)
        found = await client.get(
            "/api/v1/recipes/suggestions", params={"q": "Pancakes"}, headers=headers
        )
        assert recipe_id in [one["recipe"]["id"] for one in found.json()]

    async def test_another_cooks_recipe_cannot_be_archived(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        _, recipe_id = await self.mine(client, pantry)
        theirs = await sign_up(client, "other@example.com")
        response = await client.post(f"/api/v1/recipes/{recipe_id}/archived", headers=theirs)
        assert response.status_code == 404

    async def test_the_archived_can_be_asked_for(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Otherwise putting one away is indistinguishable from losing it."""
        headers, recipe_id = await self.mine(client, pantry)
        await client.post(f"/api/v1/recipes/{recipe_id}/archived", headers=headers)
        listed = (
            await client.get("/api/v1/recipes", params={"archived": True}, headers=headers)
        ).json()
        assert [one["id"] for one in listed] == [recipe_id]

    async def test_asking_for_the_archived_shows_only_those(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers, archived = await self.mine(client, pantry)
        kept = (
            await client.post(
                "/api/v1/recipes", json={**pancakes(pantry), "title": "Blini"}, headers=headers
            )
        ).json()["id"]
        await client.post(f"/api/v1/recipes/{archived}/archived", headers=headers)

        current = (await client.get("/api/v1/recipes", headers=headers)).json()
        put_away = (
            await client.get("/api/v1/recipes", params={"archived": True}, headers=headers)
        ).json()
        assert [one["id"] for one in current] == [kept]
        assert [one["id"] for one in put_away] == [archived]


class TestALineSaysWhatItPointsAt:
    """A presented line carried the ingredient's *name* and nothing else.

    Enough to read a recipe and not enough to correct one: an edit form that only knows
    what a line is called would have to resolve the name back to an entry, which is
    guessing at something the server already knew. A recipe has to be able to round-trip
    through the form that edits it (ADR-059).
    """

    async def test_a_line_carries_the_entry_it_points_at(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        line = created.json()["lines"][0]
        assert line["ingredient_id"] == pantry["plain-flour"]

    async def test_it_carries_the_kind_so_a_form_can_offer_units(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Which units to offer is decided by kind — powders in grams, liquids in
        millilitres — and a form that had to guess would offer the wrong ones."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        line = created.json()["lines"][0]
        assert line["ingredient_kind"] == "powder"

    async def test_the_name_is_still_there(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Additive: reading a recipe is what this model is for."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert created.json()["lines"][0]["ingredient"] == "plain flour"


class TestJargonInASteps:
    """Terms a cook can look up, marked in place (UC-2.5, ADR-055).

    Nothing is tagged and nothing is stored linking a step to a page: the terms are read
    out of the step's own words when it is displayed, exactly as its ingredient lines are
    (ADR-040). A recipe imported before a page existed gains the link the day somebody
    writes it.
    """

    @pytest.fixture
    async def academy(self) -> int:
        from quookly.managers.seed import stock_academy

        return await stock_academy()

    async def test_a_step_says_which_of_its_words_can_be_looked_up(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post(
            "/api/v1/recipes",
            json={
                **pancakes(pantry),
                "steps": [{"instruction": "Fold in the whites, then blanch the beans."}],
            },
            headers=headers,
        )
        step = created.json()["steps"][0]
        assert [one["slug"] for one in step["mentions"]] == ["fold", "blanch"]

    async def test_the_offsets_point_at_the_words_as_written(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        """A client underlines in place, so the offsets have to be into the instruction it
        was given."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post(
            "/api/v1/recipes",
            json={**pancakes(pantry), "steps": [{"instruction": "Gently fold in the whites."}]},
            headers=headers,
        )
        step = created.json()["steps"][0]
        found = step["mentions"][0]
        assert step["instruction"][found["start"] : found["end"]] == "Gently fold"

    async def test_a_step_that_names_nothing_says_so(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        created = await client.post(
            "/api/v1/recipes",
            json={**pancakes(pantry), "steps": [{"instruction": "Put it on a plate."}]},
            headers=headers,
        )
        assert created.json()["steps"][0]["mentions"] == []

    async def test_an_instance_with_no_academy_marks_nothing(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """No pages installed, so nothing to link to. The recipe still reads."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post(
            "/api/v1/recipes",
            json={**pancakes(pantry), "steps": [{"instruction": "Fold in the whites."}]},
            headers=headers,
        )
        assert created.json()["steps"][0]["mentions"] == []

    async def test_it_marks_terms_in_the_cooks_language(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        headers = await sign_up(client, "koch@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": "de-CH"}, headers=headers)
        created = await client.post(
            "/api/v1/recipes",
            json={**pancakes(pantry), "steps": [{"instruction": "Die Butter unterheben."}]},
            headers=headers,
        )
        assert [one["slug"] for one in created.json()["steps"][0]["mentions"]] == ["fold"]


class TestLinksAnAuthorWrote:
    """`[[slug|words]]` in a step, through the API (ADR-059)."""

    @pytest.fixture
    async def academy(self) -> int:
        from quookly.managers.seed import stock_academy

        return await stock_academy()

    async def written(
        self, client: AsyncClient, headers: dict[str, str], pantry: dict[str, int], step: str
    ) -> Any:
        created = await client.post(
            "/api/v1/recipes",
            json={**pancakes(pantry), "steps": [{"instruction": step}]},
            headers=headers,
        )
        return created.json()["steps"][0]

    async def test_a_reader_never_sees_the_brackets(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        step = await self.written(
            client, headers, pantry, "Sift the [[plain-flour|flour]] into the bowl."
        )
        assert step["instruction"] == "Sift the flour into the bowl."

    async def test_the_link_is_marked_where_the_words_are(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        step = await self.written(
            client, headers, pantry, "Sift the [[plain-flour|flour]] into the bowl."
        )
        # Not the first mention: "Sift" is a technique the Academy explains, and it comes
        # earlier in the sentence. Both are found, which is the point.
        found = next(one for one in step["mentions"] if one["slug"] == "plain-flour")
        assert step["instruction"][found["start"] : found["end"]] == "flour"

    async def test_what_is_stored_comes_back_for_an_editor(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        """A form filled from the rendered text would drop the link the moment somebody
        corrected a typo, which is the one thing an editable recipe must not do."""
        headers = await sign_up(client, "chef@example.com")
        step = await self.written(
            client, headers, pantry, "Sift the [[plain-flour|flour]] into the bowl."
        )
        assert step["written"] == "Sift the [[plain-flour|flour]] into the bowl."

    async def test_a_step_with_no_links_says_the_same_thing_twice(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        step = await self.written(client, headers, pantry, "Put it on a plate.")
        assert step["instruction"] == step["written"] == "Put it on a plate."

    async def test_the_rest_of_the_step_is_still_read(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        step = await self.written(
            client, headers, pantry, "[[plain-flour|Sift the flour]], then blanch the beans."
        )
        assert [one["slug"] for one in step["mentions"]] == ["plain-flour", "blanch"]

    async def test_it_survives_a_round_trip_through_the_editor(
        self, client: AsyncClient, pantry: dict[str, int], academy: int
    ) -> None:
        """Editing sends back what was stored, so the link is still there afterwards."""
        headers = await sign_up(client, "chef@example.com")
        created = await client.post(
            "/api/v1/recipes",
            json={
                **pancakes(pantry),
                "steps": [{"instruction": "Sift the [[plain-flour|flour]] in."}],
            },
            headers=headers,
        )
        recipe_id = created.json()["id"]
        stored = created.json()["steps"][0]["written"]

        amended = await client.put(
            f"/api/v1/recipes/{recipe_id}",
            json={**pancakes(pantry), "title": "Blini", "steps": [{"instruction": stored}]},
            headers=headers,
        )
        step = amended.json()["steps"][0]
        assert step["instruction"] == "Sift the flour in."
        assert "plain-flour" in [one["slug"] for one in step["mentions"]]


class TestWhatLanguageARecipeIsIn:
    """A recipe records the language it is written in (Phase 8b, ADR-032).

    Without it nothing downstream can tell a German recipe from an English one, and a
    translation has no *from*.
    """

    async def test_a_recipe_written_here_is_in_the_cooks_language(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Nobody is asked. Somebody typing a recipe into a German screen is writing
        German, and a form field for it would be a question with an obvious answer."""
        headers = await sign_up(client, "chef@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": "de-CH"}, headers=headers)

        made = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert made.json()["language"] == "de"

    async def test_a_cook_who_has_chosen_nothing_writes_the_source_language(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        made = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        assert made.json()["language"] == "en"

    async def test_it_survives_an_edit(self, client: AsyncClient, pantry: dict[str, int]) -> None:
        """Correcting a typo does not change what language the recipe is in."""
        headers = await sign_up(client, "chef@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": "fr-CH"}, headers=headers)
        made = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)

        amended = await client.put(
            f"/api/v1/recipes/{made.json()['id']}",
            json={**pancakes(pantry), "title": "Blini"},
            headers=headers,
        )
        assert amended.json()["language"] == "fr"


class TestReadingARecipeInYourOwnLanguage:
    """Phase 8b, end to end through the API (ADR-032, ADR-064).

    A recipe belongs to the cook who wrote it, so the reader here is the same cook reading
    in a different language — somebody bilingual, or somebody who changed the language the
    app speaks to them in. The import path is where a *foreign* recipe arrives, and it
    arrives into this same cook's kitchen.

    Lazy: derived on first request for a language, not eagerly. Eager spends round trips
    on content nobody may read, and makes a fourth language a migration over every recipe
    ever stored instead of a no-op.
    """

    @pytest.fixture
    def answering(self, monkeypatch: MonkeyPatch) -> list[str]:
        """A model that translates, and a note of how often it was asked."""
        from quookly.access import model as inference
        from quookly.contracts.inference import Completion

        asked: list[str] = []

        async def complete_structured(
            prompt: str, schema: dict[str, Any], system: str | None = None, **rest: Any
        ) -> tuple[dict[str, Any], Completion]:
            asked.append(prompt)
            return (
                {
                    "title": "Chocolate cake",
                    "summary": "A simple cake.",
                    "steps": ["Cream the butter and sugar.", "Bake at 180 C."],
                },
                Completion(text="{}", model="test"),
            )

        monkeypatch.setattr(inference, "complete_structured", complete_structured)
        return asked

    def german(self, pantry: dict[str, int]) -> dict[str, Any]:
        return {
            **pancakes(pantry),
            "title": "Schokoladenkuchen",
            "summary": "Ein einfacher Kuchen.",
            "steps": [
                {"instruction": "Butter und Zucker schaumig ruehren."},
                {"instruction": "Bei 180 C backen."},
            ],
        }

    async def written(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> tuple[dict[str, str], int]:
        headers = await sign_up(client, "chef@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": "de-CH"}, headers=headers)
        made = await client.post("/api/v1/recipes", json=self.german(pantry), headers=headers)
        assert made.status_code == 201, made.text
        return headers, int(made.json()["id"])

    async def reading_english(self, client: AsyncClient, headers: dict[str, str]) -> None:
        await client.put("/api/v1/setup/locale", json={"locale": "en-GB"}, headers=headers)

    async def test_it_is_read_in_the_language_the_cook_reads_in(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)

        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.json()["title"] == "Chocolate cake"
        assert found.json()["steps"][0]["instruction"] == "Cream the butter and sugar."

    async def test_read_in_its_own_language_it_is_the_authors_words(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """The original is never replaced. Taking a German cook's own recipe away from
        them in their own kitchen is what normalising-on-import would have done."""
        headers, recipe_id = await self.written(client, pantry)
        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.json()["title"] == "Schokoladenkuchen"
        assert answering == []

    async def test_it_is_asked_for_once_and_then_kept(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)

        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert len(answering) == 1

    async def test_editing_the_recipe_makes_it_ask_again(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """The whole of ADR-064. A translation of a sentence that was rewritten is a wrong
        instruction, and nothing had to remember to mark it."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)

        amended = await client.put(
            f"/api/v1/recipes/{recipe_id}",
            json={
                **self.german(pantry),
                "steps": [
                    {"instruction": "Butter und Zucker schaumig schlagen."},
                    {"instruction": "Bei 180 C backen."},
                ],
            },
            headers=headers,
        )
        assert amended.status_code == 200, amended.text

        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert len(answering) == 2

    async def test_an_instance_with_no_model_shows_the_original(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """Which is what it does today, and is not a failure. A cook reading a recipe in
        the wrong language is better served than one shown an error."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)

        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.status_code == 200
        assert found.json()["title"] == "Schokoladenkuchen"

    async def test_a_cook_can_correct_a_translation(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """The second half of ADR-064, which had storage and no screen. A model's German
        is a starting point; the cook who wrote the recipe knows what it says."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)

        corrected = await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={
                "title": "Chocolate cake, properly",
                "summary": "A simple cake.",
                "steps": ["Beat the butter and sugar until pale.", "Bake at 180 C."],
            },
            headers=headers,
        )

        assert corrected.status_code == 200, corrected.text
        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.json()["title"] == "Chocolate cake, properly"

    async def test_a_correction_is_not_re_derived(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """A model asked again would overwrite somebody's work, which is the thing ADR-064
        exists to stop."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={
                "title": "Chocolate cake, properly",
                "summary": None,
                "steps": ["Beat the butter and sugar until pale.", "Bake at 180 C."],
            },
            headers=headers,
        )

        asked = len(answering)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert len(answering) == asked

    async def test_a_correction_of_words_that_moved_shows_the_original_instead(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """Kept, and stopped being shown. The reader sees the recipe's own language, which
        is honest and is what an instance with no model shows anyway — rather than a fresh
        machine translation quietly replacing somebody's work (ADR-064)."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={
                "title": "Chocolate cake, properly",
                "summary": None,
                "steps": ["Beat the butter and sugar until pale.", "Bake at 180 C."],
            },
            headers=headers,
        )

        await client.put(
            f"/api/v1/recipes/{recipe_id}",
            json={
                **self.german(pantry),
                "steps": [
                    {"instruction": "Butter und Zucker schaumig schlagen."},
                    {"instruction": "Bei 180 C backen."},
                ],
            },
            headers=headers,
        )

        asked = len(answering)
        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)

        assert found.json()["title"] == "Schokoladenkuchen"
        assert found.json()["translated"] is False
        assert len(answering) == asked

    async def test_the_correction_can_be_read_back_to_be_brought_up_to_date(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """What the screen offering to fix it needs: the words somebody wrote, the recipe
        as it now stands, and whether the two still agree."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={
                "title": "Chocolate cake, properly",
                "summary": None,
                "steps": ["Beat the butter and sugar until pale.", "Bake at 180 C."],
            },
            headers=headers,
        )

        draft = await client.get(f"/api/v1/recipes/{recipe_id}/translations/en", headers=headers)

        assert draft.status_code == 200, draft.text
        body = draft.json()
        assert body["by_hand"] is True
        assert body["current"] is True
        assert body["title"] == "Chocolate cake, properly"
        # And the author's own words beside it, to correct against.
        assert body["source"]["title"] == "Schokoladenkuchen"
        assert body["source_language"] == "de"

    async def test_a_translation_with_the_wrong_number_of_steps_is_refused(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """The pairing is by position, so a translation with a step missing would put step
        three's words on step two — which is a wrong instruction, not a bad one."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)

        refused = await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={"title": "Chocolate cake", "summary": None, "steps": ["Only one step."]},
            headers=headers,
        )
        assert refused.status_code == 422

    async def test_only_the_cook_whose_recipe_it_is_may_correct_it(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        headers, recipe_id = await self.written(client, pantry)
        neighbour = await sign_up(client, "neighbour@example.com")

        refused = await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={"title": "Mine now", "summary": None, "steps": ["One.", "Two."]},
            headers=neighbour,
        )
        assert refused.status_code == 404

    async def test_a_recipe_cannot_be_corrected_into_its_own_language(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """Those are the author's words. A "translation" into the language the recipe is
        already in is an edit, and the edit screen is where edits happen."""
        headers, recipe_id = await self.written(client, pantry)

        refused = await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/de",
            json={"title": "Anders", "summary": None, "steps": ["Eins.", "Zwei."]},
            headers=headers,
        )
        assert refused.status_code == 409

    async def test_an_export_carries_a_persons_translation_and_not_a_machines(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """A model's translation is nobody's work: the receiving instance derives one in a
        round trip with its own model, and shipping one would spread this instance's model
        quality to everywhere that ever imported from it (ADR-012, ADR-064)."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        # A machine's, first.
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)

        exported = (await client.get("/api/v1/recipes/export", headers=headers)).json()
        [recipe] = exported["recipes"]
        assert recipe["language"] == "de"
        assert recipe["translations"] == []

        await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={
                "title": "Chocolate cake, properly",
                "summary": None,
                "steps": ["Beat the butter and sugar until pale.", "Bake at 180 C."],
            },
            headers=headers,
        )

        exported = (await client.get("/api/v1/recipes/export", headers=headers)).json()
        [carried] = exported["recipes"][0]["translations"]
        assert carried["locale"] == "en"
        assert carried["title"] == "Chocolate cake, properly"

    async def test_an_export_names_an_ingredient_in_every_language_it_knows(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """Otherwise a German import arrives named only in German, which makes a foreign
        entry less readable than a seeded one for no reason: the names existed and were
        being dropped on the way out."""
        headers, _ = await self.written(client, pantry)

        exported = (await client.get("/api/v1/recipes/export", headers=headers)).json()

        flour = next(one for one in exported["ingredients"] if one["slug"] == "plain-flour")
        assert "en-GB" in flour["names_by_locale"]

    async def test_an_import_keeps_the_language_and_the_translation(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """The round trip is the promise ADR-012 makes: what left comes back."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={
                "title": "Chocolate cake, properly",
                "summary": None,
                "steps": ["Beat the butter and sugar until pale.", "Bake at 180 C."],
            },
            headers=headers,
        )
        document = (await client.get("/api/v1/recipes/export", headers=headers)).json()

        neighbour = await sign_up(client, "neighbour@example.com")
        received = await client.post("/api/v1/recipes/import", json=document, headers=neighbour)
        assert received.status_code == 201, received.text

        theirs = (await client.get("/api/v1/recipes", headers=neighbour)).json()
        [one] = [row for row in theirs if row["title"] == "Schokoladenkuchen"]

        # Read in English, it is the *person's* words that arrived — not a fresh machine
        # translation, and not the German.
        await client.put("/api/v1/setup/locale", json={"locale": "en-GB"}, headers=neighbour)
        asked = len(answering)
        read = await client.get(f"/api/v1/recipes/{one['id']}", headers=neighbour)

        assert read.json()["title"] == "Chocolate cake, properly"
        assert read.json()["translated_by_hand"] is True
        assert len(answering) == asked

    async def test_a_correction_is_not_reported_as_a_machines_words(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """Both are translations and only one is somebody's work. Printing "a machine wrote
        this" over a cook's own correction is as wrong as the other way round (ADR-064)."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)
        machine = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert machine.json()["translated"] is True
        assert machine.json()["translated_by_hand"] is False

        await client.put(
            f"/api/v1/recipes/{recipe_id}/translations/en",
            json={
                "title": "Chocolate cake, properly",
                "summary": None,
                "steps": ["Beat the butter and sugar until pale.", "Bake at 180 C."],
            },
            headers=headers,
        )

        corrected = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert corrected.json()["translated"] is True
        assert corrected.json()["translated_by_hand"] is True

    async def test_the_reader_is_told_it_is_a_translation(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        """Not optional. Prose a model produced, shown as the author's words, is exactly
        what ADR-056 exists to prevent one layer up — and here the author is a person the
        reader may know."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)

        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.json()["translated"] is True

    async def test_the_authors_own_words_are_not_marked_as_a_translation(
        self, client: AsyncClient, pantry: dict[str, int], answering: list[str]
    ) -> None:
        headers, recipe_id = await self.written(client, pantry)
        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.json()["translated"] is False

    async def test_an_untranslated_recipe_is_not_marked_either(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """No model here, so the English reader is shown the German. Saying that is a
        translation would be saying something false about the words on the screen."""
        headers, recipe_id = await self.written(client, pantry)
        await self.reading_english(client, headers)

        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.json()["translated"] is False


class TestAPictureOfTheDish:
    """One picture per recipe (X4).

    One, not a gallery. A card wants a thumbnail and a page wants a hero; the Academy
    needs several because a technique is shown in stages, and a dish is not.

    Alt text is required for the same reason it is on an Academy picture: a picture
    without it is an accessibility failure, and this project checks that as it builds
    rather than retrofitting it.
    """

    def a_picture(self) -> bytes:
        drawn = BytesIO()
        Image.new("RGB", (60, 40), "white").save(drawn, format="PNG")
        return drawn.getvalue()

    async def a_recipe(
        self, client: AsyncClient, headers: dict[str, str], pantry: dict[str, int]
    ) -> int:
        made = await client.post("/api/v1/recipes", json=pancakes(pantry), headers=headers)
        return int(made.json()["id"])

    async def test_a_cook_can_put_a_picture_on_their_recipe(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)

        added = await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("dish.png", self.a_picture(), "image/png")},
            data={"description": "A stack of pancakes with butter melting on top."},
            headers=headers,
        )
        assert added.status_code == 200, added.text
        assert added.json()["picture"]["media_id"]
        assert added.json()["picture"]["description"].startswith("A stack")

    async def test_a_recipe_without_one_says_so_rather_than_pretending(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        found = await client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
        assert found.json()["picture"] is None

    async def test_the_list_carries_it_too(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """The list is where it earns its keep: a wall of identical text cards is a list
        that has to be read rather than looked at."""
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("dish.png", self.a_picture(), "image/png")},
            data={"description": "A stack of pancakes."},
            headers=headers,
        )

        listed = await client.get("/api/v1/recipes", headers=headers)
        mine = next(one for one in listed.json() if one["id"] == recipe_id)
        assert mine["picture"]["media_id"]

    async def test_a_second_picture_replaces_the_first(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """One picture, so putting another on is changing it rather than adding to it."""
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        first = await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("one.png", self.a_picture(), "image/png")},
            data={"description": "The first."},
            headers=headers,
        )
        second = await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("two.png", self.a_picture(), "image/png")},
            data={"description": "The second."},
            headers=headers,
        )
        assert second.json()["picture"]["description"] == "The second."
        assert second.json()["picture"]["media_id"] != first.json()["picture"]["media_id"]

    async def test_it_can_be_taken_off_again(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("dish.png", self.a_picture(), "image/png")},
            data={"description": "A stack of pancakes."},
            headers=headers,
        )
        removed = await client.delete(f"/api/v1/recipes/{recipe_id}/picture", headers=headers)
        assert removed.status_code == 200
        assert removed.json()["picture"] is None

    async def test_somebody_elses_recipe_is_not_theirs_to_illustrate(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        stranger = await sign_up(client, "neighbour@example.com")

        refused = await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("dish.png", self.a_picture(), "image/png")},
            data={"description": "Not mine."},
            headers=stranger,
        )
        assert refused.status_code == 404

    async def test_a_description_is_required(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        refused = await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("dish.png", self.a_picture(), "image/png")},
            data={"description": "  "},
            headers=headers,
        )
        assert refused.status_code == 422

    async def test_something_that_is_not_a_picture_is_refused(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        refused = await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("notes.txt", b"not a picture at all", "text/plain")},
            data={"description": "A stack of pancakes."},
            headers=headers,
        )
        assert refused.status_code == 415

    async def test_a_stranger_cannot_fetch_it(
        self, client: AsyncClient, pantry: dict[str, int]
    ) -> None:
        """ADR-063 said the first recipe photograph must not be published by a decision
        nobody revisited. This is that decision, revisited: a signed-out request is served
        a picture only when it is on an approved Academy page, and this is not one."""
        headers = await sign_up(client, "chef@example.com")
        recipe_id = await self.a_recipe(client, headers, pantry)
        added = await client.post(
            f"/api/v1/recipes/{recipe_id}/picture",
            files={"picture": ("dish.png", self.a_picture(), "image/png")},
            data={"description": "A stack of pancakes."},
            headers=headers,
        )
        media_id = added.json()["picture"]["media_id"]
        assert (await client.get(f"/api/v1/media/{media_id}")).status_code == 404
        assert (await client.get(f"/api/v1/media/{media_id}", headers=headers)).status_code == 200
