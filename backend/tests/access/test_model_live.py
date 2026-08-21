"""ModelAccess against a real provider.

Skipped unless `QUOOKLY_INFERENCE_BASE_URL` is set, because a test suite that needs a
running model is a test suite nobody runs. The stubbed tests next door cover the
behaviour; these cover the assumption underneath it — that the provider actually speaks
the wire format this service writes, which no stub can tell us.

Run against a local vLLM with:

    QUOOKLY_INFERENCE_BASE_URL=http://jarvis:9293/v1 \\
    QUOOKLY_INFERENCE_MODEL=nvidia/Qwen3.6-35B-A3B-NVFP4 \\
    just backend test -- -m live
"""

import os
from typing import Any

import pytest

from quookly.access import model as inference
from quookly.utilities.configuration import get_settings

pytestmark = pytest.mark.live

RECIPE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "ingredients": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "ingredients"],
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def a_configured_provider() -> None:
    if not os.getenv("QUOOKLY_INFERENCE_BASE_URL"):
        pytest.skip("no QUOOKLY_INFERENCE_BASE_URL configured")
    get_settings.cache_clear()


class TestAgainstARealProvider:
    async def test_it_answers_at_all(self) -> None:
        assert await inference.reachable() is True

    async def test_it_returns_prose(self) -> None:
        completion = await inference.complete("Reply with the single word: pancake.", max_tokens=32)
        assert "pancake" in completion.text.lower()

    async def test_it_honours_a_schema(self) -> None:
        """The assumption the whole import path rests on: this provider can be made to
        fill a shape rather than write prose about one."""
        parsed, completion = await inference.complete_structured(
            "Extract the recipe. Text: Cheese toast. 4 slices bread, 100g cheddar.",
            RECIPE_SCHEMA,
            max_tokens=512,
        )
        assert set(parsed) == {"title", "ingredients"}
        assert isinstance(parsed["ingredients"], list)
        assert completion.model
