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
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import academy
from quookly.access import cook as cook_access
from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.academy import NewPage, PageKind, Wording
from quookly.contracts.errors import (
    IngredientNotNamed,
    PageAlreadyWritten,
    PageNotWritten,
)
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.matching import Named
from quookly.utilities.configuration import get_settings

ENGLISH = "en-GB"


async def spotting_only(locale: str) -> list[Named]:
    """Just the vocabulary half of `vocabulary`, for the tests that are about it."""
    entries, _ = await academy.vocabulary(locale)
    return entries


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


@pytest.fixture
async def cook_id() -> int:
    """A real account, because a page records who wrote it and the column is a key."""
    cook = await cook_access.register("chef@example.com", "Emanuel", "hash")
    return cook.id


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
            ],
            origin=Origin.SEED,
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
        await academy.store_many([folding()], origin=Origin.SEED)
        assert [one.slug for one in await academy.claimants_of("fold", ENGLISH)] == ["fold"]

    async def test_a_spelling_finds_its_page_too(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        assert [one.slug for one in await academy.claimants_of("folded in", ENGLISH)] == ["fold"]

    async def test_accents_and_case_do_not_matter(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        assert [one.slug for one in await academy.claimants_of("FOLDED IN", ENGLISH)] == ["fold"]

    async def test_a_term_nobody_claims_reports_nobody(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        assert await academy.claimants_of("saffron", ENGLISH) == []

    async def test_a_page_knows_who_else_claims_its_name(self) -> None:
        """The hatnote: a page whose term is shared says so and names the others."""
        await self.butter_twice()
        found = await academy.detail("butter", ENGLISH)
        assert found is not None
        assert [one.slug for one in found.also] == ["beurre-monte"]

    async def test_a_page_nobody_shares_with_has_no_hatnote(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.also == []


class TestWhatMayBeSpottedInAStep:
    """A name that is also an ordinary word stays the name and stops being a term.

    Found by measuring rather than by reasoning: run over real steps, `sieben` matched
    "sieben Minuten" — German for *seven minutes* — and English `rest` matched "the rest of
    the flour". The page keeps its name; it is found by its spellings instead (ADR-055).
    """

    async def sifting(self, matches: bool) -> None:
        await academy.store_many(
            [
                NewPage(
                    slug="sift",
                    kind=PageKind.TECHNIQUE,
                    wordings={
                        GERMAN: Wording(
                            name="sieben",
                            spellings=["gesiebt", "durchsieben"],
                            summary="Eine trockene Zutat durch ein Sieb geben.",
                            explanation="Zerteilt Klumpen und lässt Mehl locker fallen.",
                            name_matches=matches,
                        )
                    },
                )
            ],
            origin=Origin.SEED,
        )

    async def test_a_matchable_name_is_offered_for_spotting(self) -> None:
        await self.sifting(matches=True)
        offered = await spotting_only(GERMAN)
        assert "sieben" in offered[0].names

    async def test_a_name_with_another_life_is_not(self) -> None:
        await self.sifting(matches=False)
        offered = await spotting_only(GERMAN)
        assert "sieben" not in offered[0].names

    async def test_its_spellings_are_still_offered(self) -> None:
        """The page is still findable — by the words that only mean it."""
        await self.sifting(matches=False)
        offered = await spotting_only(GERMAN)
        assert set(offered[0].names) == {"gesiebt", "durchsieben"}

    async def test_it_is_still_the_page_name(self) -> None:
        await self.sifting(matches=False)
        found = await academy.detail("sift", GERMAN)
        assert found is not None
        assert found.name == "sieben"

    async def test_a_term_still_finds_the_page_when_asked_directly(self) -> None:
        """Not matchable in a step is not the same as not a term: a cook who types it
        should still arrive."""
        await self.sifting(matches=False)
        assert [one.slug for one in await academy.claimants_of("sieben", GERMAN)] == ["sift"]

    async def test_nothing_offers_a_page_that_has_none(self) -> None:
        assert await spotting_only(ENGLISH) == []


class TestCorrecting:
    """An administrator correcting a page, one language at a time (ADR-057).

    Replacement rather than patching, for the reason ADR-059 gives for recipes: a wording
    is a small whole, and patching its spellings would need an instruction for reordering
    that nobody asked for.
    """

    async def test_the_explanation_can_be_rewritten(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        await academy.amend(
            "fold",
            ENGLISH,
            Wording(
                name="fold",
                spellings=["fold in"],
                summary="Combine without knocking out the air.",
                explanation="Cut down, sweep along the bottom, turn it over itself.",
            ),
        )
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.explanation.startswith("Cut down, sweep")

    async def test_the_spellings_are_replaced_not_added_to(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        await academy.amend(
            "fold",
            ENGLISH,
            Wording(
                name="fold",
                spellings=["folded in"],
                summary="Combine without knocking out the air.",
                explanation="Cut down through the middle and turn the mixture over itself.",
            ),
        )
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.spellings == ["folded in"]

    async def test_a_language_it_did_not_speak_can_be_added(self) -> None:
        """This is how a translation arrives: correcting a locale that has no wording yet."""
        await academy.store_many([deep_frying()], origin=Origin.SEED)
        await academy.amend(
            "deep-fry",
            GERMAN,
            Wording(
                name="frittieren",
                spellings=["frittiert"],
                summary="In heissem Fett schwimmend garen.",
                explanation="Das Fett muss heiss genug sein, dass die Oberfläche schliesst.",
            ),
        )
        found = await academy.detail("deep-fry", GERMAN)
        assert found is not None
        assert found.name == "frittieren"

    async def test_the_other_languages_are_left_alone(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        await academy.amend(
            "fold",
            ENGLISH,
            Wording(
                name="fold",
                spellings=[],
                summary="Changed.",
                explanation="Changed as well, at some length so the check passes.",
            ),
        )
        german = await academy.detail("fold", GERMAN)
        assert german is not None
        assert german.name == "unterheben"

    async def test_a_caution_can_be_taken_away(self) -> None:
        """Absent is a real answer: a warning that does not apply is worse than none."""
        await academy.store_many([deep_frying()], origin=Origin.SEED)
        await academy.amend(
            "deep-fry",
            ENGLISH,
            Wording(
                name="deep-fry",
                spellings=["deep fried"],
                summary="Cook submerged in hot fat.",
                explanation="The fat has to be hot enough that the surface seals at once.",
                caution=None,
            ),
        )
        found = await academy.detail("deep-fry", ENGLISH)
        assert found is not None
        assert found.caution is None

    async def test_a_name_can_stop_being_matchable(self) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        await academy.amend(
            "fold",
            ENGLISH,
            Wording(
                name="fold",
                spellings=["fold in"],
                summary="Combine without knocking out the air.",
                explanation="Cut down through the middle and turn the mixture over itself.",
                name_matches=False,
            ),
        )
        entries, _ = await academy.vocabulary(ENGLISH)
        assert "fold" not in entries[0].names
        assert "fold in" in entries[0].names

    async def test_correcting_does_not_approve_it(self) -> None:
        """Two statements, the same argument ADR-051 made for the registry: fixing a
        sentence is not saying somebody has read the page."""
        await academy.store_many([folding()], origin=Origin.USER)
        await academy.amend(
            "fold",
            ENGLISH,
            Wording(
                name="fold",
                spellings=[],
                summary="Changed.",
                explanation="Changed as well, at some length so the check passes.",
            ),
        )
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.approved is False

    async def test_correcting_does_not_claim_a_person_wrote_it(self) -> None:
        """`generated` records who wrote it first, and correcting a sentence does not undo
        that. Approving is what stops the page reading as unchecked."""
        await academy.store_many([folding()], origin=Origin.USER)
        await academy.approve("fold")
        found = await academy.detail("fold", ENGLISH)
        assert found is not None
        assert found.approved is True
        assert found.generated is False

    async def test_correcting_something_that_is_not_there_is_refused(self) -> None:
        with pytest.raises(PageNotWritten):
            await academy.amend(
                "no-such-thing",
                ENGLISH,
                Wording(
                    name="x",
                    spellings=[],
                    summary="A summary long enough.",
                    explanation="An explanation long enough to pass.",
                ),
            )

    async def test_approving_something_that_is_not_there_is_refused(self) -> None:
        with pytest.raises(PageNotWritten):
            await academy.approve("no-such-thing")


class TestAPageACookWrote:
    """Writing one, and what it may do before anybody has read it (ADR-060).

    The rule the whole unit turns on: an unreviewed page is readable, and its terms are
    not matched into anybody's recipe. Marking works when the reader has come to the page;
    it does nothing when the page arrives underlined inside a recipe three screens away.
    """

    async def test_what_a_cook_writes_can_be_read_back(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        page = await academy.detail("fold", ENGLISH)
        assert page is not None
        assert page.name == "fold"

    async def test_it_arrives_unreviewed(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        page = await academy.detail("fold", ENGLISH)
        assert page is not None
        assert page.approved is False

    async def test_it_says_who_wrote_it(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        standing = await academy.standing_of("fold")
        assert standing is not None and standing.written_by == cook_id

    async def test_a_seeded_page_was_written_by_nobody_here(self, cook_id: int) -> None:
        """Absent rather than nought: this instance shipped with it."""
        await academy.store_many([folding()], origin=Origin.SEED)
        standing = await academy.standing_of("fold")
        assert standing is not None and standing.written_by is None

    async def test_a_cook_cannot_take_a_slug_that_is_taken(self, cook_id: int) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        with pytest.raises(PageAlreadyWritten):
            await academy.write(folding(), cook_id=cook_id)

    async def test_it_is_listed_so_its_author_can_see_it(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        assert [one.slug for one in await academy.browse(ENGLISH)] == ["fold"]

    async def test_but_it_is_not_matched_into_a_recipe(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        assert await spotting_only(ENGLISH) == []

    async def test_and_it_does_not_answer_for_a_term(self, cook_id: int) -> None:
        """`/academy/terms/{term}` is where a step's word leads, so a page that has not
        been read cannot be what a word leads to."""
        await academy.write(folding(), cook_id=cook_id)
        assert await academy.claimants_of("fold in", ENGLISH) == []

    async def test_approving_turns_its_terms_on(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        await academy.approve("fold")
        assert [one.slug for one in await spotting_only(ENGLISH)] == ["fold"]
        assert [one.slug for one in await academy.claimants_of("fold in", ENGLISH)] == ["fold"]

    async def test_a_seeded_page_needs_no_approving_to_be_matched(self, cook_id: int) -> None:
        """Unchanged, and the reason nothing about the fifty shipped pages moves."""
        await academy.store_many([folding()], origin=Origin.SEED)
        assert [one.slug for one in await spotting_only(ENGLISH)] == ["fold"]

    async def test_the_list_says_which_pages_nobody_has_read(self, cook_id: int) -> None:
        """So an author browsing sees their own page marked, rather than wondering why it
        is not underlined in their recipes."""
        await academy.store_many([deep_frying()], origin=Origin.SEED)
        await academy.write(folding(), cook_id=cook_id)

        listed = {one.slug: one.approved for one in await academy.browse(ENGLISH)}
        assert listed == {"deep-fry": True, "fold": False}

    async def test_the_queue_is_what_nobody_has_read(self, cook_id: int) -> None:
        await academy.store_many([deep_frying()], origin=Origin.SEED)
        await academy.write(folding(), cook_id=cook_id)
        assert [one.slug for one in await academy.browse(ENGLISH, approved=False)] == ["fold"]
        assert [one.slug for one in await academy.browse(ENGLISH, approved=True)] == ["deep-fry"]


class TestDecliningAPage:
    """Put away rather than destroyed, the same choice a recipe makes."""

    async def test_a_declined_page_leaves_the_academy(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        assert await academy.archive("fold") is True
        assert await academy.browse(ENGLISH) == []

    async def test_it_leaves_the_queue_too(self, cook_id: int) -> None:
        """Otherwise declining it once means being asked about it forever."""
        await academy.write(folding(), cook_id=cook_id)
        await academy.archive("fold")
        assert await academy.browse(ENGLISH, approved=False) == []

    async def test_it_cannot_be_read(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        await academy.archive("fold")
        assert await academy.detail("fold", ENGLISH) is None

    async def test_nothing_is_destroyed(self, cook_id: int) -> None:
        """An administrator can still find it, which is what makes declining reversible."""
        await academy.write(folding(), cook_id=cook_id)
        await academy.archive("fold")
        standing = await academy.standing_of("fold")
        assert standing is not None and standing.written_by == cook_id

    async def test_declining_an_approved_page_still_takes_it_out_of_recipes(
        self, cook_id: int
    ) -> None:
        await academy.write(folding(), cook_id=cook_id)
        await academy.approve("fold")
        await academy.archive("fold")
        assert await spotting_only(ENGLISH) == []

    async def test_a_page_that_is_not_there_declines_to_nothing(self, cook_id: int) -> None:
        assert await academy.archive("nothing-of-the-sort") is False

    async def test_it_can_be_brought_back(self, cook_id: int) -> None:
        await academy.write(folding(), cook_id=cook_id)
        await academy.archive("fold")
        assert await academy.restore("fold") is True
        assert [one.slug for one in await academy.browse(ENGLISH)] == ["fold"]


class TestAPageAboutAFood:
    """The ingredient section: prose here, facts read from the registry (ADR-061)."""

    ABOUT = "about-plain-flour"

    async def flour(self, **facts: object) -> int:
        made = await registry.register(
            slug="plain-flour",
            kind=IngredientKind.POWDER,
            density=Decimal("0.593"),
            names={ENGLISH: ["plain flour"]},
            origin=Origin.SEED,
            **facts,  # type: ignore[arg-type]
        )
        assert made.id is not None
        return made.id

    def about(self) -> NewPage:
        return NewPage(
            slug=self.ABOUT,
            kind=PageKind.INGREDIENT,
            wordings={
                ENGLISH: Wording(
                    name="plain flour",
                    spellings=["all-purpose flour"],
                    summary="The everyday one.",
                    explanation="Around ten per cent protein, which is why it is the everyday one.",
                )
            },
        )

    async def test_a_page_can_be_about_a_food(self, cook_id: int) -> None:
        entry = await self.flour()
        await academy.write(self.about(), cook_id=cook_id, ingredient_id=entry)
        assert await academy.entry_of(self.ABOUT) == entry

    async def test_it_shows_the_registrys_facts(self, cook_id: int) -> None:
        await self.flour(allergens=frozenset({Allergen.GLUTEN}))
        await academy.write(self.about(), cook_id=cook_id, ingredient_id=await self.entry())

        page = await academy.detail(self.ABOUT, ENGLISH)
        assert page is not None and page.entry is not None
        assert page.entry.allergens == [Allergen.GLUTEN]
        assert page.entry.classified is True
        assert page.entry.kind is IngredientKind.POWDER

    async def test_unclassified_is_not_the_same_as_none(self, cook_id: int) -> None:
        """The whole reason `classified` travels with the list. A page rendering an
        unexamined food as "allergens: none" is the ADR-006 failure with typography."""
        await self.flour()
        await academy.write(self.about(), cook_id=cook_id, ingredient_id=await self.entry())

        page = await academy.detail(self.ABOUT, ENGLISH)
        assert page is not None and page.entry is not None
        assert page.entry.allergens == []
        assert page.entry.classified is False

    async def test_correcting_the_registry_corrects_the_page(self, cook_id: int) -> None:
        """No copy, so nothing to go stale — which is the whole of the decision."""
        await self.flour()
        await academy.write(self.about(), cook_id=cook_id, ingredient_id=await self.entry())
        await registry.classify("plain-flour", frozenset({Allergen.GLUTEN}))

        page = await academy.detail(self.ABOUT, ENGLISH)
        assert page is not None and page.entry is not None
        assert page.entry.allergens == [Allergen.GLUTEN]

    async def test_a_technique_page_is_about_no_food(self, cook_id: int) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        page = await academy.detail("fold", ENGLISH)
        assert page is not None
        assert page.entry is None

    async def test_an_ingredient_page_must_name_an_entry(self, cook_id: int) -> None:
        with pytest.raises(IngredientNotNamed):
            await academy.write(self.about(), cook_id=cook_id)

    async def test_the_section_can_be_asked_for_on_its_own(self, cook_id: int) -> None:
        await academy.store_many([folding()], origin=Origin.SEED)
        await academy.write(self.about(), cook_id=cook_id, ingredient_id=await self.flour())

        listed = await academy.browse(ENGLISH, kind=PageKind.INGREDIENT)
        assert [one.slug for one in listed] == [self.ABOUT]

    async def entry(self) -> int:
        found = await registry.detail("plain-flour")
        assert found is not None
        return found.entry.id

    async def test_the_pages_about_a_food_can_be_found_from_it(self, cook_id: int) -> None:
        """The other direction. A registry entry is where the facts are corrected, so it
        is where somebody looking at the facts should be able to reach the prose."""
        entry = await self.flour()
        await academy.write(self.about(), cook_id=cook_id, ingredient_id=entry)

        found = await academy.pages_about(entry, ENGLISH)
        assert [one.slug for one in found] == [self.ABOUT]

    async def test_a_food_nobody_has_written_about_has_no_pages(self, cook_id: int) -> None:
        assert await academy.pages_about(await self.flour(), ENGLISH) == []

    async def test_a_page_put_away_is_not_reachable_from_the_food(self, cook_id: int) -> None:
        entry = await self.flour()
        await academy.write(self.about(), cook_id=cook_id, ingredient_id=entry)
        await academy.archive(self.ABOUT)

        assert await academy.pages_about(entry, ENGLISH) == []
