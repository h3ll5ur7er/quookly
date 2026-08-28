"""Reading the ingredient registry through the API (Phase 7).

The registry is the largest list in the app and, until this endpoint, the only part of
the system a cook could not look at. That matters because importing a recipe *creates*
entries: a line that resolves to nothing cannot be shopped for, scaled or judged, so
`RecipeManager` invents one. What it invents is a guess — `SOLID`, no density, allergens
deliberately unclassified because nobody has looked (ADR-006, ADR-029).

Nothing surfaced those guesses. These tests are about making them findable.
"""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.api import app
from quookly.contracts.ingredient import Allergen, IngredientKind, Origin
from quookly.contracts.nutrition import Nutrient, NutrientProfile, NutritionSource
from quookly.utilities.configuration import get_settings
from tests.support import PASSWORD, sign_up

REGISTRY = "/api/v1/registry"
ONE = f"{REGISTRY}/creme-fraiche"
ENGLISH = "en-GB"
GERMAN = "de-CH"


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
async def admin(client: AsyncClient) -> dict[str, str]:
    """The first account on a fresh instance, which is the one that administers it."""
    claimed = await client.post(
        "/api/v1/accounts/bootstrap",
        json={"email": "admin@example.com", "display_name": "Admin", "password": PASSWORD},
    )
    return {"Authorization": f"Bearer {claimed.json()['token']}"}


@pytest.fixture
async def invented() -> None:
    """One entry of the kind an import leaves behind, and nothing else.

    Separate from `stocked` because claiming an instance seeds the registry: an admin
    fixture and a fixture that registers butter cannot both run.
    """
    await registry.register(
        slug="creme-fraiche",
        kind=IngredientKind.SOLID,
        density=None,
        names={ENGLISH: ["crème fraîche"]},
        origin=Origin.USER,
    )


@pytest.fixture
async def stocked() -> None:
    """Two entries somebody chose, and one an import invented."""
    await registry.register(
        slug="unsalted-butter",
        kind=IngredientKind.SOLID,
        density=Decimal("0.911"),
        names={ENGLISH: ["unsalted butter"], GERMAN: ["ungesalzene Butter"]},
        origin=Origin.SEED,
        allergens=frozenset({Allergen.MILK}),
    )
    await registry.register(
        slug="water",
        kind=IngredientKind.LIQUID,
        density=Decimal("1.0"),
        names={ENGLISH: ["water"], GERMAN: ["Wasser"]},
        origin=Origin.SEED,
        allergens=frozenset(),
    )
    await registry.register(
        slug="creme-fraiche",
        kind=IngredientKind.SOLID,
        density=None,
        names={ENGLISH: ["crème fraîche"]},
        origin=Origin.USER,
    )


def by_slug(body: Any) -> dict[str, Any]:
    return {entry["slug"]: entry for entry in body["entries"]}


