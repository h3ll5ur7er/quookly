"""Serving the pictures this instance keeps."""

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from quookly.managers import media as media_manager
from quookly.routes.dependencies import CurrentCook

router = APIRouter()

#: A stored picture never changes: its name is a UUID minted when it was written, so a new
#: picture is a new name. That makes it safe to cache for a long time, which matters on a
#: phone reading an Academy page in a kitchen.
CACHE_FOR_A_YEAR = "public, max-age=31536000, immutable"


@router.get("/media/{media_id}")
async def read_media(media_id: str, cook: CurrentCook) -> Response:
    """The bytes of a stored picture.

    Signed in, like everything else here: this is a household's instance, and what it holds
    is not offered to whoever asks.
    """
    found = await media_manager.read(media_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such picture.")
    return Response(
        content=found,
        media_type="image/webp",
        headers={"Cache-Control": CACHE_FOR_A_YEAR},
    )
