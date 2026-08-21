"""What comes back from asking a model (V3, ADR-003).

`ModelAccess` encapsulates *reaching* a model. What to ask, and how to read the answer,
belongs to the engines above it — so nothing here describes a prompt or a recipe.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Completion:
    """One answer, and enough about it to trace where it came from.

    `model` is what actually answered rather than what was asked for: a provider may
    route to something else, and a puzzling recipe should be traceable to the model that
    produced it. Nothing chooses behaviour by reading it.
    """

    text: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """What this instance is pointed at, for an operator to check (UC-8.2).

    The credential is deliberately absent. "Is a key set" is answerable without one, and
    a status object that carries a secret ends up in a log.
    """

    configured: bool
    base_url: str | None = None
    model: str | None = None
    authenticated: bool = False
