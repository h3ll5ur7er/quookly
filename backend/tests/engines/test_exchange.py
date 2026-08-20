"""The interchange format (FR-11, ADR-012).

One format serves export and import, so every round trip exercises the promise that a
self-hoster is not trapped. The engine is pure: turning recipes into a document and back
is a transformation, and resolving what a document refers to is the manager's job.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from quookly.contracts.errors import UnsupportedDocument
from quookly.contracts.exchange import ExchangeDocument
from quookly.contracts.ingredient import Ingredient, IngredientKind, Origin
from quookly.contracts.measure import Quantity, Unit
from quookly.contracts.recipe import (
    IngredientLine,
    Provenance,
    Recipe,
    Step,
    Visibility,
)
from quookly.engines import exchange

FLOUR = Ingredient(
    id=1,
    slug="plain-flour",
    kind=IngredientKind.POWDER,
    name="plain flour",
    density=Decimal("0.53"),
    origin=Origin.SEED,
)
EGG = Ingredient(
    id=2,
    slug="egg",
    kind=IngredientKind.COUNTABLE,
    name="egg",
    density=None,
    origin=Origin.SEED,
)


def pancakes() -> Recipe:
    return Recipe(
        id=7,
        cook_id=1,
        title="Pancakes",
        summary="Batter, pan, patience.",
        yield_quantity=Quantity(Decimal("12"), Unit.PIECE),
        provenance=Provenance.AUTHORED,
        visibility=Visibility.PRIVATE,
        origin=Origin.USER,
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
        lines=[
            IngredientLine(
                id=1,
                ingredient=FLOUR,
                quantity=Quantity(Decimal("225"), Unit.GRAM),
                preparation="sifted",
                optional=False,
            ),
            IngredientLine(
                id=2,
                ingredient=EGG,
                quantity=Quantity(Decimal("2"), Unit.PIECE),
                preparation=None,
                optional=True,
            ),
        ],
        steps=[
            Step(id=1, instruction="Whisk.", duration_seconds=None, temperature_celsius=None),
            Step(id=2, instruction="Rest.", duration_seconds=1800, temperature_celsius=None),
        ],
    )


class TestExporting:
    def test_the_document_declares_its_format_version(self) -> None:
        """The format is a public contract, so a reader can tell what it is holding."""
        assert exchange.to_document([pancakes()], "en-GB").quookly == exchange.FORMAT_VERSION

    def test_recipes_are_carried_whole(self) -> None:
        document = exchange.to_document([pancakes()], "en-GB")
        assert [recipe.title for recipe in document.recipes] == ["Pancakes"]
        assert len(document.recipes[0].lines) == 2
        assert len(document.recipes[0].steps) == 2

    def test_lines_refer_to_ingredients_by_slug(self) -> None:
        """Database ids differ between instances; a slug is the same everywhere."""
        document = exchange.to_document([pancakes()], "en-GB")
        assert [line.ingredient for line in document.recipes[0].lines] == ["plain-flour", "egg"]

    def test_the_ingredients_used_travel_with_the_recipes(self) -> None:
        """Otherwise an import into a fresh instance resolves nothing."""
        document = exchange.to_document([pancakes()], "en-GB")
        assert {entry.slug for entry in document.ingredients} == {"plain-flour", "egg"}

    def test_an_ingredient_carries_what_is_needed_to_recreate_it(self) -> None:
        document = exchange.to_document([pancakes()], "en-GB")
        flour = next(e for e in document.ingredients if e.slug == "plain-flour")
        assert flour.kind is IngredientKind.POWDER
        assert flour.density == Decimal("0.53")
        assert flour.names == ["plain flour"]

    def test_an_ingredient_used_twice_is_listed_once(self) -> None:
        document = exchange.to_document([pancakes(), pancakes()], "en-GB")
        assert len(document.ingredients) == 2

    def test_quantities_are_carried_as_written_not_as_rendered(self) -> None:
        """Export is the recipe, not one cook's view of it."""
        document = exchange.to_document([pancakes()], "en-GB")
        flour = document.recipes[0].lines[0]
        assert flour.magnitude == Decimal("225")
        assert flour.unit == "g"

    def test_identity_and_ownership_are_left_behind(self) -> None:
        """Ids and accounts belong to the instance that held them, not to the recipe."""
        serialised = exchange.to_document([pancakes()], "en-GB").model_dump_json()
        assert '"cook_id"' not in serialised
        assert '"id"' not in serialised


class TestImporting:
    def test_a_document_this_version_understands_is_read(self) -> None:
        document = exchange.to_document([pancakes()], "en-GB")
        read = exchange.from_document(document.model_dump(mode="json"))
        assert [recipe.title for recipe in read.recipes] == ["Pancakes"]

    def test_a_document_from_the_future_is_refused(self) -> None:
        """Reading a format we do not know would silently drop whatever is new in it."""
        document = exchange.to_document([pancakes()], "en-GB").model_dump(mode="json")
        document["quookly"] = exchange.FORMAT_VERSION + 1
        with pytest.raises(UnsupportedDocument):
            exchange.from_document(document)

    def test_something_that_is_not_a_document_is_refused(self) -> None:
        with pytest.raises(UnsupportedDocument):
            exchange.from_document({"recipes": []})

    def test_an_unknown_unit_is_refused_rather_than_guessed(self) -> None:
        document = exchange.to_document([pancakes()], "en-GB").model_dump(mode="json")
        document["recipes"][0]["lines"][0]["unit"] = "handfuls"
        with pytest.raises(UnsupportedDocument):
            exchange.from_document(document)


class TestRoundTrip:
    def test_a_recipe_survives_export_and_import_unchanged(self) -> None:
        """FR-11: lossless. This is the whole promise, so it is asserted field by field."""
        document = exchange.to_document([pancakes()], "en-GB")
        read = exchange.from_document(document.model_dump(mode="json")).recipes[0]
        original = pancakes()

        assert read.title == original.title
        assert read.summary == original.summary
        assert read.yield_quantity == original.yield_quantity
        assert read.provenance is original.provenance
        assert [line.slug for line in read.lines] == [
            line.ingredient.slug for line in original.lines
        ]
        assert [line.quantity for line in read.lines] == [
            line.quantity for line in original.lines
        ]
        assert [line.preparation for line in read.lines] == ["sifted", None]
        assert [line.optional for line in read.lines] == [False, True]
        assert [(s.instruction, s.duration_seconds) for s in read.steps] == [
            ("Whisk.", None),
            ("Rest.", 1800),
        ]

    def test_the_ingredients_survive_too(self) -> None:
        document = exchange.to_document([pancakes()], "en-GB")
        read = exchange.from_document(document.model_dump(mode="json"))
        flour = next(e for e in read.ingredients if e.slug == "plain-flour")
        assert flour.density == Decimal("0.53")
        assert flour.kind is IngredientKind.POWDER

    def test_a_second_round_trip_does_not_drift(self) -> None:
        """Repeated moves between instances must not erode a recipe.

        Everything but the export timestamp, which is about the act of exporting rather
        than about the content.
        """

        def content(document: ExchangeDocument) -> dict[str, Any]:
            return document.model_dump(mode="json", exclude={"exported_at"})

        first = exchange.to_document([pancakes()], "en-GB")
        second = exchange.to_document([pancakes()], "en-GB")
        assert content(first) == content(second)
