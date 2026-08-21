"""What comes back from asking a model (V3, ADR-003).

`ModelAccess` encapsulates *reaching* a model. What to ask, and how to read the answer,
belongs to the engines above it — so nothing here describes a prompt or a recipe.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict


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
    #: None when nothing was tried — which is not the same as tried and failed.
    reachable: bool | None = None
    #: Why, in words an operator can act on. "Check the key" and "could not reach it" send
    #: somebody to two different places.
    detail: str | None = None


# What crosses the API.


class InferenceStatusView(BaseModel):
    """What this instance is pointed at, for the person running it (UC-8.2).

    The credential is deliberately absent, and `authenticated` says only whether one is
    set. A status page that prints a key has published it — into a screenshot, a support
    thread, a browser cache.
    """

    model_config = ConfigDict(frozen=True)

    configured: bool
    base_url: str | None = None
    model: str | None = None
    authenticated: bool = False
    reachable: bool | None = None
    detail: str | None = None
