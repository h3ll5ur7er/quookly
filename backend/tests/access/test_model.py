"""Reaching a model (V3, FR-8, ADR-003).

`ModelAccess` encapsulates *reaching* a model and nothing else: no prompt strategy, no
reading of what came back beyond "is this the shape that was asked for". Which provider
served the answer is not knowable anywhere above this layer.

Nothing here talks to a real model. The transport is stubbed, which is what makes the
failure cases — refused, unreachable, unusable output — testable at all: they are the
cases that matter and the ones a live endpoint will not produce on demand.
"""

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from pytest import MonkeyPatch

from quookly.access import model as inference
from quookly.contracts.errors import (
    InferenceNotConfigured,
    InferenceRefused,
    InferenceUnavailable,
    StructuredOutputUnusable,
)
from quookly.utilities.configuration import get_settings

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}


def chat_response(content: str, model: str = "a-model") -> dict[str, Any]:
    return {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 22},
    }


@pytest.fixture
def configured(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("QUOOKLY_INFERENCE_BASE_URL", "http://jarvis:9293/v1")
    monkeypatch.setenv("QUOOKLY_INFERENCE_MODEL", "a-model")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def forget_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def stub(handler: Callable[[httpx.Request], httpx.Response], monkeypatch: MonkeyPatch) -> None:
    """Answer every request from this handler rather than the network."""
    monkeypatch.setattr(inference, "_transport", lambda: httpx.MockTransport(handler))


def answering(body: dict[str, Any], status: int = 200) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _: httpx.Response(status, json=body)


class TestWithoutAProvider:
    async def test_completing_is_refused_rather_than_guessed_at(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """An instance with no model configured says so; it does not fail as a network error."""
        monkeypatch.delenv("QUOOKLY_INFERENCE_BASE_URL", raising=False)
        get_settings.cache_clear()
        with pytest.raises(InferenceNotConfigured):
            await inference.complete("hello")

    async def test_the_instance_reports_that_it_has_none(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.delenv("QUOOKLY_INFERENCE_BASE_URL", raising=False)
        get_settings.cache_clear()
        assert (await inference.describe()).configured is False

    async def test_a_configured_instance_reports_what_it_will_ask(self, configured: None) -> None:
        """UC-8.2: an operator has to be able to see what the instance is pointed at."""
        described = await inference.describe()
        assert described.configured is True
        assert described.model == "a-model"
        assert described.base_url == "http://jarvis:9293/v1"


class TestCompleting:
    async def test_the_text_comes_back(self, configured: None, monkeypatch: MonkeyPatch) -> None:
        stub(answering(chat_response("a pancake")), monkeypatch)
        assert (await inference.complete("hello")).text == "a pancake"

    async def test_which_model_answered_is_reported(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """Not to choose behaviour by, but so a puzzling recipe can be traced to a model."""
        stub(answering(chat_response("x", model="qwen")), monkeypatch)
        assert (await inference.complete("hello")).model == "qwen"

    async def test_it_asks_for_the_configured_model(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def capture(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return httpx.Response(200, json=chat_response("x"))

        stub(capture, monkeypatch)
        await inference.complete("hello")
        assert seen["model"] == "a-model"

    async def test_a_system_prompt_is_sent_first(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        def capture(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return httpx.Response(200, json=chat_response("x"))

        stub(capture, monkeypatch)
        await inference.complete("hello", system="be terse")
        assert [message["role"] for message in seen["messages"]] == ["system", "user"]

    async def test_it_asks_for_a_deterministic_answer_by_default(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """Extraction is not creative writing. The same page should give the same recipe."""
        seen: dict[str, Any] = {}

        def capture(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return httpx.Response(200, json=chat_response("x"))

        stub(capture, monkeypatch)
        await inference.complete("hello")
        assert seen["temperature"] == 0


class TestCredentials:
    async def test_a_key_is_sent_when_one_is_configured(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QUOOKLY_INFERENCE_API_KEY", "sk-secret")
        get_settings.cache_clear()
        seen: dict[str, str] = {}

        def capture(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, json=chat_response("x"))

        stub(capture, monkeypatch)
        await inference.complete("hello")
        assert seen["authorization"] == "Bearer sk-secret"

    async def test_no_key_is_sent_when_none_is_configured(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """A local vLLM wants no credential, and sending an empty bearer is worse than none."""
        seen: dict[str, str] = {}

        def capture(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, json=chat_response("x"))

        stub(capture, monkeypatch)
        await inference.complete("hello")
        assert "authorization" not in seen

    async def test_a_failure_does_not_carry_the_key_into_the_error(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """Errors are logged and shown; a key that rides along in one has leaked."""
        monkeypatch.setenv("QUOOKLY_INFERENCE_API_KEY", "sk-secret")
        get_settings.cache_clear()
        stub(answering({"error": "nope"}, status=500), monkeypatch)
        with pytest.raises(InferenceUnavailable) as failure:
            await inference.complete("hello")
        assert "sk-secret" not in str(failure.value)


class TestStructuredOutput:
    async def test_the_answer_is_parsed(self, configured: None, monkeypatch: MonkeyPatch) -> None:
        stub(answering(chat_response('{"title": "Pancakes"}')), monkeypatch)
        parsed, _ = await inference.complete_structured("read this", SCHEMA)
        assert parsed == {"title": "Pancakes"}

    async def test_the_schema_is_sent_with_the_request(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """The model fills a shape; it does not author one (UC-1.3)."""
        seen: dict[str, Any] = {}

        def capture(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return httpx.Response(200, json=chat_response('{"title": "x"}'))

        stub(capture, monkeypatch)
        await inference.complete_structured("read this", SCHEMA)
        assert seen["response_format"]["json_schema"]["schema"] == SCHEMA
        assert seen["response_format"]["json_schema"]["strict"] is True

    async def test_prose_instead_of_json_is_refused(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """Never repaired, never half-read. FR-9 applies to what a model says as well."""
        stub(answering(chat_response("Sure! Here is your recipe:")), monkeypatch)
        with pytest.raises(StructuredOutputUnusable):
            await inference.complete_structured("read this", SCHEMA)

    async def test_json_that_is_not_an_object_is_refused(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        stub(answering(chat_response("[1, 2, 3]")), monkeypatch)
        with pytest.raises(StructuredOutputUnusable):
            await inference.complete_structured("read this", SCHEMA)

    async def test_a_fenced_answer_is_still_read(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """Models wrap JSON in a code fence often enough that refusing it wastes good answers.

        Stripping a fence is not repairing the JSON inside it: what is between the fences
        must still parse on its own.
        """
        stub(answering(chat_response('```json\n{"title": "Pancakes"}\n```')), monkeypatch)
        parsed, _ = await inference.complete_structured("read this", SCHEMA)
        assert parsed == {"title": "Pancakes"}

    async def test_an_answer_cut_short_is_refused(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """A recipe truncated mid-ingredient is a recipe missing ingredients."""
        body = chat_response('{"title": "Pan')
        body["choices"][0]["finish_reason"] = "length"
        stub(answering(body), monkeypatch)
        with pytest.raises(StructuredOutputUnusable):
            await inference.complete_structured("read this", SCHEMA)


class TestWhenItGoesWrong:
    async def test_a_rejected_credential_is_reported_as_such(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """An operator can act on "your key is wrong"; they cannot act on "it failed"."""
        stub(answering({"error": "bad key"}, status=401), monkeypatch)
        with pytest.raises(InferenceRefused):
            await inference.complete("hello")

    async def test_a_quota_refusal_is_reported_as_such(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        stub(answering({"error": "slow down"}, status=429), monkeypatch)
        with pytest.raises(InferenceRefused):
            await inference.complete("hello")

    async def test_a_server_fault_is_unavailability(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        stub(answering({"error": "boom"}, status=503), monkeypatch)
        with pytest.raises(InferenceUnavailable):
            await inference.complete("hello")

    async def test_an_unreachable_host_is_unavailability(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """A model that is switched off is a normal outcome, not a crash."""

        def refuse(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        stub(refuse, monkeypatch)
        with pytest.raises(InferenceUnavailable):
            await inference.complete("hello")

    async def test_a_timeout_is_unavailability(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        def hang(_: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("took too long")

        stub(hang, monkeypatch)
        with pytest.raises(InferenceUnavailable):
            await inference.complete("hello")

    async def test_an_answer_with_no_choices_is_unusable(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        stub(answering({"model": "a-model", "choices": []}), monkeypatch)
        with pytest.raises(StructuredOutputUnusable):
            await inference.complete("hello")


class TestReachability:
    async def test_a_reachable_provider_reports_reachable(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        """UC-8.2: "is this thing on" is the first question an operator asks."""
        stub(answering({"data": [{"id": "a-model"}]}), monkeypatch)
        assert await inference.reachable() is True

    async def test_an_unreachable_provider_reports_unreachable_rather_than_raising(
        self, configured: None, monkeypatch: MonkeyPatch
    ) -> None:
        def refuse(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        stub(refuse, monkeypatch)
        assert await inference.reachable() is False

    async def test_an_unconfigured_provider_is_not_reachable(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        monkeypatch.delenv("QUOOKLY_INFERENCE_BASE_URL", raising=False)
        get_settings.cache_clear()
        assert await inference.reachable() is False
