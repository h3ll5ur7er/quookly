"""What starting the application does (ADR-016, ADR-045).

The lifespan is the one piece of assembly nothing else runs. Route tests drive the app
through `ASGITransport`, which does not start it; the end-to-end suite *does* — it boots
`quookly.api:app` under uvicorn against an empty database on every run — so a mistake here
would be caught, three minutes later, as "the server did not come up".

These tests exist for the diagnosis rather than the coverage. "The registry was not stocked
at start-up" is a sentence somebody can act on.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import recipe as recipe_access
from quookly.access import search
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app, lifespan
from quookly.contracts.events import MealCooked
from quookly.contracts.ingredient import IngredientKind
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.recipe import (
    IngredientLineDraft,
    Provenance,
    RecipeDraft,
    StepDraft,
)
from quookly.managers import pantry as pantry_manager
from quookly.utilities import events
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"


@pytest.fixture(autouse=True)
async def a_fresh_instance(monkeypatch: MonkeyPatch) -> AsyncIterator[None]:
    """An empty database with a schema, which is what a first start-up meets."""
    monkeypatch.setenv("QUOOKLY_DATABASE_URL", "sqlite+aiosqlite://")
    get_settings.cache_clear()
    get_engine.cache_clear()
    async with get_engine().begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    yield
    events.forget_everything()
    await dispose_engine()
    get_settings.cache_clear()
    get_engine.cache_clear()


class TestStartingUp:
    """Everything is asserted *inside* the context. The lifespan disposes the engine on
    the way out, and this instance's database lives in that engine's one connection — so
    after the block there is nothing left to ask, which is exactly right: these are claims
    about an application that is serving."""

    async def test_the_registry_is_stocked(self) -> None:
        async with lifespan(app):
            assert await registry.resolve("plain flour", ENGLISH) is not None

    async def test_the_generic_foods_are_there_too(self) -> None:
        """The call that had never been executed by this suite. It is one line in the
        lifespan and nine hundred ingredients on a cook's screen."""
        async with lifespan(app):
            assert await registry.resolve("carrot", ENGLISH) is not None
            assert await registry.resolve("Zwiebel", "de-CH") is not None

    async def test_the_published_figures_are_attached(self) -> None:
        async with lifespan(app):
            carrot = await registry.resolve("carrot", ENGLISH)
            assert carrot is not None
            assert await registry.profiles_for([carrot.id])

    async def test_the_search_index_is_built(self) -> None:
        """Rebuilt at every start rather than migrated, so a change to what is indexed
        costs nothing to roll out and cannot be half-applied — which also means an instance
        that skipped it has a search box that finds nothing.

        The recipe is stored and then **taken back out of the index**, which is what makes
        this a test of the rebuild rather than of storing. Two earlier versions were
        vacuous: one asserted an empty instance returned no hits, which the schema alone
        satisfies since the index table is created with the others; the next stored a
        recipe and asserted it was findable, which `store` had already indexed on the way
        in. Both passed with `reindex()` deleted from the lifespan, which is how they were
        found out.
        """
        cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
        flour = await registry.register(
            slug="a-flour",
            kind=IngredientKind.POWDER,
            density=None,
            names={ENGLISH: ["a flour"]},
        )
        stored = await recipe_access.store(
            RecipeDraft(
                title="Shortbread",
                summary="Three ingredients.",
                yield_quantity=Quantity(Decimal(4), Unit.SERVING),
                provenance=Provenance.AUTHORED,
                lines=[
                    IngredientLineDraft(
                        ingredient_id=flour.id, quantity=Quantity(Decimal(100), Unit.GRAM)
                    )
                ],
                steps=[StepDraft(instruction="Cook it.")],
            ),
            cook.id,
        )
        await search.remove(stored.id)
        assert await search.query("shortbread", cook_id=cook.id, limit=5) == []

        async with lifespan(app):
            assert await search.query("shortbread", cook_id=cook.id, limit=5)

    async def test_the_event_bus_is_wired(self, monkeypatch: MonkeyPatch) -> None:
        """Patched before the lifespan, because `wire_subscriptions` takes the handler by
        reference: an instance that started without this consumes no stock when a meal is
        cooked, and nothing says so (ADR-004)."""
        heard = []

        async def listening(event: MealCooked) -> None:
            heard.append(event)

        monkeypatch.setattr(pantry_manager, "on_meal_cooked", listening)
        async with lifespan(app):
            await events.publish(MealCooked(cook_id=1, plan_slot_id=1, at=datetime.now(UTC)))
        assert heard, "a meal was cooked at start-up and the pantry did not hear it"


class TestStartingAgain:
    """A restart, which is the ordinary case and the one that must not accumulate."""

    @pytest.fixture(autouse=True)
    async def on_disk(self, monkeypatch: MonkeyPatch, tmp_path: Path) -> AsyncIterator[None]:
        # A file rather than memory: the lifespan disposes the engine on the way out, and
        # an in-memory database goes with it — so a second start would meet a fresh one
        # and this test would assert nothing.
        monkeypatch.setenv("QUOOKLY_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'q.db'}")
        get_settings.cache_clear()
        get_engine.cache_clear()
        async with get_engine().begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)
        yield
        events.forget_everything()
        await dispose_engine()
        get_settings.cache_clear()
        get_engine.cache_clear()

    async def test_a_second_start_adds_no_second_copy(self) -> None:
        async with lifespan(app):
            first = len(await registry.search("carrot", ENGLISH, limit=50))
        get_engine.cache_clear()
        async with lifespan(app):
            again = len(await registry.search("carrot", ENGLISH, limit=50))
        assert first == again
