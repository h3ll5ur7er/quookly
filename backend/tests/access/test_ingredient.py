"""The ingredient registry.

An ingredient line points at a registry entry rather than holding free text. That is what
makes quantities convertible, nutrition aggregable, allergens determinable and stock
matchable — none of which work against a string.
"""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.errors import (
    IngredientAlreadyRegistered,
    IngredientNotRegistered,
    NameAlreadyMeans,
)
from quookly.contracts.ingredient import IngredientKind, Origin
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


async def register_butter() -> None:
    await registry.register(
        slug="unsalted-butter",
        kind=IngredientKind.SOLID,
        density=Decimal("0.911"),
        names={ENGLISH: ["unsalted butter", "sweet butter"], GERMAN: ["ungesalzene Butter"]},
        origin=Origin.SEED,
    )


class TestRegistering:
    async def test_a_registered_ingredient_can_be_resolved(self) -> None:
        await register_butter()
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.slug == "unsalted-butter"

    async def test_the_slug_is_the_identity_not_the_name(self) -> None:
        """Names are per locale; the slug is what a recipe actually points at."""
        await register_butter()
        english = await registry.resolve("unsalted butter", ENGLISH)
        german = await registry.resolve("ungesalzene Butter", GERMAN)
        assert english is not None and german is not None
        assert english.slug == german.slug
        assert english.id == german.id

    async def test_a_slug_may_only_be_registered_once(self) -> None:
        await register_butter()
        with pytest.raises(IngredientAlreadyRegistered):
            await register_butter()

    async def test_origin_is_recorded_so_upgrades_know_what_they_may_replace(self) -> None:
        """Seeded rows may be replaced by an upgrade; a cook's own may never be."""
        await register_butter()
        await registry.register(
            slug="grandmothers-spice-mix",
            kind=IngredientKind.POWDER,
            density=Decimal("0.5"),
            names={ENGLISH: ["grandmother's spice mix"]},
        )
        seeded = await registry.resolve("unsalted butter", ENGLISH)
        mine = await registry.resolve("grandmother's spice mix", ENGLISH)
        assert seeded is not None and mine is not None
        assert seeded.origin is Origin.SEED
        assert mine.origin is Origin.USER


