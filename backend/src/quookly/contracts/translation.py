"""A recipe's prose, as it travels to and from a translation.

Prose only. Quantities, durations and temperatures are columns rendered per cook, and
ingredient names resolve through the registry per locale — none of it is here, which is
why translating a recipe cannot change what it asks for (ADR-032).
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict


@dataclass(frozen=True, slots=True)
class Translatable:
    """The words of a recipe, in one language.

    Steps are a list rather than one blob because a stored translation is paired back to
    the recipe **by position**: step three of the translation is step three of the recipe.
    That pairing is the only thing that makes a stored translation usable, and it is why
    an answer with the wrong number of steps is refused rather than repaired.
    """

    title: str
    summary: str | None = None
    steps: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HeldTranslation:
    """A translation as stored, and who wrote it.

    Only ever returned for a translation that still matches the recipe: `TranslationAccess`
    compares fingerprints, so a caller holding one of these is holding words that describe
    the recipe as it is now (ADR-064).
    """

    words: Translatable
    by_hand: bool


class TranslationView(BaseModel):
    """A translation as a client reads it, and who wrote it.

    `by_hand` is the load-bearing field. A model's translation is re-derived when the
    recipe changes under it; a person's is kept and stopped being shown, because a model
    silently overwriting somebody's correction is worse than no correction (ADR-064).
    """

    model_config = ConfigDict(frozen=True)

    locale: str
    by_hand: bool
    #: Whether the recipe has changed since this was written. A translation of a sentence
    #: that is no longer there is not stale — it is a wrong instruction, so it is not
    #: shown (ADR-064).
    current: bool
