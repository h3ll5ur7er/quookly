"""The registry of generic foods, derived from the Swiss database (FR-9, ADR-006).

Roughly nine hundred entries, built by `seed/generic.py` and shipped as data. What these
tests hold is the part that cannot be seen by reading the file: that installing it does
not disturb the hand-written starter set, that an entry the source could not answer for
stays *unclassified* rather than becoming safe, and that a German or French recipe reaches
the same entry an English one does.
"""

from collections.abc import AsyncIterator

import pytest
from pytest import MonkeyPatch
from sqlmodel import SQLModel

from quookly.access import ingredient as registry
from quookly.access.database import dispose_engine, get_engine
from quookly.contracts.ingredient import Allergen, Origin
from quookly.contracts.nutrition import NutritionSource
from quookly.engines import interpretation
from quookly.managers import seed
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
async def stocked() -> int:
    """The instance as it stands after a start-up: starter set, then generic foods."""
    await seed.stock_registry()
    return await seed.stock_generic_foods()


class TestTheShippedFile:
    def test_it_ships_a_registry_worth_having(self) -> None:
        assert len(seed.read_generic_foods()) > 500

    def test_all_but_a_handful_are_named_in_all_three_languages(self) -> None:
        """The reason three editions of the workbook are in `reference/`. A German recipe
        that resolves nothing creates a new entry nobody has classified, and a dish made of
        flour, milk and eggs loses its allergens entirely (FR-10).

        Not *all*: a spelling belongs to one ingredient per language, and a few rows want a
        name something better already owns — the starter's `cornflour` holds "Maisstärke",
        so the table's maize starch goes unnamed in German and a German cook reaches the
        hand-written entry instead. That is the rule working, not a gap.
        """
        entries = seed.read_generic_foods()
        for entry in entries:
            assert "en-GB" in entry["names"], entry["slug"]
        for locale in ("de-CH", "fr-CH"):
            named = sum(1 for entry in entries if locale in entry["names"])
            assert named > len(entries) * 0.99, locale

    def test_no_entry_claims_a_name_twice(self) -> None:
        """A spelling means one ingredient per language — the registry enforces it with a
        unique index, and the loser would vanish without a word. Settled at build time so
        the file says what will happen."""
        seen: set[tuple[str, str]] = set()
        for entry in seed.read_generic_foods():
            for locale, spellings in entry["names"].items():
                for spelling in spellings:
                    assert (locale, spelling) not in seen, spelling
                    seen.add((locale, spelling))

    def test_it_never_says_a_food_is_free_of_something_nobody_checked(self) -> None:
        """`allergens: null` is the honest answer for most of this table, and it must stay
        null rather than becoming an empty list on the way through a file format."""
        unclassified = [e for e in seed.read_generic_foods() if e["allergens"] is None]
        assert unclassified, "everything claiming to be classified is itself suspicious"


class TestStocking:
    async def test_it_stocks_the_registry(self, stocked: int) -> None:
        assert stocked > 500

    async def test_running_it_again_adds_nothing(self, stocked: int) -> None:
        assert await seed.stock_generic_foods() == 0

    async def test_the_hand_written_starter_entry_wins(self, stocked: int) -> None:
        """`plain-flour` is a judgement — the table has four wheat flours by ash content —
        and it carries a density this table does not publish. The derived set is built
        around it, and this is the guard that says so."""
        flour = await registry.resolve("plain flour", ENGLISH)
        assert flour is not None
        assert flour.slug == "plain-flour"
        assert flour.density is not None

    async def test_an_everyday_food_the_starter_never_had(self, stocked: int) -> None:
        for name in ("carrot", "tomato", "spinach"):
            assert await registry.resolve(name, ENGLISH) is not None, name

    async def test_it_is_reachable_in_german_and_french(self, stocked: int) -> None:
        english = await registry.resolve("carrot", ENGLISH)
        german = await registry.resolve("karotte", "de-CH")
        french = await registry.resolve("carotte", "fr-CH")
        assert english is not None
        assert german is not None and german.id == english.id
        assert french is not None and french.id == english.id

    async def test_what_it_could_answer_completely_is_classified(self, stocked: int) -> None:
        carrot = await registry.resolve("carrot", ENGLISH)
        assert carrot is not None
        assert carrot.classified
        assert carrot.allergens == frozenset()

    async def test_what_it_could_not_stays_unclassified(self, stocked: int) -> None:
        """A sausage is not a cut of meat, and what else went into one is not knowable from
        its category. Unclassified reads as "nobody has looked", never as "safe"."""
        sausage = await registry.resolve("bierwurst", ENGLISH)
        assert sausage is not None
        assert not sausage.classified

    async def test_a_named_allergen_is_recorded_even_where_the_answer_is_partial(
        self, stocked: int
    ) -> None:
        """Adding an allergen only makes a verdict more cautious, so a keyword is enough."""
        nuts = await registry.resolve("hazelnut", ENGLISH)
        assert nuts is not None
        held = await registry.allergens_for([nuts.id])
        assert Allergen.TREE_NUTS in held[nuts.id][0]

    async def test_a_dairy_food_carries_milk_even_where_its_name_never_says_so(
        self, stocked: int
    ) -> None:
        """Sbrinz, Gorgonzola, Tête de Moine, Mozzarella. None of them contains a word a
        name table could match, and a registry that judged on names alone would hand every
        one of them to somebody avoiding dairy. Twenty entries here are in that position;
        the category is what answers for them."""
        cheese = await registry.resolve("sbrinz", ENGLISH)
        assert cheese is not None
        held = await registry.allergens_for([cheese.id])
        assert Allergen.MILK in held[cheese.id][0]

    async def test_they_are_seed_entries_not_a_cooks_own(self, stocked: int) -> None:
        carrot = await registry.resolve("carrot", ENGLISH)
        assert carrot is not None
        assert carrot.origin is Origin.SEED


