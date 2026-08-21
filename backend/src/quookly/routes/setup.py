"""Guided setup endpoints (UC-10.2, UC-10.3)."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator

from quookly.contracts.onboarding import SUPPORTED_LOCALES, SetupProgressView, SetupStep
from quookly.managers import onboarding as onboarding_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()


class LocaleChoice(BaseModel):
    """The language a cook reads in."""

    model_config = ConfigDict(frozen=True)

    locale: str

    @field_validator("locale")
    @classmethod
    def one_this_instance_speaks(cls, locale: str) -> str:
        """Refused rather than stored: an unshipped locale is an interface nobody wrote.

        `$localize` would fall back to English and the cook would be left with a setting
        that appears to have taken effect and has not.
        """
        if locale not in SUPPORTED_LOCALES:
            raise ValueError(f"unsupported locale: {locale}")
        return locale


@router.get("/setup", response_model=SetupProgressView)
async def get_setup(cook: CurrentCook) -> SetupProgressView:
    """What is still missing from this cook's setup, and what comes next."""
    return await onboarding_manager.assess(cook.cook_id)


@router.post("/setup/declarations/{step}", response_model=SetupProgressView)
async def declare_step(step: SetupStep, cook: CurrentCook) -> SetupProgressView:
    """Answer a setup question outright — "nobody has any", "the defaults are fine".

    The one stored part of setup. Without it a household where nobody has a dietary
    restriction is indistinguishable from one nobody has been asked about, and setup
    would go on asking forever (FR-15).
    """
    return await onboarding_manager.declare(cook.cook_id, step)


@router.put("/setup/locale", response_model=SetupProgressView)
async def choose_locale(choice: LocaleChoice, cook: CurrentCook) -> SetupProgressView:
    """Remember the language this cook reads in, wherever they sign in from."""
    if choice.locale not in SUPPORTED_LOCALES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"This instance does not speak {choice.locale}.",
        )
    return await onboarding_manager.choose_locale(cook.cook_id, choice.locale)
