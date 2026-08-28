"""Storing a recipe's prose in another language (Phase 8b, ADR-032, ADR-064).

The decision this file exists to hold up: **a translation records what it translated**.
Not a `stale` flag — a flag has to be set by everything that edits a recipe, and the
failure is silent when somebody adds the next write path. A fingerprint of the source is
carried instead, and a translation whose fingerprint no longer matches is simply not used.

Invalidation by construction rather than by remembering.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access import recipe as recipes
from quookly.access import translation as stored
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import IngredientKind, Origin
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.recipe import (
    IngredientLineDraft,
    Provenance,
    RecipeDraft,
    StepDraft,
)
from quookly.contracts.translation import Translatable
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"


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
    made = await cook_access.register("chef@example.com", "Emanuel", "hash")
    assert made.id is not None
    return made.id


@pytest.fixture
async def recipe_id(cook_id: int) -> int:
    flour = await registry.register(
        slug="plain-flour",
        kind=IngredientKind.POWDER,
        density=None,
        names={ENGLISH: ["plain flour"]},
        origin=Origin.SEED,
    )
    made = await recipes.store(
        RecipeDraft(
            title="Schokoladenkuchen",
            summary="Ein einfacher Kuchen.",
            yield_quantity=Quantity(Decimal("1"), Unit.PIECE),
            provenance=Provenance.AUTHORED,
            language="de",
            lines=[IngredientLineDraft(ingredient_id=flour.id)],
            steps=[
                StepDraft(instruction="Butter und Zucker schaumig rühren."),
                StepDraft(instruction="Bei 180 °C backen."),
            ],
        ),
        cook_id,
    )
    return made.id


GERMAN_PROSE = Translatable(
    title="Schokoladenkuchen",
    summary="Ein einfacher Kuchen.",
    steps=["Butter und Zucker schaumig rühren.", "Bei 180 °C backen."],
)

ENGLISH_PROSE = Translatable(
    title="Chocolate cake",
    summary="A simple cake.",
    steps=["Cream the butter and sugar.", "Bake at 180 °C."],
)


class TestKeepingOne:
    async def test_a_translation_can_be_read_back(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        held = await stored.held(recipe_id, "en", of=GERMAN_PROSE)
        assert held is not None and held.words.title == "Chocolate cake"

    async def test_its_steps_come_back_in_order(self, recipe_id: int) -> None:
        """Paired back to the recipe by position, which is the only thing that makes a
        stored translation usable at all."""
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        held = await stored.held(recipe_id, "en", of=GERMAN_PROSE)
        assert held is not None
        assert held.words.steps == ["Cream the butter and sugar.", "Bake at 180 °C."]

    async def test_a_language_nobody_has_asked_for_is_absent(self, recipe_id: int) -> None:
        assert await stored.held(recipe_id, "fr", of=GERMAN_PROSE) is None

    async def test_keeping_it_twice_replaces_rather_than_doubles(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        await stored.keep(
            recipe_id,
            "en",
            Translatable(title="Chocolate loaf", steps=["A.", "B."]),
            of=GERMAN_PROSE,
        )
        held = await stored.held(recipe_id, "en", of=GERMAN_PROSE)
        assert held is not None and held.words.title == "Chocolate loaf"

    async def test_a_translation_a_model_made_says_so(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        held = await stored.held(recipe_id, "en", of=GERMAN_PROSE)
        assert held is not None and held.by_hand is False

    async def test_one_a_person_wrote_says_so(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE, by_hand=True)
        held = await stored.held(recipe_id, "en", of=GERMAN_PROSE)
        assert held is not None and held.by_hand is True


class TestWhenTheRecipeMovesUnderIt:
    """The whole of ADR-064, at the layer that decides it."""

    async def test_a_translation_of_words_that_changed_is_not_used(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)

        corrected = Translatable(
            title=GERMAN_PROSE.title,
            summary=GERMAN_PROSE.summary,
            steps=["Butter und Zucker schaumig schlagen.", "Bei 180 °C backen."],
        )
        assert await stored.held(recipe_id, "en", of=corrected) is None

    async def test_a_changed_title_is_enough(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        renamed = Translatable(
            title="Schokoladentorte", summary=GERMAN_PROSE.summary, steps=GERMAN_PROSE.steps
        )
        assert await stored.held(recipe_id, "en", of=renamed) is None

    async def test_a_step_added_is_enough(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        longer = Translatable(
            title=GERMAN_PROSE.title,
            summary=GERMAN_PROSE.summary,
            steps=[*GERMAN_PROSE.steps, "Abkühlen lassen."],
        )
        assert await stored.held(recipe_id, "en", of=longer) is None

    async def test_the_same_words_still_match(self, recipe_id: int) -> None:
        """A recipe saved without anything actually changing keeps its translations. The
        edit screen sends the whole recipe every time, so this is the common case."""
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        same = Translatable(
            title=GERMAN_PROSE.title, summary=GERMAN_PROSE.summary, steps=list(GERMAN_PROSE.steps)
        )
        assert await stored.held(recipe_id, "en", of=same) is not None


class TestWhatSurvivesAChange:
    async def test_a_model_translation_is_dropped_and_made_again(self, recipe_id: int) -> None:
        """Nobody's work is lost, and the next read derives a current one."""
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        moved = Translatable(title="Schokoladentorte", steps=GERMAN_PROSE.steps)

        await stored.keep(
            recipe_id,
            "en",
            Translatable(title="Chocolate gateau", steps=ENGLISH_PROSE.steps),
            of=moved,
        )
        held = await stored.held(recipe_id, "en", of=moved)
        assert held is not None and held.words.title == "Chocolate gateau"

    async def test_a_persons_translation_is_kept_even_though_it_is_not_shown(
        self, recipe_id: int
    ) -> None:
        """Kept because it is somebody's work; not shown because it describes words that
        are not there any more (ADR-064)."""
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE, by_hand=True)
        moved = Translatable(title="Schokoladentorte", steps=GERMAN_PROSE.steps)

        assert await stored.held(recipe_id, "en", of=moved) is None
        assert await stored.written_by_hand(recipe_id) == ["en"]

    async def test_a_model_translation_is_not_reported_as_somebodys_work(
        self, recipe_id: int
    ) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        assert await stored.written_by_hand(recipe_id) == []


