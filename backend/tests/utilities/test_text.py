"""Folding the ways one ingredient name gets written.

Two different jobs, kept apart on purpose. `normalise` is what the registry *stores* and
matches on exactly; its result is a column with a unique index behind it. `fold` goes
further and throws away accents, which is useful for finding a name and dangerous for
storing one — `pêche` and `pèche` are different words that fold to the same string.
"""

from quookly.utilities.text import fold, normalise


class TestNormalising:
    def test_case_does_not_matter(self) -> None:
        assert normalise("Plain Flour") == "plain flour"

    def test_surrounding_space_does_not_matter(self) -> None:
        assert normalise("  plain flour  ") == "plain flour"

    def test_runs_of_space_collapse(self) -> None:
        assert normalise("plain   flour") == "plain flour"

    def test_accents_are_kept(self) -> None:
        """They are part of the stored name; folding them is a separate decision."""
        assert normalise("Crème Fraîche") == "crème fraîche"


class TestFolding:
    def test_accents_are_thrown_away(self) -> None:
        assert fold("crème fraîche") == "creme fraiche"

    def test_it_normalises_too(self) -> None:
        assert fold("  Crème  Fraîche ") == "creme fraiche"

    def test_a_name_without_accents_is_unchanged(self) -> None:
        assert fold("plain flour") == "plain flour"

    def test_german_umlauts_fold_to_the_bare_letter(self) -> None:
        """Not to `ue`. The registry's own German names spell it either way, and matching
        one form against the other is the matcher's job, not this function's."""
        assert fold("Müsli") == "musli"

    def test_the_two_spellings_of_one_word_meet(self) -> None:
        assert fold("crème fraîche") == fold("creme fraiche")

    def test_different_words_can_collide(self) -> None:
        """The reason folding is a fallback and never authority: French `pêche` is a peach
        and `pèche` is fishing, and they fold together. A caller that finds two entries
        this way has to refuse rather than pick one."""
        assert fold("pêche") == fold("pèche")
