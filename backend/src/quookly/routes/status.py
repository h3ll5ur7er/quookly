from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class StatusResponse(BaseModel):
    status: Literal["ok", "error"]


@router.get("/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    return StatusResponse(status="ok")
