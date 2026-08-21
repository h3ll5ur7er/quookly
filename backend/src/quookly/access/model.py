"""Access to an inference provider (V3, FR-8, ADR-003).

This service encapsulates *reaching* a model and nothing else. It does not know what a
recipe is, does not compose prompts, and does not judge answers beyond checking that the
shape asked for is the shape that arrived. What to ask and how to read the reply belongs
to the engines above, because those change constantly while provider plumbing changes
only when somebody switches backends.

**One wire format, not a plugin system.** Requests are OpenAI-shaped chat completions,
which is what vLLM, Ollama, llama.cpp, LM Studio, OpenAI, OpenRouter and Together all
speak. That satisfies "at least one local and one hosted provider" (FR-8) with one
implementation rather than an abstraction over providers that mostly agree already. A
provider that speaks something else earns its own access service when somebody needs it.

Failures are ordinary outcomes here, not exceptions in the colloquial sense. A
self-hosted model is often simply switched off, and the difference between *not
configured*, *unreachable* and *refused* is the difference between three things an
operator would do next.
"""

import json
from dataclasses import replace
from typing import Any

import httpx

from quookly.contracts.errors import (
    InferenceNotConfigured,
    InferenceRefused,
    InferenceUnavailable,
    StructuredOutputUnusable,
)
from quookly.contracts.inference import Completion, ProviderStatus
from quookly.utilities.configuration import get_settings
from quookly.utilities.diagnostics import get_logger

log = get_logger("inference")

# Extraction is not creative writing: the same page should yield the same recipe twice.
DETERMINISTIC = 0.0
DEFAULT_MAX_TOKENS = 4096

#: How long a "is this thing on" check waits. Deliberately short: a model that is slow to
#: answer is working, one that is slow to list its own models is not, and an operator
#: staring at a status page for three minutes has learned nothing but that.
PROBE_TIMEOUT_SECONDS = 5.0

# Refusals an operator can act on, as opposed to faults they can only wait out.
_REFUSAL_STATUSES = frozenset({401, 402, 403, 429})


def _transport() -> httpx.AsyncBaseTransport | None:
    """The transport to use. Replaced in tests; `None` means the real network."""
    return None


def _configuration() -> tuple[str, str, str]:
    settings = get_settings()
    base_url = settings.inference_base_url.strip().rstrip("/")
    if not base_url:
        raise InferenceNotConfigured(
            "No inference provider is configured. Set QUOOKLY_INFERENCE_BASE_URL and "
            "QUOOKLY_INFERENCE_MODEL."
        )
    return base_url, settings.inference_model, settings.inference_api_key.get_secret_value()


