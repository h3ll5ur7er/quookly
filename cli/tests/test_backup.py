"""Copying an instance's data so it can be brought back (UC-8.1, Phase 9).

The two things this has to get right are the two things a naive `tar` of the data
directory gets wrong.

**The database must be snapshotted, not copied.** SQLite writes in pages. Reading the file
while the instance is serving gives a torn copy: some pages from before a transaction and
some from after, which restores as a corrupt database — and which looks like a perfectly
good file until the day somebody needs it. `VACUUM INTO` asks SQLite for a consistent
snapshot of a live database, which is a different operation from copying the bytes.

**The pictures must come too.** They live beside the database rather than inside it, so a
backup of the `.db` alone restores an instance whose Academy pages have holes in them.
"""

import sqlite3
import tarfile
from pathlib import Path

import pytest

from quookly_cli.subcommands.backup import take


@pytest.fixture
def instance(tmp_path: Path) -> Path:
    """A data directory shaped like a running instance's."""
    data = tmp_path / "data"
    (data / "media").mkdir(parents=True)
    (data / "media" / "a-photograph.jpg").write_bytes(b"not really a jpeg")

    held = sqlite3.connect(data / "quookly.db")
    held.execute("create table recipe (id integer primary key, title text)")
    held.execute("insert into recipe (title) values ('Focaccia')")
    held.commit()
    held.close()
    return data


class TestWhatItTakes:
    def test_it_writes_an_archive(self, instance: Path, tmp_path: Path) -> None:
        into = tmp_path / "backup.tar.gz"
        take(instance / "quookly.db", instance / "media", into)
        assert into.exists() and into.stat().st_size > 0

    def test_the_database_is_in_it(self, instance: Path, tmp_path: Path) -> None:
        into = tmp_path / "backup.tar.gz"
        take(instance / "quookly.db", instance / "media", into)
        with tarfile.open(into) as held:
            assert "quookly.db" in held.getnames()

    def test_the_pictures_are_in_it(self, instance: Path, tmp_path: Path) -> None:
        """Two things to copy, not one. A backup of the database alone restores an
        instance whose pages have holes in them."""
        into = tmp_path / "backup.tar.gz"
        take(instance / "quookly.db", instance / "media", into)
        with tarfile.open(into) as held:
            assert "media/a-photograph.jpg" in held.getnames()

    def test_what_comes_out_is_a_working_database(self, instance: Path, tmp_path: Path) -> None:
        into = tmp_path / "backup.tar.gz"
        take(instance / "quookly.db", instance / "media", into)

        out = tmp_path / "restored"
        with tarfile.open(into) as held:
            held.extractall(out, filter="data")
        rows = sqlite3.connect(out / "quookly.db").execute("select title from recipe").fetchall()
        assert rows == [("Focaccia",)]


class TestAgainstALiveInstance:
    def test_committed_data_outside_the_database_file_still_travels(self, tmp_path: Path) -> None:
        """The whole reason this is a command and not a line of `tar` in the manual.

        In WAL mode a committed transaction lives in the `-wal` file until somebody
        checkpoints it. Copying `quookly.db` alone therefore loses data that the
        application has already told a cook was saved — silently, and the copy looks like
        a perfectly good database until the day somebody needs it.

        Quookly does not enable WAL today. This asserts the backup does not *depend* on
        that: a tool that is only correct for one journal mode is a tool that breaks the
        day somebody tunes the database.
        """
        data = tmp_path / "data"
        data.mkdir()
        serving = sqlite3.connect(data / "quookly.db")
        serving.execute("pragma journal_mode=WAL")
        serving.execute("create table recipe (id integer primary key, title text)")
        serving.execute("insert into recipe (title) values ('Focaccia')")
        serving.commit()

        into = tmp_path / "backup.tar.gz"
        take(data / "quookly.db", data / "media", into)
        serving.close()

        out = tmp_path / "restored"
        with tarfile.open(into) as held:
            held.extractall(out, filter="data")
        rows = sqlite3.connect(out / "quookly.db").execute("select title from recipe").fetchall()
        assert rows == [("Focaccia",)]

    def test_it_leaves_the_original_alone(self, instance: Path, tmp_path: Path) -> None:
        """A backup that modifies what it is backing up is not a backup."""
        before = (instance / "quookly.db").read_bytes()
        take(instance / "quookly.db", instance / "media", tmp_path / "backup.tar.gz")
        assert (instance / "quookly.db").read_bytes() == before


class TestWhenItCannot:
    def test_a_database_that_is_not_there_is_said_so(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            take(tmp_path / "missing.db", tmp_path / "media", tmp_path / "out.tar.gz")

    def test_an_instance_with_no_pictures_yet_still_backs_up(self, tmp_path: Path) -> None:
        """A fresh instance has no media directory. That is not an error."""
        held = sqlite3.connect(tmp_path / "quookly.db")
        held.execute("create table recipe (id integer primary key)")
        held.commit()
        held.close()

        into = tmp_path / "backup.tar.gz"
        take(tmp_path / "quookly.db", tmp_path / "media", into)
        with tarfile.open(into) as archive:
            assert "quookly.db" in archive.getnames()


class TestPuttingItBack:
    """Restore, and the one thing it must refuse.

    Restoring over a serving instance is how somebody loses the data they still had, so a
    data directory that already holds a database is refused until it is asked for twice.
    """

    def test_it_refuses_a_directory_that_already_holds_one(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from quookly_cli.subcommands.backup import cli

        source = tmp_path / "data"
        source.mkdir()
        held = sqlite3.connect(source / "quookly.db")
        held.execute("create table recipe (id integer primary key)")
        held.commit()
        held.close()
        archive = tmp_path / "backup.tar.gz"
        take(source / "quookly.db", source / "media", archive)

        refused = CliRunner().invoke(cli, ["restore", str(archive), "--into", str(source)])

        assert refused.exit_code == 1
        assert "already exists" in refused.output

    def test_force_is_what_gets_past_it(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from quookly_cli.subcommands.backup import cli

        source = tmp_path / "data"
        source.mkdir()
        held = sqlite3.connect(source / "quookly.db")
        held.execute("create table recipe (id integer primary key, title text)")
        held.execute("insert into recipe (title) values ('Focaccia')")
        held.commit()
        held.close()
        archive = tmp_path / "backup.tar.gz"
        take(source / "quookly.db", source / "media", archive)

        done = CliRunner().invoke(cli, ["restore", str(archive), "--into", str(source), "--force"])

        assert done.exit_code == 0
        rows = sqlite3.connect(source / "quookly.db").execute("select title from recipe").fetchall()
        assert rows == [("Focaccia",)]

    def test_an_archive_that_is_not_there_is_said_so(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from quookly_cli.subcommands.backup import cli

        missing = CliRunner().invoke(cli, ["restore", str(tmp_path / "nope.tar.gz")])
        assert missing.exit_code == 1