class TestWhatAModelMayNotDo:
    """The half of ADR-064 that had nothing to trigger it yet.

    Nothing could write a `by_hand` translation before there was a screen to correct one
    on, so `keep` replacing whatever it found was harmless. It stops being harmless the
    moment a cook can correct a translation: the recipe is edited, the fingerprint stops
    matching, the next read derives a fresh machine translation — and deletes the
    correction on its way past.
    """

    async def test_a_model_may_not_replace_a_correction(self, recipe_id: int) -> None:
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE, by_hand=True)
        moved = Translatable(title="Schokoladentorte", steps=GERMAN_PROSE.steps)

        await stored.keep(
            recipe_id,
            "en",
            Translatable(title="Chocolate gateau", steps=ENGLISH_PROSE.steps),
            of=moved,
        )

        # The correction is still there, and still not shown for the moved words.
        assert await stored.written_by_hand(recipe_id) == ["en"]
        assert await stored.held(recipe_id, "en", of=moved) is None
        assert (await stored.correction(recipe_id, "en")) is not None

    async def test_a_person_may_replace_their_own_correction(self, recipe_id: int) -> None:
        """Correcting twice is correcting, not overwriting somebody else's work."""
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE, by_hand=True)
        again = Translatable(title="Chocolate gateau", steps=ENGLISH_PROSE.steps)

        await stored.keep(recipe_id, "en", again, of=GERMAN_PROSE, by_hand=True)

        held = await stored.held(recipe_id, "en", of=GERMAN_PROSE)
        assert held is not None and held.words.title == "Chocolate gateau"

    async def test_a_person_may_replace_a_models_words(self, recipe_id: int) -> None:
        """Which is what correcting one *is*."""
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE)
        corrected = Translatable(title="Chocolate cake, properly", steps=ENGLISH_PROSE.steps)

        await stored.keep(recipe_id, "en", corrected, of=GERMAN_PROSE, by_hand=True)

        held = await stored.held(recipe_id, "en", of=GERMAN_PROSE)
        assert held is not None and held.by_hand
        assert held.words.title == "Chocolate cake, properly"

    async def test_a_correction_can_be_read_back_even_when_it_is_not_current(
        self, recipe_id: int
    ) -> None:
        """What the screen offering to bring it up to date has to show: the words somebody
        wrote, beside the recipe as it now stands."""
        await stored.keep(recipe_id, "en", ENGLISH_PROSE, of=GERMAN_PROSE, by_hand=True)
        moved = Translatable(title="Schokoladentorte", steps=GERMAN_PROSE.steps)

        found = await stored.correction(recipe_id, "en")

        assert found is not None
        assert found.words.title == "Chocolate cake"
        # And it knows it no longer describes the recipe.
        assert not await stored.matches(recipe_id, "en", of=moved)
        assert await stored.matches(recipe_id, "en", of=GERMAN_PROSE)
