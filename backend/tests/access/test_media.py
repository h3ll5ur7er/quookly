"""Storing the pictures an Academy page shows (Phase 7, unit 4b).

The first thing this application keeps outside its database. Three decisions shape it, and
they were Emanuel's: files live in a directory beside the database, an upload is re-encoded
rather than stored as it arrived, and a file is named by a UUID that the database refers to.
"""

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pytest import MonkeyPatch

from quookly.access import media
from quookly.contracts.errors import UnreadableImage
from quookly.utilities.configuration import get_settings


@pytest.fixture(autouse=True)
def somewhere_to_put_them(monkeypatch: MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("QUOOKLY_MEDIA_DIR", str(tmp_path / "media"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def photograph(size: tuple[int, int] = (800, 600), fmt: str = "JPEG") -> bytes:
    held = BytesIO()
    Image.new("RGB", size, (120, 140, 130)).save(held, format=fmt)
    return held.getvalue()


class TestStoring:
    async def test_a_picture_can_be_stored_and_read_back(self) -> None:
        media_id = await media.store_image(photograph())
        assert await media.fetch_image(media_id) is not None

    async def test_it_is_named_by_a_uuid(self) -> None:
        """What the database refers to. A name derived from the upload would carry whatever
        the phone called it, which is somebody's filename and not our business."""
        media_id = await media.store_image(photograph())
        assert len(media_id) == 32
        assert media_id.isalnum()

    async def test_two_uploads_of_the_same_picture_are_two_files(self) -> None:
        first = await media.store_image(photograph())
        second = await media.store_image(photograph())
        assert first != second

    async def test_it_lands_in_the_configured_directory(self, tmp_path: Path) -> None:
        media_id = await media.store_image(photograph())
        assert (tmp_path / "media" / f"{media_id}.webp").exists()

    async def test_the_directory_is_made_if_it_is_not_there(self, tmp_path: Path) -> None:
        """A fresh instance has never stored a picture, and should not have to be told to
        make a folder before it can."""
        assert not (tmp_path / "media").exists()
        await media.store_image(photograph())
        assert (tmp_path / "media").is_dir()


class TestReEncoding:
    async def test_what_comes_back_is_a_webp(self) -> None:
        """One format out, whatever went in: a page renders the same picture for everybody,
        and one path is one thing that can go wrong."""
        media_id = await media.store_image(photograph(fmt="PNG"))
        stored = await media.fetch_image(media_id)
        assert stored is not None
        assert Image.open(BytesIO(stored)).format == "WEBP"

    async def test_a_png_is_accepted(self) -> None:
        assert await media.store_image(photograph(fmt="PNG"))

    async def test_a_photograph_is_brought_down_to_a_sensible_size(self) -> None:
        """A phone photograph is twelve megapixels and a picture of a knife cut is not."""
        media_id = await media.store_image(photograph(size=(4032, 3024)))
        stored = await media.fetch_image(media_id)
        assert stored is not None
        assert max(Image.open(BytesIO(stored)).size) <= media.LONGEST_SIDE

    async def test_a_small_picture_is_left_at_its_size(self) -> None:
        """Enlarging would invent detail nobody photographed."""
        media_id = await media.store_image(photograph(size=(320, 240)))
        stored = await media.fetch_image(media_id)
        assert stored is not None
        assert Image.open(BytesIO(stored)).size == (320, 240)

    async def test_what_the_camera_recorded_does_not_come_with_it(self) -> None:
        """Re-encoding drops the metadata, which is where a photograph keeps the place it
        was taken. Somebody uploading a picture of their chopping board is not offering
        their address."""
        held = BytesIO()
        image = Image.new("RGB", (400, 300), (10, 20, 30))
        exif = image.getexif()
        exif[0x9003] = "2026:08:26 12:00:00"
        image.save(held, format="JPEG", exif=exif)

        media_id = await media.store_image(held.getvalue())
        stored = await media.fetch_image(media_id)
        assert stored is not None
        assert not Image.open(BytesIO(stored)).getexif()

    async def test_something_that_is_not_a_picture_is_refused(self) -> None:
        with pytest.raises(UnreadableImage):
            await media.store_image(b"this is not a photograph")

    async def test_an_empty_upload_is_refused(self) -> None:
        with pytest.raises(UnreadableImage):
            await media.store_image(b"")


class TestReading:
    async def test_a_picture_nobody_stored_is_absent(self) -> None:
        assert await media.fetch_image("0" * 32) is None

    async def test_a_name_that_is_not_a_uuid_is_absent_rather_than_a_path(self) -> None:
        """The id reaches this from a URL. Anything that is not a plain hex name is refused
        before it can be joined onto a directory."""
        for wrong in ("../../etc/passwd", "..", "a/b", "", "not-hex-at-all"):
            assert await media.fetch_image(wrong) is None


class TestRemoving:
    async def test_a_picture_can_be_deleted(self) -> None:
        media_id = await media.store_image(photograph())
        await media.delete_image(media_id)
        assert await media.fetch_image(media_id) is None

    async def test_deleting_one_that_is_gone_is_not_an_error(self) -> None:
        """Nothing here deletes on its own, so the only caller is somebody who asked twice."""
        await media.delete_image("0" * 32)
