"""The hand-written seed pages for the Academy's ingredient section (ADR-057, ADR-061).

The second section existed in the schema, in the access layer and in the write-page screen
from the day ADR-057 was taken — and shipped empty. An instance's Academy was fifty
techniques and no foods, which is not what "two sections" means.

These pages are about a **registry entry**, and that is the whole difficulty: a page that
names no entry cannot show that entry's facts, and a page that names the *wrong* entry
shows one food's allergens under another food's name. So the tests that matter here are
about `about` — that every page names an entry, and that the entry exists.
"""

import json
from pathlib import Path
from typing import Any

import pytest

SEED = Path(__file__).resolve().parents[2] / "seed" / "foods.json"
REGISTRY = Path(__file__).resolve().parents[2] / "seed" / "generic-foods.json"
STARTER = Path(__file__).resolve().parents[2] / "seed" / "starter.en-GB.json"
LOCALES = ("en-GB", "de-CH", "fr-CH")


@pytest.fixture(scope="module")
def foods() -> list[dict[str, Any]]:
    document = json.loads(SEED.read_text(encoding="utf-8"))
    assert document["quookly"] == 1
    assert document["section"] == "ingredient"
    return list(document["pages"])


@pytest.fixture(scope="module")
def registry_slugs() -> set[str]:
    """Every slug the registry seed installs, from both files that install one."""
    generic = json.loads(REGISTRY.read_text(encoding="utf-8"))
    slugs = {one["slug"] for one in generic["ingredients"]}
    if STARTER.exists():
        starter = json.loads(STARTER.read_text(encoding="utf-8"))
        slugs |= {one["slug"] for one in starter.get("ingredients", [])}
    return slugs


class TestTheCorpus:
    def test_it_is_worth_shipping(self, foods: list[dict[str, Any]]) -> None:
        assert len(foods) >= 10

    def test_every_slug_is_unique(self, foods: list[dict[str, Any]]) -> None:
        slugs = [page["slug"] for page in foods]
        assert len(slugs) == len(set(slugs))


class TestWhatEachPageIsAbout:
    """The field that separates this section from the other one."""

    def test_every_page_names_a_registry_entry(self, foods: list[dict[str, Any]]) -> None:
        for page in foods:
            assert page.get("about"), f"{page['slug']} is about no food"

    def test_every_named_entry_is_one_this_build_ships(
        self, foods: list[dict[str, Any]], registry_slugs: set[str]
    ) -> None:
        """A page about a food the registry does not have is a page about nothing. It
        would also fail to install, and a seed that fails at boot is the worst place to
        find a typo."""
        for page in foods:
            assert page["about"] in registry_slugs, f"{page['slug']} names {page['about']}"

    def test_no_two_pages_are_about_the_same_food(self, foods: list[dict[str, Any]]) -> None:
        about = [page["about"] for page in foods]
        assert len(about) == len(set(about))


class TestEveryLanguage:
    def test_each_page_is_written_in_all_three(self, foods: list[dict[str, Any]]) -> None:
        for page in foods:
            assert tuple(page["locales"]) == LOCALES, page["slug"]

    def test_nothing_is_left_blank(self, foods: list[dict[str, Any]]) -> None:
        for page in foods:
            for locale, written in page["locales"].items():
                assert written["name"].strip(), f"{page['slug']}/{locale}"
                assert written["summary"].strip(), f"{page['slug']}/{locale}"
                assert written["explanation"].strip(), f"{page['slug']}/{locale}"

    def test_a_summary_is_a_sentence_not_a_paragraph(self, foods: list[dict[str, Any]]) -> None:
        """It is what a list of pages shows. A paragraph there is a broken layout."""
        for page in foods:
            for locale, written in page["locales"].items():
                assert len(written["summary"]) <= 120, f"{page['slug']}/{locale}"