class TestResolving:
    async def test_case_and_spacing_do_not_matter(self) -> None:
        """Someone typing into a form is not typing a database key."""
        await register_butter()
        for typed in ("Unsalted Butter", "  unsalted   butter ", "UNSALTED BUTTER"):
            assert await registry.resolve(typed, ENGLISH) is not None, typed

    async def test_an_alias_resolves_to_the_same_ingredient(self) -> None:
        """Recipes say cornflour or cornstarch and mean one thing."""
        await register_butter()
        alias = await registry.resolve("sweet butter", ENGLISH)
        canonical = await registry.resolve("unsalted butter", ENGLISH)
        assert alias is not None and canonical is not None
        assert alias.id == canonical.id

    async def test_the_canonical_name_comes_back_not_the_alias_typed(self) -> None:
        await register_butter()
        found = await registry.resolve("sweet butter", ENGLISH)
        assert found is not None
        assert found.name == "unsalted butter"

    async def test_the_name_is_resolved_for_the_requested_locale(self) -> None:
        await register_butter()
        found = await registry.resolve("ungesalzene Butter", GERMAN)
        assert found is not None
        assert found.name == "ungesalzene Butter"

    async def test_an_unknown_name_is_absent_not_an_error(self) -> None:
        """An unresolvable ingredient is reported to the cook, never invented (FR-9)."""
        assert await registry.resolve("moonstone", ENGLISH) is None

    async def test_a_seeded_english_name_still_resolves_on_a_swiss_instance(self) -> None:
        """The seed registry starts in English; a de-CH cook must still find it."""
        await registry.register(
            slug="caster-sugar",
            kind=IngredientKind.POWDER,
            density=Decimal("0.85"),
            names={ENGLISH: ["caster sugar"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("caster sugar", GERMAN)
        assert found is not None
        assert found.slug == "caster-sugar"

    async def test_a_locale_specific_name_wins_over_the_english_fallback(self) -> None:
        await registry.register(
            slug="cream",
            kind=IngredientKind.LIQUID,
            density=Decimal("0.994"),
            names={ENGLISH: ["cream"], GERMAN: ["Rahm"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("Rahm", GERMAN)
        assert found is not None
        assert found.name == "Rahm"


class TestDensity:
    async def test_density_is_available_for_conversion(self) -> None:
        """MeasureEngine takes density as an argument; this is where it comes from."""
        await register_butter()
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.density == Decimal("0.911")

    async def test_a_countable_ingredient_has_no_density(self) -> None:
        """An egg has a mass, but converting three eggs to millilitres is meaningless."""
        await registry.register(
            slug="egg",
            kind=IngredientKind.COUNTABLE,
            density=None,
            names={ENGLISH: ["egg"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("egg", ENGLISH)
        assert found is not None
        assert found.density is None

    async def test_densities_can_be_fetched_in_one_go(self) -> None:
        """A recipe needs every density at once; one query, not one per line."""
        await register_butter()
        await registry.register(
            slug="water",
            kind=IngredientKind.LIQUID,
            density=Decimal("1.0"),
            names={ENGLISH: ["water"]},
            origin=Origin.SEED,
        )
        butter = await registry.resolve("unsalted butter", ENGLISH)
        water = await registry.resolve("water", ENGLISH)
        assert butter is not None and water is not None

        densities = await registry.densities_for([butter.id, water.id])
        assert densities == {butter.id: Decimal("0.911"), water.id: Decimal("1.0")}


class TestKinds:
    async def test_the_kind_drives_which_unit_a_cook_prefers(self) -> None:
        """UC-6.2: powders in grams, liquids in millilitres — per kind, not globally."""
        await register_butter()
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.kind is IngredientKind.SOLID


class TestBrowsing:
    """Reading the registry as a list rather than resolving one name in it.

    `search` answers "which entry did the cook mean"; browsing answers "what is in here,
    and which of it is a guess". The second is what Phase 7 owes: an import creates
    entries nobody has looked at, and until they can be listed there is no way to find
    them.
    """

    async def a_small_registry(self) -> None:
        """Two seeded entries and one an import invented, which is the shape that matters."""
        await register_butter()
        await registry.register(
            slug="water",
            kind=IngredientKind.LIQUID,
            density=Decimal("1.0"),
            names={ENGLISH: ["water"], GERMAN: ["Wasser"]},
            origin=Origin.SEED,
        )
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.USER,
        )

    async def test_the_whole_registry_comes_back_without_a_search_term(self) -> None:
        await self.a_small_registry()
        page = await registry.browse(ENGLISH)
        assert [entry.slug for entry in page.entries] == [
            "creme-fraiche",
            "unsalted-butter",
            "water",
        ]

    async def test_a_name_that_opens_with_a_number_sorts_after_the_words(self) -> None:
        """The shipped table names its drinks by strength — "11 vol% wine white", "12 vol%
        wine red" — and plain alphabetical order puts every one of them before the letter
        A. The registry's first screen was a wine list (G3)."""
        await self.a_small_registry()
        await registry.register(
            slug="wine-white-11",
            kind=IngredientKind.LIQUID,
            density=None,
            names={ENGLISH: ["11 vol% wine white"]},
            origin=Origin.SEED,
        )

        page = await registry.browse(ENGLISH)

        assert [entry.slug for entry in page.entries] == [
            "creme-fraiche",
            "unsalted-butter",
            "water",
            "wine-white-11",
        ]

    async def test_the_total_counts_the_registry_not_the_page(self) -> None:
        """Nine hundred entries do not fit on a screen; the count is what says so."""
        await self.a_small_registry()
        page = await registry.browse(ENGLISH, limit=1)
        assert len(page.entries) == 1
        assert page.total == 3

    async def test_paging_neither_repeats_nor_skips(self) -> None:
        """Ordering has to be total, or the second page re-shows the first page's tail."""
        await self.a_small_registry()
        first = await registry.browse(ENGLISH, limit=2, offset=0)
        second = await registry.browse(ENGLISH, limit=2, offset=2)
        seen = [entry.slug for entry in first.entries + second.entries]
        assert seen == ["creme-fraiche", "unsalted-butter", "water"]

    async def test_a_term_narrows_both_the_page_and_the_total(self) -> None:
        await self.a_small_registry()
        page = await registry.browse(ENGLISH, term="butter")
        assert [entry.slug for entry in page.entries] == ["unsalted-butter"]
        assert page.total == 1

    async def test_an_alias_finds_its_entry_once(self) -> None:
        """`register_butter` gives butter two English names; matching both is still one row."""
        await self.a_small_registry()
        page = await registry.browse(ENGLISH, term="butter")
        assert page.total == 1

    async def test_origin_separates_what_an_import_invented_from_what_was_seeded(self) -> None:
        """The entries worth reviewing are the ones nobody chose to add (ADR-016)."""
        await self.a_small_registry()
        page = await registry.browse(ENGLISH, origin=Origin.USER)
        assert [entry.slug for entry in page.entries] == ["creme-fraiche"]
        assert page.total == 1

    async def test_entries_are_named_for_the_requested_locale(self) -> None:
        await self.a_small_registry()
        page = await registry.browse(GERMAN, term="Wasser")
        assert [entry.name for entry in page.entries] == ["Wasser"]

    async def test_an_entry_with_no_name_in_this_locale_falls_back_to_english(self) -> None:
        """A German cook must still see the entry, or browsing hides half the registry."""
        await self.a_small_registry()
        page = await registry.browse(GERMAN)
        assert "crème fraîche" in [entry.name for entry in page.entries]

    async def test_a_guess_an_import_made_is_visible_as_a_guess(self) -> None:
        """No density, and nobody has looked at its allergens — both have to show."""
        await self.a_small_registry()
        page = await registry.browse(ENGLISH, origin=Origin.USER)
        invented = page.entries[0]
        assert invented.density is None
        assert invented.classified is False

    async def test_an_empty_registry_is_an_empty_page_not_an_error(self) -> None:
        page = await registry.browse(ENGLISH)
        assert page.entries == []
        assert page.total == 0


class TestApproval:
    """Whether anybody has *reviewed* an entry, which is not whether anybody classified it.

    Unclassified allergens are a fact about knowledge: nobody has looked inside this
    ingredient. Approval is a fact about review: nobody has looked at this *entry*. More
    than half the shipped registry is unclassified, so the two cannot share a flag —
    reusing one would bury the handful an import invented under four hundred seeded rows
    that are exactly as the published table left them.
    """

    async def a_seeded_and_an_invented_entry(self) -> None:
        await register_butter()
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.USER,
        )

    async def test_a_seeded_entry_arrives_approved(self) -> None:
        """Nobody has to sign off nine hundred rows of a published table (ADR-050)."""
        await self.a_seeded_and_an_invented_entry()
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.approved is True

    async def test_what_an_import_invented_arrives_unapproved(self) -> None:
        await self.a_seeded_and_an_invented_entry()
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.approved is False

    async def test_approving_records_it(self) -> None:
        await self.a_seeded_and_an_invented_entry()
        await registry.approve("creme-fraiche")
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.approved is True

    async def test_approving_twice_is_the_same_as_approving_once(self) -> None:
        await self.a_seeded_and_an_invented_entry()
        await registry.approve("creme-fraiche")
        await registry.approve("creme-fraiche")
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.approved is True

    async def test_approving_does_not_make_it_a_seeded_row(self) -> None:
        """It stays the cook's own, or an upgrade would feel free to replace it (ADR-016)."""
        await self.a_seeded_and_an_invented_entry()
        await registry.approve("creme-fraiche")
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.origin is Origin.USER

    async def test_approving_an_entry_does_not_classify_its_allergens(self) -> None:
        """The safety rule. An admin saying "this entry is fine" has not said what is in
        it, and crème fraîche is milk (ADR-006)."""
        await self.a_seeded_and_an_invented_entry()
        await registry.approve("creme-fraiche")
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.classified is False

    async def test_approving_something_unregistered_is_refused(self) -> None:
        with pytest.raises(IngredientNotRegistered):
            await registry.approve("no-such-ingredient")

    async def test_browsing_can_show_only_what_awaits_review(self) -> None:
        await self.a_seeded_and_an_invented_entry()
        page = await registry.browse(ENGLISH, approved=False)
        assert [entry.slug for entry in page.entries] == ["creme-fraiche"]
        assert page.total == 1

    async def test_browsing_can_show_only_what_has_been_settled(self) -> None:
        await self.a_seeded_and_an_invented_entry()
        page = await registry.browse(ENGLISH, approved=True)
        assert [entry.slug for entry in page.entries] == ["unsalted-butter"]

    async def test_an_approved_entry_leaves_the_queue(self) -> None:
        await self.a_seeded_and_an_invented_entry()
        await registry.approve("creme-fraiche")
        page = await registry.browse(ENGLISH, approved=False)
        assert page.entries == []
        assert page.total == 0

    async def test_review_and_classification_are_different_questions(self) -> None:
        """A seeded entry the Swiss table could not answer for is approved and unchecked.

        This is the majority case in the shipped registry, and the reason these are two
        columns rather than one.
        """
        await registry.register(
            slug="wine-white",
            kind=IngredientKind.LIQUID,
            density=Decimal("0.99"),
            names={ENGLISH: ["white wine"]},
            origin=Origin.SEED,
            allergens=None,
        )
        found = await registry.resolve("white wine", ENGLISH)
        assert found is not None
        assert found.approved is True
        assert found.classified is False

    async def test_bulk_seeding_approves_what_it_seeds(self) -> None:
        """The path the nine hundred generic foods actually take (ADR-050).

        Regression: `register` set approval from origin and `register_many` did not, so a
        fresh instance opened with 864 of its 893 seeded entries in the review queue —
        exactly the "queue full of things that need no review" that ADR-051 exists to
        avoid. Every path that creates a row has to answer this the same way.
        """
        added = await registry.register_many(
            [
                registry.NewEntry(
                    slug="celeriac",
                    kind=IngredientKind.SOLID,
                    density=None,
                    names={ENGLISH: ["celeriac"]},
                    allergens=None,
                )
            ]
        )
        assert added == 1
        found = await registry.resolve("celeriac", ENGLISH)
        assert found is not None
        assert found.approved is True

    async def test_bulk_registering_a_cooks_own_entries_does_not_approve_them(self) -> None:
        added = await registry.register_many(
            [
                registry.NewEntry(
                    slug="creme-de-cassis",
                    kind=IngredientKind.LIQUID,
                    density=None,
                    names={ENGLISH: ["crème de cassis"]},
                    allergens=None,
                )
            ],
            origin=Origin.USER,
        )
        assert added == 1
        found = await registry.resolve("crème de cassis", ENGLISH)
        assert found is not None
        assert found.approved is False


class TestReadingOneEntry:
    """One entry, whole — which is what a screen that corrects it needs.

    `resolve` answers "which entry is this name", and `browse` answers "what is in the
    registry". Neither carries what an entry is called in the *other* languages, and that
    is most of what there is to correct about an imported one.
    """

    async def test_an_entry_can_be_read_by_slug(self) -> None:
        await register_butter()
        found = await registry.detail("unsalted-butter")
        assert found is not None
        assert found.entry.slug == "unsalted-butter"

    async def test_it_carries_what_it_is_called_in_every_locale(self) -> None:
        await register_butter()
        found = await registry.detail("unsalted-butter")
        assert found is not None
        assert found.names[ENGLISH] == ["unsalted butter", "sweet butter"]
        assert found.names[GERMAN] == ["ungesalzene Butter"]

    async def test_the_canonical_name_comes_first_in_its_locale(self) -> None:
        """The rest are spellings a recipe might use; the first is what to call it."""
        await register_butter()
        found = await registry.detail("unsalted-butter")
        assert found is not None
        assert found.names[ENGLISH][0] == "unsalted butter"

    async def test_an_entry_named_in_one_language_says_so(self) -> None:
        """What an import leaves behind, and the gap a correction fills."""
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.USER,
        )
        found = await registry.detail("creme-fraiche")
        assert found is not None
        assert list(found.names) == [ENGLISH]

    async def test_an_unknown_slug_is_absent_not_an_error(self) -> None:
        assert await registry.detail("no-such-thing") is None


class TestCorrecting:
    """Fixing the three facts an import guesses at: kind, density, piece weight."""

    async def an_invented_entry(self) -> None:
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.USER,
        )

    async def test_the_kind_can_be_corrected(self) -> None:
        await self.an_invented_entry()
        await registry.amend("creme-fraiche", kind=IngredientKind.LIQUID)
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.kind is IngredientKind.LIQUID

    async def test_a_density_can_be_supplied(self) -> None:
        """Without one, a scraped cup of this can never become a weight."""
        await self.an_invented_entry()
        await registry.amend("creme-fraiche", density=Decimal("0.978"))
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.density == Decimal("0.9780")

    async def test_a_density_can_be_taken_away_again(self) -> None:
        """Absent is a real answer, and a wrong density is worse than none."""
        await register_butter()
        await registry.amend("unsalted-butter", density=None)
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.density is None

    async def test_what_is_not_mentioned_is_left_alone(self) -> None:
        """Correcting the kind must not silently drop the density beside it."""
        await register_butter()
        await registry.amend("unsalted-butter", kind=IngredientKind.LIQUID)
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.density == Decimal("0.9110")

    async def test_a_piece_weight_can_be_given(self) -> None:
        await self.an_invented_entry()
        await registry.amend("creme-fraiche", piece_grams=Decimal("60"))
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.piece_grams == Decimal("60.00")

    async def test_correcting_says_nothing_about_allergens(self) -> None:
        """The safety rule. Fixing a density is not looking inside the food (ADR-006)."""
        await self.an_invented_entry()
        await registry.amend("creme-fraiche", density=Decimal("0.978"))
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.classified is False
        assert found.allergens == frozenset()

    async def test_correcting_is_not_the_same_act_as_approving(self) -> None:
        """Two statements: "this row is right" and "I have reviewed this row". An admin
        who fixes a density has not necessarily finished looking (ADR-051)."""
        await self.an_invented_entry()
        await registry.amend("creme-fraiche", kind=IngredientKind.LIQUID)
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.approved is False

    async def test_correcting_does_not_change_where_it_came_from(self) -> None:
        await self.an_invented_entry()
        await registry.amend("creme-fraiche", kind=IngredientKind.LIQUID)
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.origin is Origin.USER

    async def test_correcting_something_unregistered_is_refused(self) -> None:
        with pytest.raises(IngredientNotRegistered):
            await registry.amend("no-such-thing", kind=IngredientKind.LIQUID)


class TestRenaming:
    """Changing what a language calls an entry, rather than adding another spelling.

    `name_in` is additive and only ever sets the canonical name when a locale had none,
    so what an import decided to call something was, until now, permanent. That matters
    most for the entries an import invents: the name it records is whatever the page
    wrote, which may be a phrase rather than an ingredient.
    """

    async def test_the_canonical_name_can_be_changed(self) -> None:
        await register_butter()
        await registry.rename("unsalted-butter", ENGLISH, "sweet butter")
        found = await registry.resolve("sweet butter", ENGLISH)
        assert found is not None
        assert found.name == "sweet butter"

    async def test_a_name_it_did_not_have_becomes_the_canonical_one(self) -> None:
        await register_butter()
        await registry.rename("unsalted-butter", ENGLISH, "butter, unsalted")
        found = await registry.resolve("butter, unsalted", ENGLISH)
        assert found is not None
        assert found.name == "butter, unsalted"

    async def test_the_old_name_survives_as_a_spelling(self) -> None:
        """Demoted, not deleted. Recipes and pages out there still say the old one, and
        an import that stopped resolving it would start inventing a duplicate."""
        await register_butter()
        await registry.rename("unsalted-butter", ENGLISH, "butter, unsalted")
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.slug == "unsalted-butter"
        assert found.name == "butter, unsalted"

    async def test_only_one_name_is_canonical_afterwards(self) -> None:
        await register_butter()
        await registry.rename("unsalted-butter", ENGLISH, "butter, unsalted")
        found = await registry.detail("unsalted-butter")
        assert found is not None
        assert found.names[ENGLISH][0] == "butter, unsalted"

    async def test_renaming_one_language_leaves_the_others_alone(self) -> None:
        await register_butter()
        await registry.rename("unsalted-butter", ENGLISH, "butter, unsalted")
        german = await registry.resolve("ungesalzene Butter", GERMAN)
        assert german is not None
        assert german.name == "ungesalzene Butter"

    async def test_a_name_another_entry_means_here_is_refused(self) -> None:
        await register_butter()
        await registry.register(
            slug="margarine",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["margarine"]},
            origin=Origin.SEED,
        )
        with pytest.raises(NameAlreadyMeans):
            await registry.rename("unsalted-butter", ENGLISH, "margarine")

    async def test_a_refused_rename_changes_nothing(self) -> None:
        await register_butter()
        await registry.register(
            slug="margarine",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["margarine"]},
            origin=Origin.SEED,
        )
        with pytest.raises(NameAlreadyMeans):
            await registry.rename("unsalted-butter", ENGLISH, "margarine")
        found = await registry.resolve("unsalted butter", ENGLISH)
        assert found is not None
        assert found.name == "unsalted butter"

    async def test_renaming_to_what_it_is_already_called_is_harmless(self) -> None:
        await register_butter()
        await registry.rename("unsalted-butter", ENGLISH, "unsalted butter")
        found = await registry.detail("unsalted-butter")
        assert found is not None
        assert found.names[ENGLISH][0] == "unsalted butter"

    async def test_renaming_says_nothing_about_allergens_or_review(self) -> None:
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.USER,
        )
        await registry.rename("creme-fraiche", ENGLISH, "creme fraiche")
        found = await registry.resolve("creme fraiche", ENGLISH)
        assert found is not None
        assert found.classified is False
        assert found.approved is False

    async def test_renaming_something_unregistered_is_refused(self) -> None:
        with pytest.raises(IngredientNotRegistered):
            await registry.rename("no-such-thing", ENGLISH, "whatever")


class TestResolvingWithoutAccents:
    """A page that strips accents should still find the entry it means.

    28% of the shipped registry's name rows carry diacritics, and plenty of the web writes
    `creme fraiche`. Until now that resolved to nothing and an import invented a duplicate
    — an entry with no density and no allergen classification, sitting next to the real one.

    The fold is a **fallback**, not the lookup. An exact match always wins, and an
    ambiguous fold refuses rather than picks: `pêche` and `pèche` are different words.
    """

    async def test_a_name_written_without_its_accents_resolves(self) -> None:
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("creme fraiche", ENGLISH)
        assert found is not None
        assert found.slug == "creme-fraiche"

    async def test_the_accented_spelling_still_resolves(self) -> None:
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("crème fraîche", ENGLISH)
        assert found is not None
        assert found.slug == "creme-fraiche"

    async def test_an_exact_match_wins_over_a_folded_one(self) -> None:
        """Both exist as separate entries; the one actually typed is the one meant."""
        await registry.register(
            slug="peche-fruit",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["pêche"]},
            origin=Origin.SEED,
        )
        await registry.register(
            slug="peche-plain",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["peche"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("peche", ENGLISH)
        assert found is not None
        assert found.slug == "peche-plain"

    async def test_an_ambiguous_fold_resolves_to_nothing(self) -> None:
        """Two entries fold to one string, so folding cannot say which was meant. Refusing
        leaves the import to record and report it, which is the conservative outcome
        (ADR-029); guessing would attach one food's allergens to another's recipe."""
        await registry.register(
            slug="peche-fruit",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["pêche"]},
            origin=Origin.SEED,
        )
        await registry.register(
            slug="peche-fishing",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["pèche"]},
            origin=Origin.SEED,
        )
        assert await registry.resolve("peche", ENGLISH) is None

    async def test_two_spellings_of_one_entry_are_not_ambiguous(self) -> None:
        """Both fold to the same string but belong to the same ingredient, so there is
        nothing to be unsure about."""
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche", "creme fraiche"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("CREME FRAICHE", ENGLISH)
        assert found is not None
        assert found.slug == "creme-fraiche"

    async def test_the_canonical_name_still_comes_back(self) -> None:
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("creme fraiche", ENGLISH)
        assert found is not None
        assert found.name == "crème fraîche"

    async def test_a_folded_match_falls_back_across_to_english(self) -> None:
        """The same reach as an exact match: a Swiss instance resolves seeded names."""
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.SEED,
        )
        found = await registry.resolve("creme fraiche", GERMAN)
        assert found is not None
        assert found.slug == "creme-fraiche"

    async def test_a_name_nothing_resembles_is_still_absent(self) -> None:
        await register_butter()
        assert await registry.resolve("saffron", ENGLISH) is None


