"""Folding the ways one name gets written.

A utility rather than a private helper in the access layer, because two callers need it
and they sit on different layers: the registry stores normalised names, and the matching
engine compares written ones. Utilities depend on nothing else, which this does not.

Three functions, deliberately not one.

`normalise` is what the registry **stores** and matches exactly. Its result is a column
with a unique index on it, so what it does is part of the schema: changing it means
re-normalising every row and risking a collision the index would reject.

`fold` goes further and throws away accents. That is useful for *finding* a name — 28% of
the shipped registry's name rows carry diacritics, and pages routinely strip them — and
dangerous for *deciding* one, because different words fold together: French `pêche` is a
peach and `pèche` is fishing. Callers use it to look, never to conclude.

`affinity` scores how directly a name answers a typed word, so that a list somebody
chooses from can be *ordered* by it. Here rather than in a rule engine because the access
layer is what applies it, and access may not call an engine (ADR-008). It is mechanics
rather than judgement — how much of the name the word accounts for, and where it sits —
and it knows nothing about food.
"""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalise(name: str) -> str:
    """Fold the variations of a typed name that mean the same ingredient."""
    return _WHITESPACE.sub(" ", name.strip().lower())


def fold(name: str) -> str:
    """The same, with accents removed as well.

    Decomposes to NFD and drops the combining marks, so `crème` and `creme` meet. This is
    the same reach as the search index's `remove_diacritics 2`, which is deliberate: a
    cook typing on a phone keyboard should not have to find the accent first.
    """
    decomposed = unicodedata.normalize("NFD", normalise(name))
    return "".join(mark for mark in decomposed if not unicodedata.combining(mark))


#: What each kind of match is worth, before length is considered. The gaps are wide enough
#: that no amount of shortness promotes a name from one tier to the one above it: how the
#: word sits in the name decides the tier, and length only breaks ties inside it.
_EXACTLY = 400
_STARTS_WITH = 300
_WHOLE_WORD = 200
_ANYWHERE = 100


def affinity(term: str, name: str) -> int:
    """How directly `name` answers somebody typing `term`. Higher is better; 0 is no match.

    Four tiers, in the order a person means them. The **word itself** is the answer, and
    beats everything. A name that **starts with the word** is the plainest of the rest —
    `tomato paste` is more the thing than `canned peeled tomato`. A name carrying it as a
    **whole word** anywhere comes next. Anything else that merely contains the letters
    comes last, because it is usually a coincidence: `saltimbocca` begins with `salt` and
    `basalt` ends with it, and neither is salt.

    The top three tiers all require a **word**, not a run of letters. That is the whole
    distinction — without it, any word beginning with the term would outrank every name
    that actually contains it.

    Within a tier the **shorter** name wins. Two names equally direct differ only in how
    much else they carry, and the one carrying less is the plainer food — which is nearly
    always the one somebody typing a bare word meant.

    Accent-blind, via `fold`. Somebody looking for `creme fraiche` is looking for the same
    thing as somebody who found the accent key, and neither should be ranked below the
    other.
    """
    wanted, against = fold(term), fold(name)
    if not wanted or wanted not in against:
        return 0

    if against == wanted:
        tier = _EXACTLY
    else:
        # Where the term appears as a *word*. Anchored to word boundaries on purpose:
        # `salt` begins `saltimbocca`, which has nothing to do with salt, and promoting it
        # a whole tier for that would put it above `sea salt flakes`.
        found = re.search(rf"\b{re.escape(wanted)}\b", against)
        if found is None:
            tier = _ANYWHERE
        elif found.start() == 0:
            tier = _STARTS_WITH
        else:
            tier = _WHOLE_WORD

    # Shorter is better, so length is subtracted — capped so that a very long name cannot
    # subtract its way down into the tier below.
    return tier + max(0, 99 - len(against))