class TestTheirNutrition:
    async def test_the_published_figures_come_with_them(self, stocked: int) -> None:
        await seed.stock_nutrition()
        carrot = await registry.resolve("carrot", ENGLISH)
        assert carrot is not None
        held = await registry.profiles_for([carrot.id])
        assert [one for one in held if one.source is NutritionSource.SWISS]
        assert any(one.amounts for one in held)

    async def test_a_figure_can_be_traced_to_a_published_row(self, stocked: int) -> None:
        """A number on a cook's screen should lead back to a row in a document somebody can
        open (FR-20, ADR-045)."""
        await seed.stock_nutrition()
        carrot = await registry.resolve("carrot", ENGLISH)
        assert carrot is not None
        held = await registry.profiles_for([carrot.id])
        assert held
        assert held[0].reference[0].isdigit()

    async def test_restating_them_does_not_multiply_them(self, stocked: int) -> None:
        """Seeding restates every shipped figure on every start-up, deliberately."""
        first = await seed.stock_nutrition()
        again = await seed.stock_nutrition()
        assert first == again


class TestWhatACookCanActuallyType:
    """The point of the whole import, stated as a number.

    Before this registry a British cook typing "carrot" got nothing, and an import invented
    an entry nobody had classified. These are ordinary words from ordinary recipes; if a
    change to the naming rules quietly stops resolving them, this is what says so.
    """

    EVERYDAY = [
        "apple",
        "apricot",
        "asparagus",
        "aubergine",
        "avocado",
        "bacon",
        "banana",
        "beef",
        "beetroot",
        "broccoli",
        "butter",
        "carrot",
        "cauliflower",
        "celery",
        "cherry",
        "chicken",
        "chickpeas",
        "cod",
        "courgette",
        "couscous",
        "cream",
        "cucumber",
        "egg",
        "fennel",
        "feta",
        "fig",
        "flour",
        "garlic",
        "ginger",
        "grape",
        "ham",
        "honey",
        "kale",
        "leek",
        "lemon",
        "lentils",
        "mango",
        "milk",
        "mozzarella",
        "mushroom",
        "mustard",
        "olive",
        "onion",
        "orange",
        "paprika",
        "parsley",
        "parsnip",
        "pasta",
        "peach",
        "pear",
        "peas",
        "pineapple",
        "pork",
        "potato",
        "prawns",
        "pumpkin",
        "quinoa",
        "radish",
        "raspberry",
        "rice",
        "rocket",
        "rosemary",
        "salmon",
        "salt",
        "spinach",
        "strawberry",
        "sweetcorn",
        "tofu",
        "tomato",
        "trout",
        "tuna",
        "turkey",
        "vinegar",
        "walnut",
        "watermelon",
        "yoghurt",
    ]

    async def test_the_everyday_words_resolve(self, stocked: int) -> None:
        missing = []
        for word in self.EVERYDAY:
            for candidate in interpretation.candidate_names(word):
                if await registry.resolve(candidate, ENGLISH) is not None:
                    break
            else:
                missing.append(word)
        assert missing == [], f"a British kitchen cannot name: {missing}"

    async def test_the_swiss_and_american_spellings_were_taught_british_ones(
        self, stocked: int
    ) -> None:
        """The table says zucchini, eggplant and shrimp. Quookly's source locale is
        `en-GB`, so those are the words a cook here does *not* type."""
        for british, published in (
            ("courgette", "zucchini"),
            ("aubergine", "eggplant"),
            ("prawns", "shrimp"),
        ):
            ours = await registry.resolve(british, ENGLISH)
            theirs = await registry.resolve(published, ENGLISH)
            assert ours is not None, british
            assert theirs is not None and theirs.id == ours.id, british

    def test_an_ambiguous_word_is_left_ambiguous(self) -> None:
        """ "Yogurt" is not a food in this table — there are twenty-three of them, nearly all
        flavoured. Handing the bare word to whichever sorted first is how chocolate ends up
        in a tzatziki, so nothing claims it and the cook picks."""
        claimed = {
            spelling
            for entry in seed.read_generic_foods()
            for spelling in entry["names"].get(ENGLISH, [])
        }
        assert "yogurt" not in claimed