class TestSearchingWithoutAccents:
    """The picker a cook types into, which had the same gap `resolve` had.

    Unlike `resolve`, this returns a list somebody chooses from, so an ambiguous fold is
    not a hazard here — showing both `pêche` and `pèche` is the right answer, and the cook
    decides. That is why this folds freely where resolution refuses to.
    """

    async def test_a_term_without_accents_finds_the_accented_entry(self) -> None:
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.SEED,
        )
        found = await registry.search("creme", ENGLISH)
        assert [entry.slug for entry in found] == ["creme-fraiche"]

    async def test_the_accented_term_still_works(self) -> None:
        await registry.register(
            slug="creme-fraiche",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["crème fraîche"]},
            origin=Origin.SEED,
        )
        found = await registry.search("crème", ENGLISH)
        assert [entry.slug for entry in found] == ["creme-fraiche"]

    async def test_an_ambiguous_term_shows_both_rather_than_refusing(self) -> None:
        """The opposite of `resolve`, on purpose: a person is going to pick one."""
        await registry.register(
            slug="peche-fruit",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["pêche"]},
            origin=Origin.SEED,
        )
        await registry.register(
            slug="peche-fishing",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["pèche"]},
            origin=Origin.SEED,
        )
        found = await registry.search("peche", ENGLISH)
        assert {entry.slug for entry in found} == {"peche-fruit", "peche-fishing"}

    async def test_an_exact_hit_still_comes_back_once(self) -> None:
        await register_butter()
        found = await registry.search("butter", ENGLISH)
        assert [entry.slug for entry in found] == ["unsalted-butter"]

    async def test_a_term_matching_nothing_still_finds_nothing(self) -> None:
        await register_butter()
        assert await registry.search("saffron", ENGLISH) == []

    async def test_the_limit_still_holds(self) -> None:
        for index in range(5):
            await registry.register(
                slug=f"creme-{index}",
                kind=IngredientKind.SOLID,
                density=None,
                names={ENGLISH: [f"crème number {index}"]},
                origin=Origin.SEED,
            )
        assert len(await registry.search("creme", ENGLISH, limit=2)) == 2
