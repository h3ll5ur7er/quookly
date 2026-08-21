"""Guiding a new cook from an empty profile to a ready kitchen (UC-10.2, UC-10.3).

The sequence, and nothing else: gather what the profile holds, hand it to
`OnboardingEngine`, report what it says. The judgement is the engine's, which is what
keeps "what is still missing" answerable as a table of cases rather than a walk through
four services.

Nothing here stores progress. A cook who leaves halfway and returns a month later is
asked exactly what is still outstanding, because that is derived rather than remembered
(ADR-014).
"""

from quookly.access import cook as cook_access
from quookly.access import eater as eater_access
from quookly.access import preferences as preference_access
from quookly.access import setup as setup_access
from quookly.contracts.onboarding import (
    ProfileState,
    SetupProgress,
    SetupProgressView,
    SetupStep,
    StepStatusView,
)
from quookly.engines import onboarding


def _view(progress: SetupProgress) -> SetupProgressView:
    return SetupProgressView(
        steps=[
            StepStatusView(step=status.step, done=status.done, declared=status.declared)
            for status in progress.steps
        ],
        next_step=progress.next_step,
        complete=progress.complete,
    )


async def _gather(cook_id: int) -> ProfileState:
    household = await eater_access.list_for_cook(cook_id)
    account = await cook_access.fetch(cook_id)
    return ProfileState(
        eaters=len(household),
        eaters_with_constraints=sum(1 for eater in household if eater.constraints),
        chosen_units=len(await preference_access.chosen_kinds(cook_id)),
        locale_chosen=account is not None and account.locale is not None,
        declared=await setup_access.declarations_for(cook_id),
    )


async def assess(cook_id: int) -> SetupProgressView:
    """What this cook has settled, what is outstanding, and what to do next."""
    return _view(onboarding.assess(await _gather(cook_id)))


async def declare(cook_id: int, step: SetupStep) -> SetupProgressView:
    """Record that a question was answered outright — "nobody has any", "defaults are fine".

    Returns the whole progress rather than an acknowledgement, so the screen that asked
    can show what is left without a second request.
    """
    await setup_access.declare(cook_id, step)
    return await assess(cook_id)


async def choose_locale(cook_id: int, locale: str) -> SetupProgressView:
    """Remember the language this cook reads in, and settle that step with it."""
    await cook_access.choose_locale(cook_id, locale)
    return await assess(cook_id)
