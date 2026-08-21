"""What a new cook still has to set up (V16, UC-10.2, UC-10.3).

`OnboardingEngine` is a rule engine: a pure function of the profile, with no I/O. Nothing
stores "step 2 of 4 complete" (ADR-014), so this file is a table of profile states and the
guidance each one produces.

The rule the whole design rests on: **declared none is not the same as not answered**
(FR-15). A household where genuinely nobody has a restriction must be recordable as
answered, or onboarding nags a cook forever about a question they have already settled.
"""

import pytest

from quookly.contracts.onboarding import ProfileState, SetupProgress, SetupStep
from quookly.engines import onboarding


def state(
    *,
    eaters: int = 0,
    constrained: int = 0,
    chosen_units: int = 0,
    locale_chosen: bool = False,
    declared: frozenset[SetupStep] = frozenset(),
) -> ProfileState:
    return ProfileState(
        eaters=eaters,
        eaters_with_constraints=constrained,
        chosen_units=chosen_units,
        locale_chosen=locale_chosen,
        declared=declared,
    )


def done(progress: SetupProgress) -> set[SetupStep]:
    return {status.step for status in progress.steps if status.done}


class TestAFreshProfile:
    def test_nothing_is_done(self) -> None:
        assert done(onboarding.assess(state())) == set()

    def test_it_is_not_complete(self) -> None:
        assert onboarding.assess(state()).complete is False

    def test_the_first_thing_asked_for_is_the_household(self) -> None:
        """Everything else is a preference. Who is eating is what the product is about."""
        assert onboarding.assess(state()).next_step is SetupStep.HOUSEHOLD

    def test_every_step_is_reported_so_a_cook_sees_the_whole_road(self) -> None:
        """UC-10.3: what is still missing, not just what is next."""
        assert [status.step for status in onboarding.assess(state()).steps] == list(SetupStep)


class TestSatisfiedByData:
    def test_recording_somebody_settles_the_household(self) -> None:
        assert SetupStep.HOUSEHOLD in done(onboarding.assess(state(eaters=1)))

    def test_a_recorded_constraint_settles_the_constraints_step(self) -> None:
        assert SetupStep.CONSTRAINTS in done(onboarding.assess(state(eaters=1, constrained=1)))

    def test_choosing_a_unit_settles_the_units_step(self) -> None:
        assert SetupStep.UNITS in done(onboarding.assess(state(chosen_units=1)))

    def test_choosing_a_language_settles_the_locale_step(self) -> None:
        assert SetupStep.LOCALE in done(onboarding.assess(state(locale_chosen=True)))

    def test_a_household_with_nobody_restricted_is_still_asked(self) -> None:
        """The distinction ADR-014 exists for: silence here could mean either thing."""
        assert SetupStep.CONSTRAINTS not in done(onboarding.assess(state(eaters=2)))


class TestDeclaringNone:
    def test_declaring_no_constraints_settles_the_step(self) -> None:
        progress = onboarding.assess(state(eaters=2, declared=frozenset({SetupStep.CONSTRAINTS})))
        assert SetupStep.CONSTRAINTS in done(progress)

    def test_a_declared_step_says_it_was_declared(self) -> None:
        """So an interface can show "you said nobody has any" rather than a bare tick."""
        progress = onboarding.assess(state(eaters=2, declared=frozenset({SetupStep.CONSTRAINTS})))
        status = next(s for s in progress.steps if s.step is SetupStep.CONSTRAINTS)
        assert status.declared is True

    def test_a_step_settled_by_data_is_not_marked_declared(self) -> None:
        progress = onboarding.assess(state(eaters=1, constrained=1))
        status = next(s for s in progress.steps if s.step is SetupStep.CONSTRAINTS)
        assert status.declared is False

    def test_declaring_every_step_completes_setup(self) -> None:
        assert onboarding.assess(state(declared=frozenset(SetupStep))).complete is True

    def test_a_cook_who_cooks_for_nobody_in_particular_may_say_so(self) -> None:
        progress = onboarding.assess(state(declared=frozenset({SetupStep.HOUSEHOLD})))
        assert SetupStep.HOUSEHOLD in done(progress)
        assert progress.next_step is SetupStep.CONSTRAINTS


class TestItStaysTrue:
    def test_removing_everybody_reopens_the_household(self) -> None:
        """ADR-014's whole rationale: a stored flag would still say complete."""
        assert SetupStep.HOUSEHOLD not in done(onboarding.assess(state(eaters=0)))

    def test_but_not_when_the_cook_answered_the_question(self) -> None:
        """They were asked and they answered; emptying the list does not unask it."""
        progress = onboarding.assess(state(eaters=0, declared=frozenset({SetupStep.HOUSEHOLD})))
        assert SetupStep.HOUSEHOLD in done(progress)

    def test_removing_the_only_constraint_reopens_the_constraints_step(self) -> None:
        assert SetupStep.CONSTRAINTS not in done(onboarding.assess(state(eaters=2)))


class TestWhatComesNext:
    def test_it_is_the_first_thing_outstanding(self) -> None:
        progress = onboarding.assess(state(eaters=1, constrained=1))
        assert progress.next_step is SetupStep.UNITS

    def test_there_is_nothing_next_once_everything_is_settled(self) -> None:
        progress = onboarding.assess(
            state(eaters=1, constrained=1, chosen_units=1, locale_chosen=True)
        )
        assert progress.complete is True
        assert progress.next_step is None

    def test_a_later_step_being_done_does_not_skip_an_earlier_one(self) -> None:
        """A cook who set their units first is still asked who they cook for."""
        progress = onboarding.assess(state(chosen_units=1, locale_chosen=True))
        assert progress.next_step is SetupStep.HOUSEHOLD
        assert progress.complete is False


class TestItIsARuleEngine:
    def test_it_reads_nothing(self) -> None:
        """ADR-006's sibling rule: an engine that fetches cannot be tested as a table."""
        import inspect

        source = inspect.getsource(onboarding)
        for forbidden in ("await ", "async def", "session(", "requests", "open("):
            assert forbidden not in source, f"{forbidden!r} in a rule engine"

    @pytest.mark.parametrize("eaters", [0, 1, 5])
    @pytest.mark.parametrize("constrained", [0, 1])
    @pytest.mark.parametrize("units", [0, 3])
    def test_the_same_profile_always_gives_the_same_answer(
        self, eaters: int, constrained: int, units: int
    ) -> None:
        profile = state(eaters=eaters, constrained=constrained, chosen_units=units)
        assert onboarding.assess(profile) == onboarding.assess(profile)