class TestReading:
    async def test_the_registry_can_be_listed(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        response = await client.get(REGISTRY, headers=cook)
        assert response.status_code == 200
        assert set(by_slug(response.json())) == {"unsalted-butter", "water", "creme-fraiche"}

    async def test_the_total_says_how_much_there_is(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"limit": 1}, headers=cook)).json()
        assert len(body["entries"]) == 1
        assert body["total"] == 3

    async def test_an_entry_carries_what_is_needed_to_judge_it(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """Kind, density and origin — the three fields an import guesses at."""
        butter = by_slug((await client.get(REGISTRY, headers=cook)).json())["unsalted-butter"]
        assert butter["name"] == "unsalted butter"
        assert butter["kind"] == "solid"
        assert butter["density"] == "0.9110"
        assert butter["origin"] == "seed"

    async def test_signing_in_is_required(self, client: AsyncClient, stocked: None) -> None:
        assert (await client.get(REGISTRY)).status_code == 401


class TestFindingTheGuesses:
    async def test_unclassified_allergens_are_not_reported_as_none(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """The safety rule, at the edge of the API (ADR-006).

        Water carries no allergens and somebody said so. Crème fraîche carries none
        *recorded*, because nobody has looked — and it is milk. Both have an empty list,
        so the empty list cannot be what a client reads.
        """
        entries = by_slug((await client.get(REGISTRY, headers=cook)).json())
        assert entries["water"]["allergens"] == []
        assert entries["water"]["classified"] is True
        assert entries["creme-fraiche"]["allergens"] == []
        assert entries["creme-fraiche"]["classified"] is False

    async def test_what_an_import_invented_can_be_listed_on_its_own(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"origin": "user"}, headers=cook)).json()
        assert set(by_slug(body)) == {"creme-fraiche"}
        assert body["total"] == 1

    async def test_a_guess_shows_its_missing_density(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        entries = by_slug((await client.get(REGISTRY, headers=cook)).json())
        assert entries["creme-fraiche"]["density"] is None

    async def test_an_unknown_origin_is_refused_rather_than_ignored(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """Silently listing everything would answer a question nobody asked."""
        assert (
            await client.get(REGISTRY, params={"origin": "invented"}, headers=cook)
        ).status_code == 422


class TestSearching:
    async def test_a_term_narrows_the_list(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"search": "butter"}, headers=cook)).json()
        assert set(by_slug(body)) == {"unsalted-butter"}
        assert body["total"] == 1

    async def test_a_term_matching_nothing_is_an_empty_page(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        body = (await client.get(REGISTRY, params={"search": "saffron"}, headers=cook)).json()
        assert body["entries"] == []
        assert body["total"] == 0


class TestLanguage:
    async def test_entries_are_named_in_the_cooks_language(
        self, client: AsyncClient, stocked: None
    ) -> None:
        """A registry a Swiss cook reads in English is a registry they cannot correct."""
        swiss = await sign_up(client, "koch@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": GERMAN}, headers=swiss)
        entries = by_slug((await client.get(REGISTRY, headers=swiss)).json())
        assert entries["water"]["name"] == "Wasser"

    async def test_an_entry_with_no_name_in_that_language_still_appears(
        self, client: AsyncClient, stocked: None
    ) -> None:
        """Falling back is what keeps browsing complete; hiding it would hide the guesses."""
        swiss = await sign_up(client, "koch@example.com")
        await client.put("/api/v1/setup/locale", json={"locale": GERMAN}, headers=swiss)
        entries = by_slug((await client.get(REGISTRY, headers=swiss)).json())
        assert entries["creme-fraiche"]["name"] == "crème fraîche"


