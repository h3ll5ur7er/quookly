"""The hand-written seed pages for the Academy's technique section (Phase 7).

Written rather than derived: there is no openly available table of cooking techniques the
way there is one of foods, so `seed/techniques.json` is authored by hand and these tests
are what stands in for a builder's guarantees
([ADR-056](../../doc/07-decisions.md)).

The load-bearing field is `spellings`. It is what a recipe step's own words are matched
against ([ADR-055](../../doc/07-decisions.md)), which means a careless entry there does not
produce a bad definition — it produces a *wrong link on somebody else's recipe*. Most of
what follows is about that field.
"""

import json
import unicodedata
from pathlib import Path
from typing import Any

import pytest

SEED = Path(__file__).resolve().parents[2] / "seed" / "techniques.json"
LOCALES = ("en-GB", "de-CH", "fr-CH")


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", " ".join(text.lower().split()))
    return "".join(mark for mark in decomposed if not unicodedata.combining(mark))


@pytest.fixture(scope="module")
def techniques() -> list[dict[str, Any]]:
    document = json.loads(SEED.read_text(encoding="utf-8"))
    assert document["quookly"] == 1
    # Techniques are one section of the Academy, not the whole of it (ADR-057).
    assert document["section"] == "technique"
    return list(document["pages"])


class TestTheCorpus:
    def test_it_is_worth_shipping(self, techniques: list[dict[str, Any]]) -> None:
        """Enough that a cook meets one on an ordinary recipe rather than never."""
        assert len(techniques) >= 45

    def test_every_technique_speaks_all_three_shipped_languages(
        self, techniques: list[dict[str, Any]]
    ) -> None:
        """A German recipe's steps can only be matched against German spellings."""
        for technique in techniques:
            assert set(technique["locales"]) == set(LOCALES), technique["slug"]

    def test_every_slug_is_unique(self, techniques: list[dict[str, Any]]) -> None:
        slugs = [technique["slug"] for technique in techniques]
        assert len(slugs) == len(set(slugs))

    def test_a_slug_is_a_slug(self, techniques: list[dict[str, Any]]) -> None:
        for technique in techniques:
            assert technique["slug"].replace("-", "").isalnum(), technique["slug"]
            assert technique["slug"] == technique["slug"].lower()

    def test_every_entry_says_what_it_is_and_then_explains(
        self, techniques: list[dict[str, Any]]
    ) -> None:
        for technique in techniques:
            for locale in LOCALES:
                written = technique["locales"][locale]
                assert written["name"].strip(), (technique["slug"], locale)
                assert len(written["summary"]) > 20, (technique["slug"], locale)
                assert len(written["explanation"]) > 60, (technique["slug"], locale)

    def test_a_summary_is_one_sentence_not_a_paragraph(
        self, techniques: list[dict[str, Any]]
    ) -> None:
        """It is what sits under a term in a list; the explanation is behind the link."""
        for technique in techniques:
            for locale in LOCALES:
                assert len(technique["locales"][locale]["summary"]) <= 130, (
                    technique["slug"],
                    locale,
                )


