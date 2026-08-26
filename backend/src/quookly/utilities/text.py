"""Folding the ways one name gets written.

A utility rather than a private helper in the access layer, because two callers need it
and they sit on different layers: the registry stores normalised names, and the matching
engine compares written ones. Utilities depend on nothing else, which this does not.

Two functions, deliberately not one.

`normalise` is what the registry **stores** and matches exactly. Its result is a column
with a unique index on it, so what it does is part of the schema: changing it means
re-normalising every row and risking a collision the index would reject.

`fold` goes further and throws away accents. That is useful for *finding* a name — 28% of
the shipped registry's name rows carry diacritics, and pages routinely strip them — and
dangerous for *deciding* one, because different words fold together: French `pêche` is a
peach and `pèche` is fishing. Callers use it to look, never to conclude.
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
