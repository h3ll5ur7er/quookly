"""Structured logging and request correlation.

Production logs JSON, one object per line, so a self-hoster can grep or ship it.
Development logs for a human reading a terminal. Both carry a request id when one is in
scope, which is what makes the several lines of one request findable together.

Built on the standard library rather than a logging framework: one fewer dependency in
something every deployment runs, and the formatter is short enough to read.
"""

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

ROOT_LOGGER_NAME = "quookly"
HANDLER_NAME = "quookly"

_request_id: ContextVar[str | None] = ContextVar("quookly_request_id", default=None)

# Attributes the standard library puts on every record. Anything else was added by the
# caller and is worth carrying into the log line.
_STANDARD_ATTRIBUTES = frozenset(
    set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)
    | {"message", "asctime", "taskName"}
)


def current_request_id() -> str | None:
    """The id of the request being handled, if any."""
    return _request_id.get()


@contextmanager
def use_request_id(request_id: str) -> Iterator[None]:
    """Attach an id to everything logged inside this scope."""
    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = current_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Whatever the caller passed as `extra=`, without the noise.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRIBUTES and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """Readable in a terminal, with the request id inline when there is one."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s  %(message)s", "%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        request_id = current_request_id()
        return f"{line}  [{request_id}]" if request_id else line


def configure_logging() -> None:
    """Install the handler for this environment.

    Idempotent: calling it twice must not double every line, which is the usual result
    of configuring logging from more than one entry point.
    """
    from quookly.utilities.configuration import get_settings

    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(
        JsonFormatter() if settings.environment == "production" else HumanFormatter()
    )

    root = logging.getLogger()
    # Replace only our own handler. Removing every handler would silence whatever else
    # attached one — uvicorn, a test harness, or a self-hoster's own configuration.
    for existing in list(root.handlers):
        if existing.get_name() == HANDLER_NAME:
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(settings.log_level)


def get_logger(name: str) -> logging.Logger:
    """A logger namespaced under the application, so its level can be set as a group."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
