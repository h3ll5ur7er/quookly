"""Endpoints about the instance itself, for whoever runs it (UC-8.2)."""

from fastapi import APIRouter

from quookly.contracts.inference import InferenceStatusView
from quookly.managers import instance as instance_manager
from quookly.routes.dependencies import CurrentAdmin

router = APIRouter()


@router.get("/instance/inference", response_model=InferenceStatusView)
async def get_inference_status(admin: CurrentAdmin) -> InferenceStatusView:
    """What model this instance will ask, and whether it is answering.

    Administrators only. It names an address on the operator's network and says whether a
    credential is set — the first of those is a map of what the server can see, and
    neither is an ordinary cook's business.
    """
    return await instance_manager.inference_status()
