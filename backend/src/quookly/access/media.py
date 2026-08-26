"""Access to the pictures this instance keeps.

The first thing here that lives outside the database. Three decisions shape it:

**Files sit in a directory beside the database.** A database holding megabytes of
photographs is one that is slow to copy and awkward to look inside. The cost is that
backing an instance up is copying two things rather than one, which the installation
documentation has to say.

**An upload is re-encoded, never stored as it arrived.** One format out means a page
renders the same picture for everybody and there is one path to go wrong. It also drops
what the camera recorded — a photograph carries the place it was taken, and somebody
uploading a picture of their chopping board is not offering their address. And it brings a
twelve-megapixel phone photograph down to something a page can reasonably send.

**A file is named by a UUID.** The database refers to that and nothing else. A name derived
from the upload would carry whatever the phone called it, which is somebody's filename and
not this application's business — and a name that came from outside is a name that can try
to be a path.

**Nothing here deletes on its own.** Removing a picture from a page leaves the file, by
decision: a reference that changes is not evidence that nobody wants the bytes, and a sweep
that guessed would eventually guess wrong. Collecting what is no longer referred to is a
job for a CLI command, and the CLI is a later stage.
"""

import re
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from quookly.contracts.errors import UnreadableImage
from quookly.utilities.configuration import get_settings

#: The longest side a stored picture keeps. A photograph of a knife cut does not need to be
#: four thousand pixels wide, and a page on a phone will never show it at that size.
LONGEST_SIDE = 1600

#: How hard to compress. High enough that a technique photograph still reads, low enough
#: that a page is not a megabyte.
QUALITY = 82

#: What a media id may be. Checked before it is joined onto a directory, because this
#: arrives from a URL: anything that is not a plain hex name is refused rather than resolved.
_MEDIA_ID = re.compile(r"^[0-9a-f]{32}$")


def _directory() -> Path:
    return Path(get_settings().media_dir)


def _path_for(media_id: str) -> Path | None:
    """Where a picture lives, or nothing if that is not a name we could have written."""
    if not _MEDIA_ID.match(media_id):
        return None
    return _directory() / f"{media_id}.webp"


async def store_image(data: bytes) -> str:
    """Re-encode an upload and keep it. Returns the id the database should refer to.

    Raises `UnreadableImage` for anything Pillow cannot open, which is the honest outcome
    for a file that is not a picture — better than storing bytes nobody can render and
    finding out when a page is drawn.
    """
    try:
        opened = Image.open(BytesIO(data))
        opened.load()
    except (UnidentifiedImageError, OSError, ValueError) as unreadable:
        raise UnreadableImage("that upload is not a picture this instance can read") from unreadable

    # Whatever came in, a page shows one kind of thing. `RGB` because a palette or an alpha
    # channel would survive the resize and then surprise the encoder.
    image: Image.Image = opened.convert("RGB") if opened.mode != "RGB" else opened

    # Only ever down. Enlarging would invent detail nobody photographed.
    if max(image.size) > LONGEST_SIDE:
        image.thumbnail((LONGEST_SIDE, LONGEST_SIDE), Image.Resampling.LANCZOS)

    media_id = uuid4().hex
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    # Saved from a fresh image rather than the opened one, so nothing the camera recorded
    # rides along: `Image.save` carries `info` across, and `info` is where EXIF lives.
    kept = Image.new("RGB", image.size)
    kept.paste(image)
    kept.save(directory / f"{media_id}.webp", format="WEBP", quality=QUALITY, method=4)
    return media_id


async def fetch_image(media_id: str) -> bytes | None:
    """The bytes of a stored picture, or nothing where there is no such picture."""
    path = _path_for(media_id)
    if path is None or not path.is_file():
        return None
    return path.read_bytes()


async def delete_image(media_id: str) -> None:
    """Remove a stored picture. Deleting one that is already gone is not an error.

    Called by somebody who asked, never by a reference changing (see the module docstring).
    """
    path = _path_for(media_id)
    if path is not None:
        path.unlink(missing_ok=True)
