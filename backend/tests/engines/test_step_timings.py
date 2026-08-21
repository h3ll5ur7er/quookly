"""Reading a time and a temperature out of a step's own words (V2, V15).

A pure reader, for the same reason the ingredient reader is one: the model decides what a
step *says*, and this decides what a number in it *means*. Without it an imported recipe
has no timers at all — the one thing a cook standing at a hob reaches for.

The case that has to be right is the one where there is no duration. "Chop 5 onions" has a
number in it, and a timer for five seconds would be worse than no timer.
"""

import pytest

from quookly.engines import interpretation


class TestHowLong:
    @pytest.mark.parametrize(
        ("written", "seconds"),
        [
            ("Bake for 25 minutes.", 1500),
            ("Bake 25 min.", 1500),
            ("Simmer for 1 hour.", 3600),
            ("Rest for 90 seconds.", 90),
            ("Fry for 2 mins.", 120),
            # Decimals, because a site will write one.
            ("Prove for 1.5 hours.", 5400),
        ],
    )
    def test_a_duration_in_the_words(self, written: str, seconds: int) -> None:
        assert interpretation.read_step_timing(written)[0] == seconds

    def test_a_range_takes_the_lower_end(self) -> None:
        """A timer that goes off at 25 sends a cook to look at the oven. One that goes off
        at 30 sends them to look at something already burnt."""
        assert interpretation.read_step_timing("Bake for 25-30 minutes.")[0] == 1500

    def test_an_en_dash_is_a_range_too(self) -> None:
        assert interpretation.read_step_timing("Bake for 25–30 minutes.")[0] == 1500

    @pytest.mark.parametrize(
        "written",
        [
            "Cook for about 2 to 3 minutes.",
            "Cook for 2 or 3 minutes.",
            "2 bis 3 Minuten backen.",
        ],
    )
    def test_a_range_written_in_words_is_still_a_range(self, written: str) -> None:
        """Without this the pattern skips the lower end and reads the upper one, which is
        the direction that burns things."""
        assert interpretation.read_step_timing(written)[0] == 120

    def test_hours_and_minutes_together(self) -> None:
        assert interpretation.read_step_timing("Simmer for 1 hour 30 minutes.")[0] == 5400

    def test_the_first_duration_is_the_step_s_own(self) -> None:
        """After splitting there is normally one. Where two survive, the sentence leads
        with the one it is about."""
        assert interpretation.read_step_timing("Rest 30 minutes, then bake 25 minutes.")[0] == 1800

    def test_a_number_that_is_not_a_duration_is_not_one(self) -> None:
        assert interpretation.read_step_timing("Chop 5 onions.") == (None, None)

    def test_a_quantity_is_not_a_duration(self) -> None:
        assert interpretation.read_step_timing("Add 200 g of flour.")[0] is None

    def test_a_duration_in_words_is_left_absent(self) -> None:
        """ "Half an hour" is prose. Absent rather than guessed, as everywhere else."""
        assert interpretation.read_step_timing("Rest for half an hour.")[0] is None

    def test_german(self) -> None:
        """A Swiss cook's recipes are as likely to be in German as in English."""
        assert interpretation.read_step_timing("20 Minuten backen.")[0] == 1200
        assert interpretation.read_step_timing("1 Stunde ruhen lassen.")[0] == 3600

    def test_french(self) -> None:
        assert interpretation.read_step_timing("Cuire 25 minutes.")[0] == 1500
        assert interpretation.read_step_timing("Laisser reposer 1 heure.")[0] == 3600


class TestHowHot:
    @pytest.mark.parametrize(
        ("written", "celsius"),
        [
            ("Bake at 180C.", 180),
            ("Bake at 180 °C.", 180),
            ("Heat the oven to 200°C.", 200),
            ("Backofen auf 180 Grad vorheizen.", 180),
        ],
    )
    def test_a_temperature_in_the_words(self, written: str, celsius: int) -> None:
        assert interpretation.read_step_timing(written)[1] == celsius

    def test_fahrenheit_is_converted(self) -> None:
        """A cook with a European oven cannot act on 350 °F, and every temperature in this
        system is Celsius."""
        assert interpretation.read_step_timing("Bake at 350°F.")[1] == 177

    def test_a_gas_mark_is_left_absent(self) -> None:
        """Gas marks do not map to a number without a table, and a wrong oven temperature
        is a ruined dinner."""
        assert interpretation.read_step_timing("Bake at gas mark 4.")[1] is None

    def test_a_quantity_is_not_a_temperature(self) -> None:
        assert interpretation.read_step_timing("Add 200 g of flour.")[1] is None

    def test_a_cup_is_not_celsius(self) -> None:
        """The letter after the number is the whole of the test, and "1 cup" starts with
        the wrong one being right."""
        assert interpretation.read_step_timing("Add 1 cup of milk.")[1] is None

    def test_both_at_once(self) -> None:
        assert interpretation.read_step_timing("Bake at 180°C for 25 minutes.") == (1500, 180)
