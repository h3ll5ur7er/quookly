import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any


def coro[**P, R](f: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, R]:
    """Adapt an async function into the sync callable Typer expects."""

    @wraps(f)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return asyncio.run(f(*args, **kwargs))

    return wrapper