def _headers(api_key: str) -> dict[str, str]:
    """Bearer only when there is one. A local vLLM wants no credential at all."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def describe() -> ProviderStatus:
    """What this instance will ask, without asking it (UC-8.2)."""
    settings = get_settings()
    base_url = settings.inference_base_url.strip().rstrip("/")
    if not base_url:
        return ProviderStatus(
            configured=False,
            detail=(
                "No inference provider is configured. Set QUOOKLY_INFERENCE_BASE_URL and "
                "QUOOKLY_INFERENCE_MODEL to point this instance at one."
            ),
        )
    return ProviderStatus(
        configured=True,
        base_url=base_url,
        model=settings.inference_model,
        authenticated=bool(settings.inference_api_key.get_secret_value()),
    )


async def reachable() -> bool:
    """Whether the provider answers at all — "is this thing on" (UC-8.2).

    Returns rather than raises: this is asked in order to *report* a state, and a
    diagnostic that throws when the thing it diagnoses is broken is no diagnostic.
    """
    return (await probe()).reachable is True


async def probe() -> ProviderStatus:
    """What this instance is pointed at, and whether it answers (UC-8.2).

    The probe has its own short timeout rather than the one an actual completion gets. A
    model that takes three minutes to think is working; one that takes three minutes to
    list its own models is not, and an operator waiting that long for a status page has
    been told nothing except that something is wrong.
    """
    described = await describe()
    if not described.configured:
        return described

    base_url, _, api_key = _configuration()
    try:
        async with _client(base_url, api_key, timeout=PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get("/models")
    except httpx.HTTPError as unreachable:
        return replace(described, reachable=False, detail=f"could not reach it: {unreachable}")

    if response.status_code in _REFUSAL_STATUSES:
        # The address is right and the credential is not, which is a different thing to
        # go and fix from a provider that is switched off.
        return replace(
            described,
            reachable=False,
            detail=f"it refused the request ({response.status_code}) — check the key",
        )
    if response.status_code >= 400:
        return replace(described, reachable=False, detail=f"it answered {response.status_code}")
    return replace(described, reachable=True)


def _client(base_url: str, api_key: str, timeout: float | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        headers=_headers(api_key),
        timeout=timeout or get_settings().inference_timeout_seconds,
        transport=_transport(),
    )


async def _ask(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Send one chat completion and return the raw answer, or say why not.

    The request body never reaches the log and neither does the credential. A prompt can
    carry a whole web page, and a log is the wrong place for either.
    """
    base_url, model, api_key = _configuration()
    try:
        async with _client(base_url, api_key) as client:
            response = await client.post("/chat/completions", json={"model": model, **payload})
    except httpx.HTTPError as unreachable:
        # The exception's own text is safe — it names a host, not a header — but it is
        # rebuilt from the URL rather than interpolated, so a future httpx cannot start
        # including request headers in it.
        log.warning("inference unreachable", extra={"base_url": base_url})
        raise InferenceUnavailable(f"could not reach {base_url}") from unreachable

    if response.status_code in _REFUSAL_STATUSES:
        raise InferenceRefused(f"{base_url} refused the request ({response.status_code})")
    if response.status_code >= 400:
        raise InferenceUnavailable(f"{base_url} failed ({response.status_code})")

    try:
        body = response.json()
    except ValueError as unreadable:
        raise StructuredOutputUnusable(f"{base_url} did not return JSON") from unreadable

    choices = body.get("choices") or []
    if not choices:
        raise StructuredOutputUnusable(f"{base_url} returned no answer")
    return body, str(choices[0].get("message", {}).get("content") or "")


def _messages(prompt: str, system: str | None) -> list[dict[str, str]]:
    conversation = [] if system is None else [{"role": "system", "content": system}]
    return [*conversation, {"role": "user", "content": prompt}]


def _completion(body: dict[str, Any], text: str) -> Completion:
    usage = body.get("usage") or {}
    return Completion(
        text=text,
        model=str(body.get("model", "")),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )


async def complete(
    prompt: str,
    *,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DETERMINISTIC,
) -> Completion:
    """Ask for an answer in prose."""
    body, text = await _ask(
        {
            "messages": _messages(prompt, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    )
    return _completion(body, text)


def _unfence(text: str) -> str:
    """Take JSON out of a code fence, if a model put it in one.

    Models wrap JSON in fences often enough that refusing those wastes good answers. This
    is not repair: whatever is between the fences still has to parse on its own.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    without_opener = stripped.split("\n", 1)[-1]
    return without_opener.rsplit("```", 1)[0].strip()


async def complete_structured(
    prompt: str,
    schema: dict[str, Any],
    *,
    system: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DETERMINISTIC,
) -> tuple[dict[str, Any], Completion]:
    """Ask for an answer shaped like `schema`.

    The model fills a shape; it does not author one. An answer that is not that shape is
    refused rather than repaired — a half-read recipe is a recipe missing ingredients,
    and quietly correcting a model is the failure FR-9 exists to prevent.
    """
    body, text = await _ask(
        {
            "messages": _messages(prompt, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "quookly", "strict": True, "schema": schema},
            },
        }
    )

    if (body.get("choices") or [{}])[0].get("finish_reason") == "length":
        # Cut off mid-answer. What arrived may even parse, and would be missing whatever
        # came after the cut — which for a recipe is ingredients.
        raise StructuredOutputUnusable("the answer was cut short by the token limit")

    try:
        parsed = json.loads(_unfence(text))
    except ValueError as unreadable:
        raise StructuredOutputUnusable("the answer was not JSON") from unreadable
    if not isinstance(parsed, dict):
        raise StructuredOutputUnusable(f"expected an object, got {type(parsed).__name__}")
    return parsed, _completion(body, text)
