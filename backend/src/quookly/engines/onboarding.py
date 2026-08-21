"""What a new cook still has to set up (V16, UC-10.2, UC-10.3).

A pure function of the profile. It stores nothing and reads nothing: the answer is
derived every time it is asked for, which is what makes it true (ADR-014). A cook who
deletes every eater is told their household is unset again, and "resume later" needs no
machinery at all because there is no session to resume.

The one thing derivation cannot do is tell *declared none* from *not answered* — a
household where nobody has a dietary restriction looks identical to one nobody has been
asked about. That distinction arrives as `declared`, and it is the only stored part of
setup (FR-15).
"""

from quookly.contracts.onboarding import ProfileState, SetupProgress, SetupStep, StepStatus


def _settled_by_data(step: SetupStep, profile: ProfileState) -> bool:
    """Whether the profile already answers this question without anybody saying so.

    Each of these is a count being non-zero rather than a flag, which is why the answer
    can go back to *unsettled* when a cook removes what satisfied it.
    """
    match step:
        case SetupStep.HOUSEHOLD:
            return profile.eaters > 0
        case SetupStep.CONSTRAINTS:
            return profile.eaters_with_constraints > 0
        case SetupStep.UNITS:
            return profile.chosen_units > 0
        case SetupStep.LOCALE:
            return profile.locale_chosen


def assess(profile: ProfileState) -> SetupProgress:
    """What is settled, what is outstanding, and what to do next.

    Every step is reported rather than only the next one: UC-10.3 is about seeing the
    whole road, and a wizard that shows one door at a time cannot say how far there is
    left to go.
    """
    steps = [
        StepStatus(
            step=step,
            done=_settled_by_data(step, profile) or step in profile.declared,
            # Declared only counts as *declared* when nothing in the profile settled it
            # anyway: a cook with a recorded allergy did not merely say they had none.
            declared=step in profile.declared and not _settled_by_data(step, profile),
        )
        for step in SetupStep
    ]
    outstanding = [status.step for status in steps if not status.done]
    return SetupProgress(
        steps=steps,
        # The first thing outstanding, in step order. A cook who set their units first is
        # still asked who they cook for rather than being skipped past it.
        next_step=outstanding[0] if outstanding else None,
        complete=not outstanding,
    )
