"""The Academy's pages (Phase 7, ADR-054 to ADR-058).

Shaped like the ingredient registry on purpose: a page has a slug, a canonical name and
its spellings per locale, a provenance and a review state, and the same things go wrong
with it.

One difference is load-bearing. The registry refuses a name a second entry claims, because
a recipe line resolving to the wrong ingredient gets the wrong food's allergens. Nothing
computes on a page, so several may claim a term and the page says so at the top
(ADR-058).
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import academy
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.academy import NewPage, PageKind, Wording
from quookly.contracts.ingredient import Origin
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"
GERMAN = "de-CH"


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


def folding() -> NewPage:
    return NewPage(
        slug="fold",
        kind=PageKind.TECHNIQUE,
        wordings={
            ENGLISH: Wording(
                name="fold",
                spellings=["fold in", "folded in"],
                summary="Combine without knocking out the air.",
                explanation="Cut down through the middle and turn the mixture over itself.",
            ),
            GERMAN: Wording(
                name="unterheben",
                spellings=["untergehoben"],
                summary="Vermengen, ohne die Luft herauszuschlagen.",
                explanation="Mit dem Teigschaber durch die Mitte stechen und wenden.",
            ),
        },
    )


def deep_frying() -> NewPage:
    return NewPage(
        slug="deep-fry",
        kind=PageKind.TECHNIQUE,
        wordings={
            ENGLISH: Wording(
                name="deep-fry",
                spellings=["deep fried"],
                summary="Cook submerged in hot fat.",
                explanation="The fat has to be hot enough that the surface seals at once.",
                caution="Never put water into hot fat.",
            )
        },
    )


class TestStoring:
    async def test_a_page_can_be_read_back(self) -> None:
        await academy.store_many([folding()])
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.name == "fold"

    async def test_it_is_read_in_the_asked_for_language(self) -> None:
        await academy.store_many([folding()])
        found = await academy.detail("fold", GERMAN)
        assert found is not None
        assert found.name == "unterheben"
        assert found.summary.startswith("Vermengen")

    async def test_a_language_it_does_not_speak_falls_back_to_english(self) -> None:
        """The same fallback the registry makes: a page a cook cannot read is a page that
        might as well not be there."""
        await academy.store_many([deep_frying()])
        found = await academy.detail("deep-fry", GERMAN)
        assert found is not None
        assert found.name == "deep-fry"

    async def test_a_caution_comes_with_it(self) -> None:
        await academy.store_many([deep_frying()])
        found = await academy.detail("deep-fry", ENGLISH)
        assert found is not None
        assert found.caution == "Never put water into hot fat."

    async def test_a_page_without_one_says_nothing(self) -> None:
        """Restraint is what keeps a caution worth reading."""
        await academy.store_many([folding()])
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.caution is None

    async def test_the_spellings_come_with_it(self) -> None:
        await academy.store_many([folding()])
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert set(found.spellings) == {"fold in", "folded in"}

    async def test_a_seeded_page_is_shipped_and_needs_no_review(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.origin is Origin.SEED
        assert found.approved is True
        assert found.generated is False

    async def test_storing_again_adds_nothing(self) -> None:
        """Start-up runs this every boot and must not accumulate copies."""
        assert await academy.store_many([folding()]) == 1
        assert await academy.store_many([folding()]) == 0
        page = await academy.browse(ENGLISH)
        assert len(page) == 1

    async def test_a_page_that_is_not_there_is_absent(self) -> None:
        assert await academy.detail("no-such-thing", ENGLISH) is None


class TestBrowsing:
    async def test_every_page_comes_back(self) -> None:
        await academy.store_many([folding(), deep_frying()])
        assert {one.slug for one in await academy.browse(ENGLISH)} == {"fold", "deep-fry"}

    async def test_they_come_back_in_reading_order(self) -> None:
        """Alphabetical by the name the reader sees, not by slug: a German cook looking
        for *unterheben* should not have to know it is filed under `fold`."""
        await academy.store_many([folding(), deep_frying()])
        assert [one.name for one in await academy.browse(GERMAN)] == [
            "deep-fry",
            "unterheben",
        ]

    async def test_a_section_can_be_asked_for_on_its_own(self) -> None:
        """Techniques are one section of the Academy, not the whole of it (ADR-057)."""
        await academy.store_many([folding()])
        assert len(await academy.browse(ENGLISH, kind=PageKind.TECHNIQUE)) == 1

    async def test_an_empty_academy_is_an_empty_list(self) -> None:
        assert await academy.browse(ENGLISH) == []


class TestSharedTerms:
    """Several pages may claim one term, which the registry refuses and this allows.

    Nothing computes on a page: a cook who lands on the wrong one reads a paragraph about
    the wrong thing and clicks again, where a recipe line resolving to the wrong
    ingredient gets the wrong food's allergens (ADR-058).
    """

    async def butter_twice(self) -> None:
        await academy.store_many(
            [
                NewPage(
                    slug="beurre-monte",
                    kind=PageKind.TECHNIQUE,
                    wordings={
                        ENGLISH: Wording(
                            name="butter",
                            spellings=[],
                            summary="Finishing a sauce with cold butter.",
                            explanation="Whisked in off the heat, it thickens and glosses.",
                        )
                    },
                ),
                NewPage(
                    slug="butter",
                    kind=PageKind.TECHNIQUE,
                    wordings={
                        ENGLISH: Wording(
                            name="butter",
                            spellings=[],
                            summary="Churned cream.",
                            explanation=("Around eighty per cent fat, the rest water and milk."),
                        )
                    },
                ),
            ]
        )

    async def test_both_pages_are_stored(self) -> None:
        """The registry would have refused the second. Here the second is the point."""
        await self.butter_twice()
        assert len(await academy.browse(ENGLISH)) == 2

    async def test_a_term_reports_everyone_who_claims_it(self) -> None:
        await self.butter_twice()
        claiming = await academy.claimants_of("butter", ENGLISH)
        assert {one.slug for one in claiming} == {"beurre-monte", "butter"}

    async def test_a_term_only_one_page_claims_reports_one(self) -> None:
        await academy.store_many([folding()])
        assert [one.slug for one in await academy.claimants_of("fold", ENGLISH)] == ["fold"]

    async def test_a_spelling_finds_its_page_too(self) -> None:
        await academy.store_many([folding()])
        assert [one.slug for one in await academy.claimants_of("folded in", ENGLISH)] == ["fold"]

    async def test_accents_and_case_do_not_matter(self) -> None:
        await academy.store_many([folding()])
        assert [one.slug for one in await academy.claimants_of("FOLDED IN", ENGLISH)] == ["fold"]

    async def test_a_term_nobody_claims_reports_nobody(self) -> None:
        await academy.store_many([folding()])
        assert await academy.claimants_of("saffron", ENGLISH) == []

    async def test_a_page_knows_who_else_claims_its_name(self) -> None:
        """The hatnote: a page whose term is shared says so and names the others."""
        await self.butter_twice()
        found = await academy.detail("butter", ENGLISH)
        assert found is not None
        assert [one.slug for one in found.also] == ["beurre-monte"]

    async def test_a_page_nobody_shares_with_has_no_hatnote(self) -> None:
        await academy.store_many([folding()])
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.also == []
