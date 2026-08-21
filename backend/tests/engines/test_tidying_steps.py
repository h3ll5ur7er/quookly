"""Turning a website's instructions into ones a cook can follow (V2, UC-1.3).

The founding annoyance, arriving through the front door. A recipe page's method is written
to be read on a sofa: several actions to a paragraph, a step for gathering the ingredients,
and a sentence about the author's grandmother in the middle of the béchamel. Imported
verbatim, that is the thing this product exists to replace.

So the steps are edited on the way in. The rule that matters is what must **survive**: a
time, a temperature, a doneness cue, a warning. Losing "do not overmix" would be a worse
import than a wordy one.
"""

import json
from typing import Any

from pytest import MonkeyPatch

from quookly.access import model as inference
from quookly.contracts.execution import Attention
from quookly.contracts.inference import Completion
from quookly.contracts.interpretation import InterpretedStep
from quookly.engines import interpretation

WRITTEN = [
    InterpretedStep(instruction="Gather all ingredients."),
    InterpretedStep(
        instruction=(
            "Cut 185g unsalted butter into small cubes and tip into a medium bowl. "
            "Break 185g dark chocolate into small pieces and drop into the bowl."
        )
    ),
    InterpretedStep(instruction="Enjoy! And do let me know in the comments how it went."),
]

EDITED = {
    "steps": [
        {"instruction": "Cube the butter into a medium bowl.", "attention": "hands_on"},
        {"instruction": "Break the chocolate into the bowl.", "attention": "hands_on"},
    ]
}


def answering(
    body: dict[str, Any], monkeypatch: MonkeyPatch, capture: dict[str, Any] | None = None
) -> None:
    """Stand in for the model, and optionally record what it was asked."""

    async def complete_structured(
        prompt: str, schema: dict[str, Any], system: str | None = None
    ) -> tuple[dict[str, Any], Completion]:
        if capture is not None:
            capture.update({"prompt": prompt, "schema": schema, "system": system})
        return body, Completion(text=json.dumps(body), model="test")

    monkeypatch.setattr(inference, "complete_structured", complete_structured)


def refusing(monkeypatch: MonkeyPatch, failure: Exception) -> None:
    async def complete_structured(
        prompt: str, schema: dict[str, Any], system: str | None = None
    ) -> tuple[dict[str, Any], Completion]:
        raise failure

    monkeypatch.setattr(inference, "complete_structured", complete_structured)


class TestEditing:
    async def test_a_step_with_two_actions_becomes_two(self, monkeypatch: MonkeyPatch) -> None:
        answering(EDITED, monkeypatch)
        tidied = await interpretation.tidy_steps(WRITTEN)
        assert [step.instruction for step in tidied] == [
            "Cube the butter into a medium bowl.",
            "Break the chocolate into the bowl.",
        ]

    async def test_what_is_not_an_instruction_is_gone(self, monkeypatch: MonkeyPatch) -> None:
        answering(EDITED, monkeypatch)
        tidied = await interpretation.tidy_steps(WRITTEN)
        assert all("grandmother" not in step.instruction for step in tidied)
        assert all("Gather" not in step.instruction for step in tidied)

    async def test_what_each_step_asks_of_the_cook_is_read(self, monkeypatch: MonkeyPatch) -> None:
        answering(
            {
                "steps": [
                    {"instruction": "Bake until pale gold.", "attention": "waiting"},
                    {"instruction": "Cut while warm.", "attention": "hands_on"},
                ]
            },
            monkeypatch,
        )
        tidied = await interpretation.tidy_steps(WRITTEN)
        assert [step.attention for step in tidied] == [Attention.WAITING, Attention.HANDS_ON]

    async def test_a_time_in_the_words_becomes_a_timer(self, monkeypatch: MonkeyPatch) -> None:
        """The point of editing rather than only trimming: a step that is one action can
        carry the timer for it (UC-9.4)."""
        answering(
            {"steps": [{"instruction": "Bake at 180°C for 25 minutes.", "attention": "waiting"}]},
            monkeypatch,
        )
        tidied = await interpretation.tidy_steps(WRITTEN)
        assert tidied[0].duration_seconds == 1500
        assert tidied[0].temperature_celsius == 180

    async def test_it_is_told_what_must_survive(self, monkeypatch: MonkeyPatch) -> None:
        """The whole risk of this pass. A shorter step that lost "do not overmix" is a
        worse import than the wordy one it replaced."""
        asked: dict[str, Any] = {}
        answering(EDITED, monkeypatch, asked)
        await interpretation.tidy_steps(WRITTEN)
        told = f"{asked['system']}".lower()
        assert "do not overmix" in told or "warning" in told
        assert "temperature" in told
        assert "invent" in told or "not say" in told

    async def test_it_is_given_the_steps_as_written(self, monkeypatch: MonkeyPatch) -> None:
        asked: dict[str, Any] = {}
        answering(EDITED, monkeypatch, asked)
        await interpretation.tidy_steps(WRITTEN)
        assert "Break 185g dark chocolate" in asked["prompt"]


class TestWhenItCannotHelp:
    async def test_an_instance_with_no_model_keeps_the_steps_it_had(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Editing is an improvement, not a requirement. An instance with no model can
        still import from every site that publishes its recipes properly."""
        from quookly.contracts.errors import InferenceNotConfigured

        refusing(monkeypatch, InferenceNotConfigured("nothing configured"))
        assert await interpretation.tidy_steps(WRITTEN) == WRITTEN

    async def test_a_model_that_fails_keeps_the_steps_it_had(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        refusing(monkeypatch, RuntimeError("the model fell over"))
        assert await interpretation.tidy_steps(WRITTEN) == WRITTEN

    async def test_an_empty_answer_keeps_the_steps_it_had(self, monkeypatch: MonkeyPatch) -> None:
        """A recipe with no method is not an improvement on a wordy one."""
        answering({"steps": []}, monkeypatch)
        assert await interpretation.tidy_steps(WRITTEN) == WRITTEN

    async def test_nothing_to_edit(self, monkeypatch: MonkeyPatch) -> None:
        answering(EDITED, monkeypatch)
        assert await interpretation.tidy_steps([]) == []

    async def test_a_time_the_site_gave_survives_when_no_step_says_one(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """A site's single `cookTime` is a poor answer and better than none. It is a
        fallback, so a recipe whose steps say their own times keeps those instead."""
        answering(EDITED, monkeypatch)
        tidied = await interpretation.tidy_steps(
            [
                InterpretedStep(instruction="Mix."),
                InterpretedStep(
                    instruction="Bake.", duration_seconds=1800, attention=Attention.WAITING
                ),
            ]
        )
        assert tidied[-1].duration_seconds == 1800
        assert tidied[-1].attention is Attention.WAITING
        assert tidied[0].duration_seconds is None
