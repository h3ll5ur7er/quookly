"""The `inference` subcommand (UC-8.2).

An operator's diagnostic. It runs on the machine the instance runs on, at the moment
something is wrong — so what it must never do is fail in a way that looks like the thing
it is diagnosing. An unreachable API, an unconfigured provider and a refused credential
are three different messages and three different exit codes are not needed to tell them
apart; the words are.
"""

from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from quookly_cli.api_client.api.instance import get_inference_status
from quookly_cli.api_client.models.inference_status_view import InferenceStatusView
from quookly_cli.cli import app

runner = CliRunner()


def answering(monkeypatch: pytest.MonkeyPatch, status: Any) -> None:
    """Stand in for the API."""

    async def respond(*args: Any, **options: Any) -> Any:
        return status

    monkeypatch.setattr(get_inference_status, "asyncio", respond)


def configured(**overrides: Any) -> InferenceStatusView:
    return InferenceStatusView.from_dict(
        {
            "configured": True,
            "base_url": "http://jarvis:9293/v1",
            "model": "a-model",
            "authenticated": False,
            "reachable": True,
            "detail": None,
            **overrides,
        }
    )


def run(*arguments: str) -> Any:
    return runner.invoke(app, ["inference", "status", "--token", "a-token", *arguments])


class TestWhenAllIsWell:
    def test_it_says_what_the_instance_will_ask(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answering(monkeypatch, configured())
        result = run()
        assert result.exit_code == 0
        assert "jarvis" in result.output
        assert "a-model" in result.output

    def test_it_says_that_it_answered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answering(monkeypatch, configured())
        assert "reachable" in run().output.lower()


class TestWhenSomethingIsWrong:
    def test_an_unconfigured_instance_is_told_what_to_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The difference between a diagnostic and a support question."""
        answering(
            monkeypatch,
            InferenceStatusView.from_dict(
                {
                    "configured": False,
                    "detail": "Set QUOOKLY_INFERENCE_BASE_URL and QUOOKLY_INFERENCE_MODEL.",
                }
            ),
        )
        result = run()
        assert result.exit_code == 1
        assert "QUOOKLY_INFERENCE_BASE_URL" in result.output

    def test_an_unreachable_provider_reports_why(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answering(
            monkeypatch,
            configured(reachable=False, detail="could not reach it: no route to host"),
        )
        result = run()
        assert result.exit_code == 1
        assert "no route to host" in result.output

    def test_an_unreachable_api_is_told_apart_from_an_unreachable_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two different machines to go and look at. A diagnostic that conflates them
        sends an operator to the wrong one.

        The client *raises* when it cannot connect rather than returning nothing — an
        earlier version of this test faked it as a `None` return, so the friendly branch
        was never reached and running it for real printed a stack trace.
        """

        async def refuse(*args: Any, **options: Any) -> Any:
            raise httpx.ConnectError("All connection attempts failed")

        monkeypatch.setattr(get_inference_status, "asyncio", refuse)
        result = run()
        assert result.exit_code == 1
        assert "quookly" in result.output.lower()
        assert "Traceback" not in result.output

    def test_an_unexpected_answer_is_also_survived(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The generated client returns nothing for a status it was not taught about."""
        answering(monkeypatch, None)
        result = run()
        assert result.exit_code == 1
        assert "quookly" in result.output.lower()

    def test_an_unconfigured_instance_is_not_told_twice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answering(
            monkeypatch,
            InferenceStatusView.from_dict(
                {"configured": False, "detail": "No inference provider is configured."}
            ),
        )
        assert run().output.count("No inference provider is configured") == 1


class TestCredentials:
    def test_it_refuses_without_one_rather_than_failing_obscurely(self) -> None:
        """The endpoint is administrators only. "You need a token" beats a bare 403."""
        result = runner.invoke(app, ["inference", "status"])
        assert result.exit_code == 1
        assert "token" in result.output.lower()

    def test_it_never_prints_the_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answering(monkeypatch, configured())
        assert "a-token" not in run().output

    def test_it_says_whether_a_key_is_set_without_saying_what(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        answering(monkeypatch, configured(authenticated=True))
        output = run().output.lower()
        assert "key" in output
