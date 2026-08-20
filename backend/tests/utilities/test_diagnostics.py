"""Structured logging and request correlation.

Logs are what a self-hoster has when something goes wrong at 19:00 with a pan on the
hob. They need to be machine-readable in production, legible in development, and they
must never contain a password.
"""

import json
import logging
from collections.abc import Iterator

import pytest
from pytest import MonkeyPatch

from quookly.utilities.configuration import get_settings
from quookly.utilities.diagnostics import (
    HANDLER_NAME,
    JsonFormatter,
    configure_logging,
    current_request_id,
    get_logger,
    use_request_id,
)


@pytest.fixture(autouse=True)
def clean_logging(monkeypatch: MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("QUOOKLY_LOG_LEVEL", raising=False)
    monkeypatch.delenv("QUOOKLY_ENVIRONMENT", raising=False)
    get_settings.cache_clear()
    root = logging.getLogger()
    original = list(root.handlers), root.level
    yield
    root.handlers, root.level = original[0], original[1]
    get_settings.cache_clear()


def installed_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if h.get_name() == HANDLER_NAME]


def record(message: str = "hello", **extra: object) -> logging.LogRecord:
    made = logging.LogRecord("quookly.test", logging.INFO, __file__, 10, message, None, None)
    for key, value in extra.items():
        setattr(made, key, value)
    return made


class TestJsonFormatting:
    def test_a_record_formats_as_one_json_object(self) -> None:
        """One line per event, or log shipping has to reassemble them."""
        formatted = JsonFormatter().format(record("stock reserved"))
        assert "\n" not in formatted
        assert json.loads(formatted)["message"] == "stock reserved"

    def test_the_essentials_are_present(self) -> None:
        payload = json.loads(JsonFormatter().format(record()))
        assert payload["level"] == "INFO"
        assert payload["logger"] == "quookly.test"
        assert payload["timestamp"]

    def test_the_request_id_travels_with_the_record(self) -> None:
        """Correlating the lines of one request is the whole point of having an id."""
        with use_request_id("abc-123"):
            payload = json.loads(JsonFormatter().format(record()))
        assert payload["request_id"] == "abc-123"

    def test_a_record_outside_a_request_has_no_request_id(self) -> None:
        payload = json.loads(JsonFormatter().format(record()))
        assert "request_id" not in payload

    def test_an_exception_is_included_as_text(self) -> None:
        try:
            raise ValueError("deliberate")
        except ValueError:
            made = record("failed")
            made.exc_info = __import__("sys").exc_info()
            payload = json.loads(JsonFormatter().format(made))
        assert "ValueError: deliberate" in payload["exception"]


class TestConfiguration:
    def test_production_logs_json(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("QUOOKLY_ENVIRONMENT", "production")
        monkeypatch.setenv("QUOOKLY_SECRET_KEY", "a-signing-key-long-enough-for-hs256-0123")
        get_settings.cache_clear()
        configure_logging()
        assert isinstance(installed_handlers()[0].formatter, JsonFormatter)

    def test_development_logs_for_humans(self) -> None:
        configure_logging()
        assert not isinstance(installed_handlers()[0].formatter, JsonFormatter)

    def test_configuring_twice_does_not_double_every_line(self) -> None:
        configure_logging()
        configure_logging()
        assert len(installed_handlers()) == 1

    def test_handlers_we_do_not_own_are_left_alone(self) -> None:
        """Removing every handler would silence uvicorn, or a self-hoster's own setup."""
        foreign = logging.NullHandler()
        foreign.set_name("somebody-else")
        logging.getLogger().addHandler(foreign)
        configure_logging()
        assert foreign in logging.getLogger().handlers

    def test_the_level_is_configurable(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("QUOOKLY_LOG_LEVEL", "WARNING")
        get_settings.cache_clear()
        configure_logging()
        assert logging.getLogger().level == logging.WARNING


class TestRequestId:
    def test_there_is_no_id_outside_a_request(self) -> None:
        assert current_request_id() is None

    def test_the_id_is_restored_afterwards(self) -> None:
        """Nested scopes must not leak an id into whatever runs next."""
        with use_request_id("outer"):
            with use_request_id("inner"):
                assert current_request_id() == "inner"
            assert current_request_id() == "outer"
        assert current_request_id() is None


class TestLoggers:
    def test_loggers_are_namespaced_under_the_application(self) -> None:
        assert get_logger("managers.account").name == "quookly.managers.account"
