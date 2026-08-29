"""Folding the ways one ingredient name gets written.

Two different jobs, kept apart on purpose. `normalise` is what the registry *stores* and
matches on exactly; its result is a column with a unique index behind it. `fold` goes
further and throws away accents, which is useful for finding a name and dangerous for
storing one — `pêche` and `pèche` are different words that fold to the same string.
"""

from quookly.utilities.text import affinity, fold, normalise


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


class TestAffinity:
    """How directly a name answers what somebody typed (ADR-069)."""

    def test_the_word_itself_beats_a_name_that_merely_contains_it(self) -> None:
        assert affinity("salt", "salt") > affinity("salt", "fine salt")

    def test_a_name_that_starts_with_the_word_beats_one_that_buries_it(self) -> None:
        assert affinity("tomato", "tomato paste") > affinity("tomato", "canned peeled tomato")

    def test_a_whole_word_beats_the_middle_of_a_longer_one(self) -> None:
        """`salt` in `sea salt flakes` is the word; in `basalt` it is a coincidence. Both
        names are the same length, so nothing but the tier separates them."""
        assert affinity("salt", "sea salt flakes") > affinity("salt", "unsalted basalt")

    def test_between_two_equally_direct_names_the_shorter_one_wins(self) -> None:
        """Nothing separates them but length, and the shorter name is the plainer food:
        `tomato juice` before `drained in oil dried tomato`."""
        assert affinity("tomato", "tomato juice") > affinity("tomato", "tomato paste sun dried")

    def test_accents_do_not_change_how_direct_a_match_is(self) -> None:
        """Whichever side wrote the accent, and whether either did."""
        plain = affinity("creme fraiche", "creme fraiche")
        assert affinity("creme fraiche", "crème fraîche") == plain
        assert affinity("crème fraîche", "creme fraiche") == plain

    def test_length_cannot_promote_a_name_into_a_better_tier(self) -> None:
        """A short coincidence stays below a long real match: `basalt` is not salt, however
        much shorter it is than `coarse rock salt for grinding`."""
        assert affinity("salt", "basalt") < affinity("salt", "coarse rock salt for grinding")

    def test_a_name_that_does_not_match_at_all_scores_nothing(self) -> None:
        assert affinity("salt", "flour") == 0

    def test_a_word_that_merely_begins_with_the_letters_is_not_a_direct_match(self) -> None:
        """`saltimbocca` starts with `salt` and has nothing to do with salt. Starting with
        the *word* is what earns the tier; starting with the letters is a coincidence, and
        a coincidence must not outrank a name that contains the actual word."""
        assert affinity("salt", "saltimbocca") < affinity("salt", "sea salt flakes")

    def test_starting_with_the_word_still_wins_when_more_follows(self) -> None:
        assert affinity("tomato", "tomato paste") > affinity("tomato", "sun dried tomato")
