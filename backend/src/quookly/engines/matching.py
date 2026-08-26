"""Deciding which written names might mean the same ingredient (Phase 7).

A rule engine: pure, no I/O, reference data arrives as an argument, and its tests are a
table of cases. It is listed in the `Rule engines do not reach resource access` contract
for that reason.

**It ranks; it never decides.** Two callers use it and neither is allowed to act on its
answer alone. The registry screen shows an administrator possible duplicates and they
choose. An import attaches a suspicion to the entry it creates and still creates it — a
fuzzy match that resolved a recipe line would attach one food's allergens to another
food's recipe, and an unresolved ingredient already reads as *unknown*, which is the
conservative direction (ADR-006, ADR-029).

Exact resolution, including the accent-folding fallback, lives in `IngredientAccess`.
That is a different question — "is this the same word" — and it has a definite answer.
This module is for "is this the same thing", which does not.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from difflib import SequenceMatcher

from quookly.contracts.matching import (
    Duplicate,
    Mention,
    Named,
    Resemblance,
    Resembling,
)
from quookly.utilities.text import fold

#: Below this, a pair is noise. Tuned against the shipped registry of ~900 generic foods
#: rather than guessed: at 0.78 the report is mostly long descriptive names that share a
#: tail, and at 0.85 what survives is spelling variants, which is what this can actually
#: find.
CONFIDENCE = Decimal("0.85")

#: How alike two words must be to count as the same word. `brussel`/`brussels` and
#: `doug`/`dough` are both real in the shipped data; `peach`/`pear` and `oat`/`soya` are
#: comfortably below it.
_SAME_WORD = 0.85

#: Words that flip a name's meaning. A name carrying one that the other lacks is not a
#: spelling of it — it is its opposite, and character similarity cannot see the difference:
#: `sweetened` and `unsweetened` are 0.98 alike and are different foods.
_NEGATORS = frozenset({"not", "without", "free", "no", "ohne", "sans", "sugarfree"})

#: Words that carry nothing about which food this is. Deliberately short: `with` and
#: `without` are *not* here, because the first distinguishes a dish from an ingredient and
#: the second reverses a meaning.
_EMPTY_WORDS = frozenset({"at", "least", "and", "or", "the", "a", "of"})

#: A word appearing in more than this share of entries is useless for narrowing the search,
#: so it is not used to decide which pairs are worth comparing.
_TOO_COMMON = 0.05

#: How many leading characters block a comparison when every word is too common.
_PREFIX = 4


def _words(name: str) -> frozenset[str]:
    """The meaningful words of a name, folded.

    **Numbers are kept.** Dropping them was the first version and it was backwards: in the
    shipped registry the number *is* the distinction — `at least 15% fidm appenzeller` and
    `at least 45% fidm appenzeller` are different cheeses, and `11 vol% wine white` and
    `12.5 vol% wine white` are different wines. Stripping the digits made every one of them
    a duplicate of every other.
    """
    return frozenset(
        word
        for word in fold(name)
        .replace(",", " ")
        .replace("-", " ")
        .replace("(", " ")
        .replace(")", " ")
        .split()
        if len(word) > 1 and word not in _EMPTY_WORDS
    )


def _opposed(mine: frozenset[str], theirs: frozenset[str]) -> bool:
    """Whether one name negates something the other asserts.

    Two shapes, both real in the shipped registry: an explicit negator on one side only
    (`pineapple ... drained` against `pineapple ... not drained`), and an `un-` prefix on a
    word the other side has plain (`sweetened` against `unsweetened`). Both pairs score
    above 0.95 on any character-level measure, which is why this is a separate check and
    not a lower score.
    """
    if (mine ^ theirs) & _NEGATORS:
        return True
    return any(word.startswith("un") and word[2:] in theirs for word in mine - theirs) or any(
        word.startswith("un") and word[2:] in mine for word in theirs - mine
    )


def _same_word(one: str, other: str) -> bool:
    """Whether two words are the same word, allowing for a spelling."""
    return one == other or SequenceMatcher(None, one, other).ratio() >= _SAME_WORD


def _compare(written: str, candidate: str) -> tuple[Decimal, Resemblance] | None:
    """How alike two names are, and why. `None` when they are not alike at all.

    Compared **word by word**, not character by character over the whole string. The first
    version used `SequenceMatcher` on the whole name and it was dominated by shared tails:
    `peach with sweetener, canned, drained` and `pear with sweetener, canned, drained`
    scored 0.96 and are different fruits. Words that differ have to differ; a long agreeing
    description cannot outvote them.
    """
    folded, other = fold(written), fold(candidate)
    if not folded or not other:
        return None
    if folded == other:
        return Decimal("1"), Resemblance.SAME_SPELLING

    mine, theirs = _words(written), _words(candidate)
    if not mine or not theirs or _opposed(mine, theirs):
        return None

    unmatched = set(theirs)
    shared = 0
    spelled = False
    for word in mine:
        partner = next(
            (other_word for other_word in unmatched if _same_word(word, other_word)), None
        )
        if partner is None:
            continue
        shared += 1
        spelled = spelled or partner != word
        unmatched.discard(partner)

    union = len(mine) + len(theirs) - shared
    if union == 0:
        return None
    score = Decimal(shared) / Decimal(union)

    if shared == len(mine) or shared == len(theirs):
        reason = (
            Resemblance.SPELLING if spelled and len(mine) == len(theirs) else Resemblance.CONTAINS
        )
    else:
        reason = Resemblance.SPELLING if spelled else Resemblance.SAME_WORDS
    return score, reason


def resembling(
    written: str,
    entries: Sequence[Named],
    *,
    at_least: Decimal = CONFIDENCE,
    limit: int = 5,
) -> list[Resembling]:
    """Registry entries a written name might mean, best first.

    Every spelling of every entry is compared and the best one for each entry is kept: an
    entry answers to several names, and matching an alias is as good as matching the
    canonical one.
    """
    best: dict[str, Resembling] = {}
    for entry in entries:
        for name in entry.names:
            verdict = _compare(written, name)
            if verdict is None:
                continue
            confidence, reason = verdict
            if confidence < at_least:
                continue
            held = best.get(entry.slug)
            if held is None or confidence > held.confidence:
                best[entry.slug] = Resembling(
                    slug=entry.slug, name=name, confidence=confidence, reason=reason
                )

    return sorted(best.values(), key=lambda found: (-found.confidence, found.slug))[:limit]


def duplicates(
    entries: Sequence[Named],
    *,
    at_least: Decimal = CONFIDENCE,
    limit: int = 50,
) -> list[Duplicate]:
    """Pairs of entries that might be one ingredient, best first.

    Nine hundred entries is four hundred thousand pairs, and comparing them all with
    `SequenceMatcher` is slow enough that nobody would run it. So pairs are only compared
    when they share a word worth sharing: an inverted index over the meaningful words,
    with the words too common to narrow anything left out of it, and a leading-character
    bucket for entries whose every word is common.

    That is a filter on *what is compared*, not on what counts as a match. A pair sharing
    no word and no prefix is not reported — which is the trade this makes for being
    runnable, and it is stated here rather than discovered later.
    """
    by_slug = {entry.slug: entry for entry in entries}
    buckets = _buckets(entries)

    considered: set[tuple[str, str]] = set()
    for members in buckets.values():
        ordered = sorted(members)
        for index, slug in enumerate(ordered):
            for other in ordered[index + 1 :]:
                considered.add((slug, other))

    found: list[Duplicate] = []
    for slug, other in considered:
        best: tuple[Decimal, Resemblance, str, str] | None = None
        for name in by_slug[slug].names:
            for other_name in by_slug[other].names:
                verdict = _compare(name, other_name)
                if verdict is None:
                    continue
                confidence, reason = verdict
                if best is None or confidence > best[0]:
                    best = (confidence, reason, name, other_name)
        if best is None or best[0] < at_least:
            continue
        confidence, reason, name, other_name = best
        found.append(
            Duplicate(
                slug=slug,
                other=other,
                name=name,
                other_name=other_name,
                confidence=confidence,
                reason=reason,
            )
        )

    return sorted(found, key=lambda pair: (-pair.confidence, pair.slug, pair.other))[:limit]


def _buckets(entries: Sequence[Named]) -> dict[str, set[str]]:
    """Which entries are worth comparing with which.

    Keyed by a shared word, or by a leading-character prefix where every word an entry has
    is too common to narrow anything — which in the shipped registry means the entries
    named entirely out of `at least 45% fidm ...`.
    """
    occurrences: dict[str, int] = defaultdict(int)
    words: dict[str, frozenset[str]] = {}
    for entry in entries:
        held = (
            frozenset().union(*(_words(name) for name in entry.names))
            if entry.names
            else frozenset()
        )
        words[entry.slug] = held
        for word in held:
            occurrences[word] += 1

    ceiling = max(2, int(len(entries) * _TOO_COMMON))
    buckets: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        narrowing = [word for word in words[entry.slug] if occurrences[word] <= ceiling]
        if narrowing:
            for word in narrowing:
                buckets[f"word:{word}"].add(entry.slug)
            continue
        for name in entry.names:
            folded = fold(name)
            if folded:
                buckets[f"prefix:{folded[:_PREFIX]}"].add(entry.slug)
    return buckets


#: What separates one word from another when reading a step. Hyphens count: a step writes
#: `deep-fry` and a page lists `deep fry`, or the other way round, and they are the same
#: words either way.
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

#: What ends a thought. A term of several words may not reach across one of these, or
#: "cook until brown. Butter the tin" names `brown butter`, which nobody wrote.
_BREAK = re.compile(r"[.!?;:\n]")


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """The words of a text, folded, each with where it sits in the original.

    Tokenising the original rather than folding the whole string is what keeps the offsets
    honest: folding can change a string's length, so a position in the folded form is not
    a position in what the cook is reading.
    """
    return [(fold(found.group()), found.start(), found.end()) for found in _WORD.finditer(text)]


def _joinable(text: str, words: list[tuple[str, int, int]], start: int, end: int) -> bool:
    """Whether these consecutive words belong to one thought.

    A term of several words may not reach across a full stop. `brown butter` is a real
    technique and "cook until brown. Butter the tin" names two different things.
    """
    return not any(
        _BREAK.search(text[words[index][2] : words[index + 1][1]])
        for index in range(start, end - 1)
    )


def _prepared(entries: Sequence[Named]) -> list[tuple[tuple[str, ...], str]]:
    """The vocabulary as words, longest first.

    Longest first so a shorter term never claims words a longer one wants; sorted by slug
    within a length so the result is the same on every run.

    Separated from the matching because a recipe has many steps and one vocabulary.
    Rebuilding it per step tokenised two hundred terms a dozen times over to read one
    sentence, which measurement put at most of the cost of showing a recipe.
    """
    vocabulary: list[tuple[tuple[str, ...], str]] = []
    for held in entries:
        for spelling in held.names:
            spoken = tuple(word for word, _, _ in _tokens(spelling))
            if spoken:
                vocabulary.append((spoken, held.slug))
    vocabulary.sort(key=lambda one: (-len(one[0]), one[1], one[0]))
    return vocabulary


def _spot(text: str, vocabulary: list[tuple[tuple[str, ...], str]]) -> list[Mention]:
    words = _tokens(text)
    if not words:
        return []

    found: list[Mention] = []
    at = 0
    while at < len(words):
        for spoken, slug in vocabulary:
            end = at + len(spoken)
            if end > len(words):
                continue
            if tuple(word for word, _, _ in words[at:end]) == spoken and _joinable(
                text, words, at, end
            ):
                found.append(Mention(slug=slug, start=words[at][1], end=words[end - 1][2]))
                at = end
                break
        else:
            at += 1
    return found


def mentioned(text: str, entries: Sequence[Named]) -> list[Mention]:
    """The known terms one step names, in reading order.

    Whole words only, which comparing token by token gives for nothing: `scaffold` is not
    folding. **Longest first** — a step naming a `bain-marie` is not naming a `bain` — and
    matches never overlap, because two links over the same words is not something a reader
    can act on.

    The vocabulary arrives as an argument and no database is read, which is what keeps this
    a rule engine and its tests a table of steps and expected offsets.

    For a whole recipe use `mentioned_in`, which prepares the vocabulary once.
    """
    return _spot(text, _prepared(entries))


def mentioned_in(texts: Sequence[str], entries: Sequence[Named]) -> list[list[Mention]]:
    """The same, for every step of a recipe, preparing the vocabulary once."""
    vocabulary = _prepared(entries)
    return [_spot(text, vocabulary) for text in texts]