class TestReviewing:
    """Approving an entry — a fact about review, not about what is inside it (ADR-051)."""

    async def test_a_seeded_entry_needs_no_review(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        entries = by_slug((await client.get(REGISTRY, headers=cook)).json())
        assert entries["unsalted-butter"]["approved"] is True

    async def test_what_an_import_invented_is_flagged(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        entries = by_slug((await client.get(REGISTRY, headers=cook)).json())
        assert entries["creme-fraiche"]["approved"] is False

    async def test_the_queue_can_be_listed_on_its_own(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """The useful filter. Narrowing by origin cannot do this job once an entry has
        been approved: it stays the cook's own for ever (ADR-016)."""
        body = (await client.get(REGISTRY, params={"approved": False}, headers=cook)).json()
        assert set(by_slug(body)) == {"creme-fraiche"}
        assert body["total"] == 1

    async def test_an_admin_can_approve_one(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.post(f"{REGISTRY}/creme-fraiche/approved", headers=admin)
        assert response.status_code == 200
        assert response.json()["approved"] is True

    async def test_an_approved_entry_leaves_the_queue(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        await client.post(f"{REGISTRY}/creme-fraiche/approved", headers=admin)
        body = (await client.get(REGISTRY, params={"approved": False}, headers=admin)).json()
        assert body["entries"] == []
        assert body["total"] == 0

    async def test_approving_says_nothing_about_allergens(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """The safety rule. "This entry is fine" is not "I have looked inside it", and
        crème fraîche is milk (ADR-006)."""
        approved = (await client.post(f"{REGISTRY}/creme-fraiche/approved", headers=admin)).json()
        assert approved["classified"] is False
        assert approved["allergens"] == []

    async def test_approving_a_classified_entry_keeps_its_allergens(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """Regression. `approve` built its answer from the row alone, so an entry that
        had been classified came back with `classified: true` and an empty allergen list
        — which does not read as unknown, it reads as *examined and clear*. A false clean
        bill is worse than the silence ADR-006 is about, and the earlier test missed it
        because its fixture was unclassified either way.
        """
        await client.put(f"{ONE}/allergens", json={"allergens": ["milk"]}, headers=admin)
        approved = (await client.post(f"{ONE}/approved", headers=admin)).json()
        assert approved["allergens"] == ["milk"]
        assert approved["classified"] is True

    async def test_approving_twice_is_the_same_as_once(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        await client.post(f"{REGISTRY}/creme-fraiche/approved", headers=admin)
        again = await client.post(f"{REGISTRY}/creme-fraiche/approved", headers=admin)
        assert again.status_code == 200
        assert again.json()["approved"] is True

    async def test_an_ordinary_cook_may_not_approve(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """Reading the registry is reference material; signing an entry off is not."""
        response = await client.post(f"{REGISTRY}/creme-fraiche/approved", headers=cook)
        assert response.status_code == 403

    async def test_approving_something_that_is_not_there_is_a_404(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.post(f"{REGISTRY}/no-such-thing/approved", headers=admin)
        assert response.status_code == 404


class TestReadingOneEntry:
    async def test_an_entry_can_be_opened(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        response = await client.get(f"{REGISTRY}/unsalted-butter", headers=cook)
        assert response.status_code == 200
        assert response.json()["entry"]["slug"] == "unsalted-butter"

    async def test_it_says_what_the_thing_is_called_everywhere(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """The gap in the list view, and most of what an imported entry needs."""
        body = (await client.get(f"{REGISTRY}/unsalted-butter", headers=cook)).json()
        assert body["names"] == {
            "en-GB": ["unsalted butter"],
            "de-CH": ["ungesalzene Butter"],
        }

    async def test_an_entry_that_is_not_there_is_a_404(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        assert (await client.get(f"{REGISTRY}/no-such-thing", headers=cook)).status_code == 404


class TestCorrecting:
    async def test_an_admin_can_fix_the_kind(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.put(ONE, json={"kind": "liquid"}, headers=admin)
        assert response.status_code == 200
        assert response.json()["kind"] == "liquid"

    async def test_an_admin_can_supply_a_density(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.put(ONE, json={"density": "0.978"}, headers=admin)
        assert response.json()["density"] == "0.9780"

    async def test_a_density_can_be_taken_away(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """`null` is a correction, not an omission: a wrong density is worse than none."""
        await client.put(ONE, json={"density": "0.978"}, headers=admin)
        response = await client.put(ONE, json={"density": None}, headers=admin)
        assert response.json()["density"] is None

    async def test_a_field_not_mentioned_is_left_alone(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """The whole reason `density` needs a sentinel rather than a `None` default."""
        await client.put(ONE, json={"density": "0.978"}, headers=admin)
        response = await client.put(ONE, json={"kind": "liquid"}, headers=admin)
        assert response.json()["density"] == "0.9780"

    async def test_correcting_says_nothing_about_allergens(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        body = (await client.put(ONE, json={"density": "0.978"}, headers=admin)).json()
        assert body["classified"] is False

    async def test_correcting_does_not_approve_it(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        body = (await client.put(ONE, json={"kind": "liquid"}, headers=admin)).json()
        assert body["approved"] is False

    async def test_an_ordinary_cook_may_not_correct(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """The registry is shared: a correction here changes everybody's verdicts."""
        response = await client.put(ONE, json={"kind": "liquid"}, headers=cook)
        assert response.status_code == 403

    async def test_correcting_something_absent_is_a_404(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.put(
            f"{REGISTRY}/no-such-thing", json={"kind": "liquid"}, headers=admin
        )
        assert response.status_code == 404


class TestClassifying:
    async def test_an_admin_can_record_what_is_in_it(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.put(f"{ONE}/allergens", json={"allergens": ["milk"]}, headers=admin)
        assert response.status_code == 200
        assert response.json()["allergens"] == ["milk"]
        assert response.json()["classified"] is True

    async def test_recording_none_is_a_real_answer(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """ "I looked, there is nothing" — which is what makes it different from silence."""
        response = await client.put(f"{ONE}/allergens", json={"allergens": []}, headers=admin)
        assert response.json()["allergens"] == []
        assert response.json()["classified"] is True

    async def test_classifying_is_a_separate_act_from_correcting(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """Its own endpoint so a correction that omits allergens cannot unclassify one.

        A single PUT of the whole entry would turn "forgot to include the allergens" into
        "this ingredient is now unexamined", which is a known-milk entry silently becoming
        unknown (ADR-006).
        """
        await client.put(f"{ONE}/allergens", json={"allergens": ["milk"]}, headers=admin)
        corrected = (await client.put(ONE, json={"kind": "liquid"}, headers=admin)).json()
        assert corrected["allergens"] == ["milk"]
        assert corrected["classified"] is True

    async def test_an_ordinary_cook_may_not_classify(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        response = await client.put(f"{ONE}/allergens", json={"allergens": ["milk"]}, headers=cook)
        assert response.status_code == 403


class TestNaming:
    async def test_an_admin_can_teach_it_another_language(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.post(
            f"{ONE}/names", json={"locale": "de-CH", "spellings": ["Crème fraîche"]}, headers=admin
        )
        assert response.status_code == 200
        assert response.json()["names"]["de-CH"] == ["Crème fraîche"]

    async def test_the_original_name_survives(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        body = (
            await client.post(
                f"{ONE}/names",
                json={"locale": "de-CH", "spellings": ["Crème fraîche"]},
                headers=admin,
            )
        ).json()
        assert body["names"]["en-GB"] == ["crème fraîche"]

    async def test_a_name_already_known_is_not_duplicated(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        payload = {"locale": "de-CH", "spellings": ["Crème fraîche"]}
        await client.post(f"{ONE}/names", json=payload, headers=admin)
        body = (await client.post(f"{ONE}/names", json=payload, headers=admin)).json()
        assert body["names"]["de-CH"] == ["Crème fraîche"]

    async def test_an_ordinary_cook_may_not_rename(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        response = await client.post(
            f"{ONE}/names", json={"locale": "de-CH", "spellings": ["X"]}, headers=cook
        )
        assert response.status_code == 403

    async def test_a_name_another_entry_already_means_is_refused(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """Found by running it: on a seeded instance `Sauerrahm` in de-CH already means
        `sour-cream-35-fat`, so the insert hit the unique index, rolled back, and the
        endpoint answered 200 with nothing changed. An admin pressed the button and was
        told it worked.

        A name means one thing per language, so refusing is right — but it has to *say*
        so, and say which entry holds it. That is also the most useful thing this screen
        can report: two entries wanting the same name in the same language are very often
        one ingredient that an import split in two.
        """
        await registry.register(
            slug="sour-cream",
            kind=IngredientKind.SOLID,
            density=None,
            names={"de-CH": ["Sauerrahm"]},
            origin=Origin.SEED,
        )
        response = await client.post(
            f"{ONE}/names", json={"locale": "de-CH", "spellings": ["Sauerrahm"]}, headers=admin
        )
        assert response.status_code == 409
        assert "sour-cream" in response.json()["detail"]

    async def test_a_refused_name_changes_nothing(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        await registry.register(
            slug="sour-cream",
            kind=IngredientKind.SOLID,
            density=None,
            names={"de-CH": ["Sauerrahm"]},
            origin=Origin.SEED,
        )
        await client.post(
            f"{ONE}/names",
            json={"locale": "de-CH", "spellings": ["Rahmquark", "Sauerrahm"]},
            headers=admin,
        )
        body = (await client.get(ONE, headers=admin)).json()
        assert "de-CH" not in body["names"]

    async def test_a_name_this_entry_already_has_is_not_a_conflict(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """Re-adding its own spelling is a no-op, not somebody else's claim."""
        payload = {"locale": "de-CH", "spellings": ["Sauerrahm"]}
        assert (await client.post(f"{ONE}/names", json=payload, headers=admin)).status_code == 200
        assert (await client.post(f"{ONE}/names", json=payload, headers=admin)).status_code == 200


class TestRenaming:
    """Changing what a language calls an entry, as opposed to adding another spelling."""

    async def test_an_admin_can_rename_it(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.put(
            f"{ONE}/name", json={"locale": "en-GB", "name": "creme fraiche"}, headers=admin
        )
        assert response.status_code == 200
        assert response.json()["entry"]["name"] == "creme fraiche"

    async def test_the_old_name_stays_as_a_spelling(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        """An import that stopped resolving the old name would invent a duplicate."""
        body = (
            await client.put(
                f"{ONE}/name", json={"locale": "en-GB", "name": "creme fraiche"}, headers=admin
            )
        ).json()
        assert set(body["names"]["en-GB"]) == {"creme fraiche", "crème fraîche"}
        assert body["names"]["en-GB"][0] == "creme fraiche"

    async def test_a_name_another_entry_means_is_refused(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        await registry.register(
            slug="sour-cream",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["sour cream"]},
            origin=Origin.SEED,
        )
        response = await client.put(
            f"{ONE}/name", json={"locale": "en-GB", "name": "sour cream"}, headers=admin
        )
        assert response.status_code == 409
        assert "sour-cream" in response.json()["detail"]

    async def test_an_ordinary_cook_may_not_rename_it(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        response = await client.put(
            f"{ONE}/name", json={"locale": "en-GB", "name": "whatever"}, headers=cook
        )
        assert response.status_code == 403

    async def test_renaming_something_absent_is_a_404(
        self, client: AsyncClient, admin: dict[str, str], invented: None
    ) -> None:
        response = await client.put(
            f"{REGISTRY}/no-such-thing/name",
            json={"locale": "en-GB", "name": "whatever"},
            headers=admin,
        )
        assert response.status_code == 404


class TestMerging:
    """Folding one entry into another (Phase 7's reason for existing)."""

    @pytest.fixture
    async def both(self) -> None:
        """What a French page leaves beside the entry the instance already ships.

        Only the invented one is registered here: claiming an instance seeds the registry,
        so `plain-flour` is already there and registering it again would collide. That is
        also the true shape of the problem — the duplicate arrives next to a seeded row.
        """
        await registry.register(
            slug="farine-t55",
            kind=IngredientKind.SOLID,
            density=None,
            names={"fr-CH": ["farine T55"]},
            origin=Origin.USER,
        )

    async def test_an_admin_can_merge_one_into_another(
        self, client: AsyncClient, admin: dict[str, str], both: None
    ) -> None:
        response = await client.post(
            f"{REGISTRY}/farine-t55/merge", json={"into": "plain-flour"}, headers=admin
        )
        assert response.status_code == 200
        assert response.json()["entry"]["slug"] == "plain-flour"

    async def test_the_survivor_answers_to_both_names(
        self, client: AsyncClient, admin: dict[str, str], both: None
    ) -> None:
        body = (
            await client.post(
                f"{REGISTRY}/farine-t55/merge", json={"into": "plain-flour"}, headers=admin
            )
        ).json()
        # The seeded entry already answers to several French spellings; the merge adds
        # to them rather than replacing them, and its own name stays canonical.
        assert "farine T55" in body["names"]["fr-CH"]
        assert body["names"]["fr-CH"][0] != "farine T55"
        assert "plain flour" in body["names"][ENGLISH]

    async def test_the_merged_entry_is_gone(
        self, client: AsyncClient, admin: dict[str, str], both: None
    ) -> None:
        await client.post(
            f"{REGISTRY}/farine-t55/merge", json={"into": "plain-flour"}, headers=admin
        )
        assert (await client.get(f"{REGISTRY}/farine-t55", headers=admin)).status_code == 404

    async def test_merging_into_itself_is_refused(
        self, client: AsyncClient, admin: dict[str, str], both: None
    ) -> None:
        response = await client.post(
            f"{REGISTRY}/farine-t55/merge", json={"into": "farine-t55"}, headers=admin
        )
        assert response.status_code == 400

    async def test_merging_into_something_absent_is_a_404(
        self, client: AsyncClient, admin: dict[str, str], both: None
    ) -> None:
        response = await client.post(
            f"{REGISTRY}/plain-flour/merge", json={"into": "no-such-thing"}, headers=admin
        )
        assert response.status_code == 404

    async def test_an_ordinary_cook_may_not_merge(
        self, client: AsyncClient, cook: dict[str, str], both: None
    ) -> None:
        """It repoints every eater's dietary constraints. Not a cook's button."""
        response = await client.post(
            f"{REGISTRY}/farine-t55/merge", json={"into": "plain-flour"}, headers=cook
        )
        assert response.status_code == 403


class TestSuggestingMerges:
    """The matcher, through the API. Suggestions — nothing here merges anything."""

    @pytest.fixture
    async def split(self) -> None:
        """One ingredient written two ways, which is what an import leaves behind.

        Both halves registered here: signing up does not seed the registry, so the entry
        the duplicate duplicates has to exist for there to be a pair at all.
        """
        await registry.register(
            slug="brown-sugar",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["brown sugar"]},
            origin=Origin.SEED,
        )
        await registry.register(
            slug="sugar-brown",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["sugar, brown"]},
            origin=Origin.USER,
        )

    async def test_the_registry_can_be_swept_for_duplicates(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        response = await client.get(f"{REGISTRY}/duplicates", headers=cook)
        assert response.status_code == 200
        pairs = {tuple(sorted((one["slug"], one["other"]))) for one in response.json()}
        assert ("brown-sugar", "sugar-brown") in pairs

    async def test_the_sweep_route_is_not_swallowed_by_the_entry_route(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        """`/registry/duplicates` and `/registry/{slug}` share a shape and the first match
        wins, so the order they are declared in is the whole behaviour."""
        response = await client.get(f"{REGISTRY}/duplicates", headers=cook)
        assert isinstance(response.json(), list)

    async def test_every_suggestion_says_why_it_is_there(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        """A list that only reordered itself would be asking to be trusted (ADR-046)."""
        pairs = (await client.get(f"{REGISTRY}/duplicates", headers=cook)).json()
        assert all(one["reason"] for one in pairs)
        assert all(Decimal(one["confidence"]) > 0 for one in pairs)

    async def test_one_entry_can_be_asked_what_it_resembles(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        response = await client.get(f"{REGISTRY}/sugar-brown/resembling", headers=cook)
        assert response.status_code == 200
        assert "brown-sugar" in [one["slug"] for one in response.json()]

    async def test_an_entry_never_resembles_itself(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        found = (await client.get(f"{REGISTRY}/sugar-brown/resembling", headers=cook)).json()
        assert "sugar-brown" not in [one["slug"] for one in found]

    async def test_an_entry_nothing_resembles_reports_nothing(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        await registry.register(
            slug="xylophone-fruit",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["xylophone fruit"]},
            origin=Origin.USER,
        )
        found = (await client.get(f"{REGISTRY}/xylophone-fruit/resembling", headers=cook)).json()
        assert found == []

    async def test_an_entry_that_is_not_there_resembles_nothing(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        response = await client.get(f"{REGISTRY}/no-such-thing/resembling", headers=cook)
        assert response.status_code == 200
        assert response.json() == []

    async def test_suggesting_does_not_merge_anything(
        self, client: AsyncClient, cook: dict[str, str], split: None
    ) -> None:
        """The whole design: the matcher ranks, a person decides (ADR-053)."""
        await client.get(f"{REGISTRY}/duplicates", headers=cook)
        assert (await client.get(f"{REGISTRY}/sugar-brown", headers=cook)).status_code == 200


class TestWhatMergingWouldRecover:
    """What an unmerged duplicate actually costs, said on the page.

    An entry an import invented carries no figures — deliberately, because nothing is
    known about it (ADR-029). The entry it duplicates usually carries a full published
    profile. Saying so turns "these names look alike" into a reason to act: merging is
    what brings the figures across (ADR-052), and copying them instead would leave two
    entries claiming to be one food, which is the split merging exists to undo.
    """

    @pytest.fixture
    async def split(self) -> None:
        """A seeded entry with figures, and the one an import invented beside it.

        The figure is recorded here rather than relied on from start-up: these tests drive
        the app through `ASGITransport`, which does not run the lifespan, so what a booted
        instance would have attached is not here. The flag is what is under test, not the
        seeding.
        """
        held = await registry.resolve("brown sugar", ENGLISH)
        assert held is not None
        await registry.record_profile(
            NutrientProfile(
                ingredient_id=held.id,
                source=NutritionSource.SWISS,
                reference="471 Sugar, brown",
                amounts={Nutrient.ENERGY_KCAL: Decimal("390")},
            )
        )
        await registry.register(
            slug="sugar-brown",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["sugar, brown"]},
            origin=Origin.USER,
        )

    async def test_a_suggestion_says_it_carries_figures_this_entry_lacks(
        self, client: AsyncClient, admin: dict[str, str], split: None
    ) -> None:
        found = (await client.get(f"{REGISTRY}/sugar-brown/resembling", headers=admin)).json()
        brown = next(one for one in found if one["slug"] == "brown-sugar")
        assert brown["carries_nutrition"] is True

    async def test_an_entry_knows_whether_it_has_any_of_its_own(
        self, client: AsyncClient, admin: dict[str, str], split: None
    ) -> None:
        invented = (await client.get(f"{REGISTRY}/sugar-brown", headers=admin)).json()
        seeded = (await client.get(f"{REGISTRY}/brown-sugar", headers=admin)).json()
        assert invented["has_nutrition"] is False
        assert seeded["has_nutrition"] is True

    async def test_merging_actually_recovers_them(
        self, client: AsyncClient, admin: dict[str, str], split: None
    ) -> None:
        """The claim the page makes, checked rather than asserted at the reader."""
        assert (await client.get(f"{REGISTRY}/sugar-brown", headers=admin)).json()[
            "has_nutrition"
        ] is False

        await client.post(
            f"{REGISTRY}/sugar-brown/merge", json={"into": "brown-sugar"}, headers=admin
        )
        survivor = (await client.get(f"{REGISTRY}/brown-sugar", headers=admin)).json()
        assert survivor["has_nutrition"] is True


class TestWhereAFoodSits:
    """The category tree, which the published table always carried and Quookly threw away.

    It is what three separate findings were waiting on: a shopping list grouped by aisle,
    a registry of nine hundred entries with sections in it, and an Academy that can be
    read as *Ingredients > Vegetables > Carrot* rather than as one flat alphabet.

    `IngredientKind` could not stand in for it. That is `liquid / powder / solid /
    countable` and exists to choose a unit; grouping a shopping list by it gives
    "Solid: apples, cheese, bread".
    """

    @pytest.fixture
    async def tree(self) -> None:
        await registry.add_category(
            slug="vegetables",
            names={ENGLISH: "Vegetables", GERMAN: "Gemüse"},
        )
        await registry.add_category(
            slug="vegetables-fresh-vegetables",
            names={ENGLISH: "Fresh vegetables", GERMAN: "Gemüse frisch"},
            parent_slug="vegetables",
        )
        await registry.register(
            slug="carrot",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["carrot"], GERMAN: ["Rüebli"]},
            origin=Origin.SEED,
            category_slug="vegetables-fresh-vegetables",
        )

    async def test_the_tree_can_be_read(
        self, client: AsyncClient, cook: dict[str, str], tree: None
    ) -> None:
        answered = await client.get("/api/v1/registry/categories", headers=cook)

        assert answered.status_code == 200, answered.text
        assert answered.json() == [
            {"slug": "vegetables", "name": "Vegetables", "parent_slug": None},
            {
                "slug": "vegetables-fresh-vegetables",
                "name": "Fresh vegetables",
                "parent_slug": "vegetables",
            },
        ]

    async def test_the_tree_is_named_in_the_cooks_language(
        self, client: AsyncClient, cook: dict[str, str], tree: None
    ) -> None:
        """Free, and the reason the tree is worth taking from the published table at all:
        the three editions carry the same categories against identical row ids, so nobody
        translates anything (FR-10)."""
        await client.put("/api/v1/setup/locale", json={"locale": GERMAN}, headers=cook)

        answered = await client.get("/api/v1/registry/categories", headers=cook)

        assert [one["name"] for one in answered.json()] == ["Gemüse", "Gemüse frisch"]

    async def test_an_entry_says_where_it_sits(
        self, client: AsyncClient, cook: dict[str, str], tree: None
    ) -> None:
        listed = await client.get(REGISTRY, headers=cook)
        assert by_slug(listed.json())["carrot"]["category_slug"] == "vegetables-fresh-vegetables"

    async def test_an_entry_nobody_placed_says_so(
        self, client: AsyncClient, cook: dict[str, str], stocked: None
    ) -> None:
        """Every entry a cook adds, and every entry that predates the tree. Absent rather
        than a bucket called "other", which would be a claim about the food."""
        listed = await client.get(REGISTRY, headers=cook)
        assert by_slug(listed.json())["water"]["category_slug"] is None

    async def test_the_registry_can_be_narrowed_to_one_category(
        self, client: AsyncClient, cook: dict[str, str], tree: None, stocked: None
    ) -> None:
        """Which is what makes nine hundred entries navigable rather than merely lettered."""
        listed = await client.get(
            REGISTRY, params={"category": "vegetables-fresh-vegetables"}, headers=cook
        )
        assert [one["slug"] for one in listed.json()["entries"]] == ["carrot"]
        assert listed.json()["total"] == 1

    async def test_a_section_takes_the_groups_under_it(
        self, client: AsyncClient, cook: dict[str, str], tree: None, stocked: None
    ) -> None:
        """Asking for "Vegetables" means the vegetables, not the empty set. A cook filtering
        by a section is asking about the food in it, and no food sits on a section."""
        listed = await client.get(REGISTRY, params={"category": "vegetables"}, headers=cook)
        assert [one["slug"] for one in listed.json()["entries"]] == ["carrot"]

    async def test_signing_in_is_required_to_read_the_tree(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/registry/categories")).status_code == 401

    async def test_an_admin_can_say_where_a_food_sits(
        self, client: AsyncClient, admin: dict[str, str], tree: None
    ) -> None:
        """The half the seed cannot do. An import invents an entry for a line that resolved
        to nothing, and nothing places it — so the person who merges or corrects that entry
        is the only one who can (ADR-067)."""
        await registry.register(
            slug="samphire",
            kind=IngredientKind.SOLID,
            density=None,
            names={ENGLISH: ["samphire"]},
            origin=Origin.USER,
        )

        amended = await client.put(
            f"{REGISTRY}/samphire",
            json={"category": "vegetables-fresh-vegetables"},
            headers=admin,
        )

        assert amended.status_code == 200, amended.text
        assert amended.json()["category_slug"] == "vegetables-fresh-vegetables"

    async def test_a_correction_that_says_nothing_about_it_leaves_it_alone(
        self, client: AsyncClient, admin: dict[str, str], tree: None
    ) -> None:
        """The same rule the density has, and the reason it needs one: fixing the kind of a
        placed food must not unplace it."""
        amended = await client.put(f"{REGISTRY}/carrot", json={"kind": "liquid"}, headers=admin)

        assert amended.status_code == 200, amended.text
        assert amended.json()["category_slug"] == "vegetables-fresh-vegetables"

    async def test_saying_it_sits_nowhere_takes_it_out_of_the_tree(
        self, client: AsyncClient, admin: dict[str, str], tree: None
    ) -> None:
        """Explicit `null` clears it, exactly as it clears a density. A food filed in the
        wrong aisle is worse than one filed in none."""
        amended = await client.put(f"{REGISTRY}/carrot", json={"category": None}, headers=admin)

        assert amended.status_code == 200, amended.text
        assert amended.json()["category_slug"] is None

    async def test_a_category_nobody_defined_leaves_it_where_it_was(
        self, client: AsyncClient, admin: dict[str, str], tree: None
    ) -> None:
        """Rather than a 422 or a silent unplacing. The same rule registering follows: an
        unknown category is not a reason to lose what is already known."""
        amended = await client.put(
            f"{REGISTRY}/carrot", json={"category": "sea-vegetables"}, headers=admin
        )

        assert amended.status_code == 200, amended.text
        assert amended.json()["category_slug"] == "vegetables-fresh-vegetables"

    async def test_only_an_admin_may_move_a_food(
        self, client: AsyncClient, cook: dict[str, str], tree: None
    ) -> None:
        """The registry is shared: where flour sits changes every cook's shopping list."""
        refused = await client.put(
            f"{REGISTRY}/carrot", json={"category": "vegetables"}, headers=cook
        )
        assert refused.status_code == 403
