"""Reading prose with a real model.

Skipped unless a provider is configured. The stubbed tests next door cover the engine's
behaviour given an answer; this covers the thing no stub can — whether a real model,
given these instructions, produces answers the reader can actually use.

    QUOOKLY_INFERENCE_BASE_URL=http://localhost:8000/v1 \\
    QUOOKLY_INFERENCE_MODEL=your-model \\
    just backend test -- -m live
"""

import os

import pytest

from quookly.contracts.interpretation import InterpretedRecipe, Source
from quookly.contracts.measure import Unit
from quookly.contracts.web import ReadableContent
from quookly.engines import interpretation
from quookly.utilities.configuration import get_settings

pytestmark = pytest.mark.live

# A blog in the shape the product exists to solve: forty words of recipe wrapped in a
# thousand of reminiscence, with the amounts written into the sentences.
BLOG = """
The Only Pancakes I Make Any More

My grandmother, on a windswept morning somewhere around 1962, first showed me what she
called the secret to pancakes. It was a Tuesday. The kitchen smelled of rain and
possibility, and I have never forgotten the way the light fell across the linoleum.

Before we get to it: a word about resting the batter. Everyone will tell you twenty
minutes. Everyone is wrong. Give it half an hour if you can.

You will want 225g of plain flour, sifted if you can be bothered, and a good pinch of
salt. Then 300ml of whole milk and 2 large eggs, beaten. A knob of butter for the pan,
and 1 tablespoon of caster sugar if you like them sweet — optional, obviously.

Sift the flour and salt into a wide bowl and make a well in the middle. Beat the eggs into
the milk, then pour the lot into the well and whisk outwards until smooth. Rest the batter
for thirty minutes. Heat a knob of butter in a heavy pan until it foams, pour in a
ladleful, and swirl to coat the base. Cook for about a minute, then flip.

Makes about 8. Serve with lemon and sugar.

Subscribe to my newsletter for more stories like this one.
"""


@pytest.fixture(autouse=True)
def a_configured_provider() -> None:
    if not os.getenv("QUOOKLY_INFERENCE_BASE_URL"):
        pytest.skip("no QUOOKLY_INFERENCE_BASE_URL configured")
    get_settings.cache_clear()


@pytest.fixture
async def read() -> InterpretedRecipe:
    page = ReadableContent(url="https://example.com/blog", text=BLOG, title="The Only Pancakes")
    return await interpretation.read_page(page)


class TestABlogWithNoMetadata:
    async def test_a_model_reads_it(self, read: InterpretedRecipe) -> None:
        assert read.source is Source.MODEL
        assert read.title

    async def test_the_amounts_in_the_sentences_are_found(self, read: InterpretedRecipe) -> None:
        by_name = {line.ingredient.lower(): line for line in read.lines}
        flour = next(line for name, line in by_name.items() if "flour" in name)
        assert flour.magnitude == 225
        assert flour.unit is Unit.GRAM
        milk = next(line for name, line in by_name.items() if "milk" in name)
        assert milk.magnitude == 300
        assert milk.unit is Unit.MILLILITRE

    async def test_the_ingredient_names_are_clean_enough_to_resolve(
        self, read: InterpretedRecipe
    ) -> None:
        """ "butter for the pan" never matches a registry entry and "butter" does. This is
        the difference between an import a cook accepts and one they have to repair."""
        for line in read.lines:
            assert len(line.ingredient.split()) <= 4, line.ingredient
            assert " if " not in line.ingredient
            assert not line.ingredient.lower().startswith(("a ", "an "))

    async def test_a_vague_amount_is_not_given_a_number(self, read: InterpretedRecipe) -> None:
        """ "A good pinch of salt" is a judgement. Inventing a gram figure for it would be
        a number a cook cannot see is wrong."""
        salt = next(line for line in read.lines if "salt" in line.ingredient.lower())
        assert salt.magnitude is None

    async def test_the_yield_written_into_a_sentence_is_found(
        self, read: InterpretedRecipe
    ) -> None:
        assert read.yield_magnitude == 8

    async def test_the_reminiscence_does_not_survive(self, read: InterpretedRecipe) -> None:
        """The whole point. None of the grandmother, none of the newsletter."""
        method = " ".join(step.instruction for step in read.steps).lower()
        assert "grandmother" not in method
        assert "newsletter" not in method
        assert "linoleum" not in method

    async def test_the_method_survives(self, read: InterpretedRecipe) -> None:
        method = " ".join(step.instruction for step in read.steps).lower()
        assert "well" in method
        assert "rest" in method or "thirty minutes" in method