class TestSpellings:
    """The field that decides which words in a step become links."""

    def test_every_locale_offers_more_than_the_bare_name(
        self, techniques: list[dict[str, Any]]
    ) -> None:
        """A step says "folded in", not "fold". Without inflections nothing matches."""
        for technique in techniques:
            for locale in LOCALES:
                assert technique["locales"][locale]["spellings"], (technique["slug"], locale)

    def test_no_spelling_repeats_its_own_name(self, techniques: list[dict[str, Any]]) -> None:
        for technique in techniques:
            for locale in LOCALES:
                written = technique["locales"][locale]
                assert fold(written["name"]) not in {
                    fold(spelling) for spelling in written["spellings"]
                }, (technique["slug"], locale)

    def test_no_term_is_claimed_twice_within_this_section(
        self, techniques: list[dict[str, Any]]
    ) -> None:
        """Not a rule about the Academy — a rule about this file.

        Several pages *may* claim a term, and one that is shared says so at the top and
        names the others (ADR-058). That is for collisions between sections, and between
        what cooks write: `butter` will reasonably be both a food and part of mounting a
        sauce.

        Inside one hand-written section it is still a mistake. Two technique pages
        answering to one word means one of them was written twice or named carelessly,
        and nobody chose that.
        """
        for locale in LOCALES:
            claimed: dict[str, str] = {}
            for technique in techniques:
                written = technique["locales"][locale]
                for spelling in [written["name"], *written["spellings"]]:
                    key = fold(spelling)
                    assert key not in claimed, (
                        locale,
                        spelling,
                        claimed.get(key),
                        technique["slug"],
                    )
                    claimed[key] = technique["slug"]

    def test_no_spelling_is_a_single_short_word_that_means_something_else(
        self, techniques: list[dict[str, Any]]
    ) -> None:
        """Bare words that appear in recipes meaning something entirely different.

        "Reduce the heat", "the rest of the flour", "brown sugar", "double cream", "a
        toast" — each would light up on nearly every recipe if the bare word were a
        spelling. The technique keeps them only as verb phrases.
        """
        forbidden = {
            "reduce",
            "rest",
            "brown",
            "cream",
            "toast",
            "score",
            "dice",
            "steam",
            "grill",
            "glaze",
            "zest",
            "fold",
            "whip",
            "mince",
            "strain",
        }
        for technique in techniques:
            for locale in LOCALES:
                for spelling in technique["locales"][locale]["spellings"]:
                    assert fold(spelling) not in forbidden, (technique["slug"], locale, spelling)


class TestCautions:
    """Where getting it wrong matters, and only there."""

    def test_the_dangerous_ones_carry_one(self, techniques: list[dict[str, Any]]) -> None:
        """Hot fat, molten sugar, raw-meat marinade, kidney beans, escaping steam. Each is
        a way somebody gets hurt or ill that a definition alone would not mention."""
        by_slug = {technique["slug"]: technique for technique in techniques}
        for slug in ("deep-fry", "caramelise", "marinate", "rehydrate", "steam", "bain-marie"):
            assert by_slug[slug]["locales"]["en-GB"]["caution"], slug

    def test_a_caution_is_written_in_every_language_or_none(
        self, techniques: list[dict[str, Any]]
    ) -> None:
        """A German cook must not be the one who does not get warned."""
        for technique in techniques:
            written = [bool(technique["locales"][locale]["caution"]) for locale in LOCALES]
            assert len(set(written)) == 1, technique["slug"]

    def test_most_techniques_carry_none(self, techniques: list[dict[str, Any]]) -> None:
        """Restraint is what keeps a warning worth reading — the same argument the dietary
        badges make. Twenty cautions would drown the one about the fat fire."""
        carrying = sum(1 for technique in techniques if technique["locales"]["en-GB"]["caution"])
        assert carrying <= len(techniques) // 3


class TestAgainstTheIngredientRegistry:
    """Terms that are also the name of a food this instance ships.

    Both corpora are matched against the same recipe text, so a term in both is a link
    pointing at the wrong kind of thing. `clarified butter` and the French `glacé` were
    both in the first draft: the first is something the registry sells rather than an act,
    and the second means *iced* as readily as *glazed* — the registry has ice cream under
    it.

    This is the check the design said a visible alias list would make possible: a wrong
    alias is a row somebody can delete, which a similarity threshold never is.
    """

    @pytest.fixture(scope="class")
    def ingredient_names(self) -> dict[str, dict[str, str]]:
        source = SEED.parent / "generic-foods.json"
        gathered: dict[str, dict[str, str]] = {}
        for entry in json.loads(source.read_text(encoding="utf-8"))["ingredients"]:
            for locale, names in entry["names"].items():
                for name in names:
                    gathered.setdefault(locale, {})[fold(name)] = entry["slug"]
        return gathered

    def test_no_technique_term_is_also_an_ingredient(
        self, techniques: list[dict[str, Any]], ingredient_names: dict[str, dict[str, str]]
    ) -> None:
        for technique in techniques:
            for locale in LOCALES:
                written = technique["locales"][locale]
                for spelling in [written["name"], *written["spellings"]]:
                    food = ingredient_names.get(locale, {}).get(fold(spelling))
                    assert food is None, (locale, spelling, technique["slug"], food)
