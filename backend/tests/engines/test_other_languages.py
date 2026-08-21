"""Reading a recipe that is not in English (V2, V14, FR-10).

Quookly ships in en-GB, de-CH and fr-CH, so a Swiss cook pasting a link to a Swiss recipe
site is the ordinary case rather than an edge one. The strings below come from
swissmilk.ch, which writes its quantities the way German-speaking Switzerland does.

Three things differ and all three matter. The decimal separator is a comma. The spoon
measures are abbreviations of German words. And the yield counts Portionen.
"""

from decimal import Decimal

import pytest

from quookly.contracts.interpretation import InterpretedLine
from quookly.contracts.measure import Unit
from quookly.engines import interpretation


def read(text: str) -> InterpretedLine:
    line = interpretation.read_ingredient(text)
    assert line is not None, f"{text!r} read as nothing"
    return line


class TestTheCommaIsADecimalPoint:
    def test_a_swiss_decilitre_is_not_torn_in_half(self) -> None:
        """ "2,5 dl Milch" was being split on the comma into "2" and a note reading
        "5 dl Milch" — a quantity destroyed by a rule meant for "butter, softened"."""
        line = read("2,5 dl Milch")
        assert line.magnitude == Decimal("2.5")
        assert line.unit is Unit.DECILITRE
        assert line.ingredient == "Milch"
        assert line.preparation is None

    def test_a_note_after_a_real_comma_still_separates(self) -> None:
        line = read("225g Butter, weich")
        assert line.ingredient == "Butter"
        assert line.preparation == "weich"

    def test_a_decimal_comma_inside_a_line_with_a_note_survives_both(self) -> None:
        line = read("2,5 dl Rahm, geschlagen")
        assert line.magnitude == Decimal("2.5")
        assert line.preparation == "geschlagen"


class TestGermanMeasures:
    @pytest.mark.parametrize(
        ("written", "magnitude", "unit", "ingredient"),
        [
            ("150 g Mehl", "150", Unit.GRAM, "Mehl"),
            ("2 TL Backpulver", "2", Unit.TEASPOON_METRIC, "Backpulver"),
            ("3 EL Zucker", "3", Unit.TABLESPOON_METRIC, "Zucker"),
            ("¼ TL Salz", "0.25", Unit.TEASPOON_METRIC, "Salz"),
            ("1 Teelöffel Vanille", "1", Unit.TEASPOON_METRIC, "Vanille"),
            ("2 Esslöffel Öl", "2", Unit.TABLESPOON_METRIC, "Öl"),
            ("500 Gramm Kartoffeln", "500", Unit.GRAM, "Kartoffeln"),
            ("1 Liter Milch", "1", Unit.LITRE, "Milch"),
            ("2 Stück Eier", "2", Unit.PIECE, "Eier"),
        ],
    )
    def test_it_reads_what_a_swiss_page_writes(
        self, written: str, magnitude: str, unit: Unit, ingredient: str
    ) -> None:
        line = read(written)
        assert line.magnitude == Decimal(magnitude)
        assert line.unit is unit
        assert line.ingredient == ingredient

    def test_a_bare_count_still_counts(self) -> None:
        line = read("3 Eigelb")
        assert line.magnitude == Decimal("3")
        assert line.unit is Unit.PIECE
        assert line.ingredient == "Eigelb"


class TestFrenchMeasures:
    @pytest.mark.parametrize(
        ("written", "magnitude", "unit", "ingredient"),
        [
            ("200 g de farine", "200", Unit.GRAM, "farine"),
            ("1 cuillère à soupe de sucre", "1", Unit.TABLESPOON_METRIC, "sucre"),
            ("2 cuillères à café de sel", "2", Unit.TEASPOON_METRIC, "sel"),
            ("3 dl de lait", "3", Unit.DECILITRE, "lait"),
        ],
    )
    def test_it_reads_what_a_french_page_writes(
        self, written: str, magnitude: str, unit: Unit, ingredient: str
    ) -> None:
        line = read(written)
        assert line.magnitude == Decimal(magnitude)
        assert line.unit is unit
        assert line.ingredient == ingredient


class TestVagueMeasuresInAnyLanguage:
    @pytest.mark.parametrize(
        ("written", "ingredient"),
        [
            ("1 Prise Salz", "Salz"),
            ("2 Prisen Muskatnuss", "Muskatnuss"),
            ("1 Msp. Zimt", "Zimt"),
            ("1 Bund Petersilie", "Petersilie"),
            ("1 pincée de sel", "sel"),
            ("2 pinches salt", "salt"),
        ],
    )
    def test_a_measure_that_is_a_judgement_gets_no_number(
        self, written: str, ingredient: str
    ) -> None:
        """A pinch is a judgement whatever language it is judged in. Turning it into
        grams would be a number a cook cannot see is wrong."""
        line = read(written)
        assert line.ingredient == ingredient
        assert line.magnitude is None
        assert line.unit is None

    def test_the_amount_is_kept_as_the_note(self) -> None:
        assert read("1 Prise Salz").preparation == "1 Prise"


class TestYieldsInOtherLanguages:
    @pytest.mark.parametrize(
        ("written", "magnitude", "unit"),
        [
            ("4 Portionen", "4", Unit.SERVING),
            ("Für 4 Personen", "4", Unit.SERVING),
            ("2 Portionen", "2", Unit.SERVING),
            ("4 personnes", "4", Unit.SERVING),
            ("6 parts", "6", Unit.SERVING),
            ("12 Stück", "12", Unit.PIECE),
        ],
    )
    def test_it_reads_how_many_it_feeds(self, written: str, magnitude: str, unit: Unit) -> None:
        found, read_unit = interpretation.read_yield(written)
        assert found == Decimal(magnitude)
        assert read_unit is unit
