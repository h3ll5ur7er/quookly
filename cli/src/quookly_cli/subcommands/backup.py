"""Copying an instance's data so it can be brought back (UC-8.1).

Two things live in an instance's data directory and both have to travel: the **database**,
and the **pictures** beside it. A backup of the database alone restores an instance whose
Academy pages have holes in them, which is the trap the compose file's single volume
exists to keep people out of.

**The database is snapshotted, not copied.** This is the reason this is a command rather
than a line of `tar` in the manual. SQLite writes in pages; reading the file while the
instance is serving gives some pages from before a transaction and some from after. That
restores as a corrupt database, and — the part that makes it worth code — it looks like a
perfectly good file until the day somebody needs it. `VACUUM INTO` asks SQLite for a
consistent snapshot of a live database, which is a different operation from copying bytes
and is why the instance does not have to be stopped.

It runs where the data is, not where the API is. Everything else this CLI does goes over
HTTP to an instance; this reads a directory, so it is the one command that has to be run
on the box (or in the container) that holds it.
"""

import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

cli = typer.Typer(no_args_is_help=False)
console = Console()

#: Where an instance keeps its two things, matching `.env.example` and the compose file.
DATABASE = "QUOOKLY_DATABASE_URL"
MEDIA = "QUOOKLY_MEDIA_DIR"
DEFAULT_DATA = Path("/data")


def take(database: Path, media: Path, into: Path) -> Path:
    """Write a consistent copy of one instance's data to `into`. Returns the path.

    The snapshot is taken first and to a temporary file, so that a failure part-way leaves
    no half-written archive where a backup is supposed to be. A backup that might be a
    backup is worse than an obvious absence.
    """
    if not database.exists():
        raise FileNotFoundError(f"No database at {database}")

    into.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        snapshot = Path(scratch) / "quookly.db"
        held = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            # Not a file copy. See the module docstring: this is the whole point.
            held.execute("VACUUM INTO ?", (str(snapshot),))
        finally:
            held.close()

        building = into.with_suffix(into.suffix + ".part")
        with tarfile.open(building, "w:gz") as archive:
            archive.add(snapshot, arcname="quookly.db")
            if media.is_dir():
                archive.add(media, arcname="media")
        building.replace(into)
    return into


def _database_path(url: str | None) -> Path:
    """The file a SQLAlchemy SQLite URL points at.

    Parsed rather than guessed because the URL is what an operator has already configured,
    and asking them to write the path a second time is asking for the two to disagree.
    """
    if not url:
        return DEFAULT_DATA / "quookly.db"
    _, _, tail = url.partition("///")
    return Path("/" + tail.lstrip("/")) if tail else DEFAULT_DATA / "quookly.db"


@cli.command()
def take_backup(
    into: Annotated[
        Path | None,
        typer.Argument(help="Where to write the archive. Defaults to a dated name here."),
    ] = None,
    database: Annotated[
        Path | None, typer.Option(help=f"The database file. Defaults to ${DATABASE}.")
    ] = None,
    media: Annotated[
        Path | None, typer.Option(help=f"The pictures directory. Defaults to ${MEDIA}.")
    ] = None,
) -> None:
    """Copy this instance's database and pictures into one archive.

    Safe to run against a serving instance: the database is snapshotted rather than copied.
    """
    from_db = database or _database_path(os.environ.get(DATABASE))
    from_media = media or Path(os.environ.get(MEDIA) or DEFAULT_DATA / "media")
    target = into or Path(f"quookly-backup-{datetime.now(UTC):%Y%m%d-%H%M%S}.tar.gz")

    try:
        written = take(from_db, from_media, target)
    except FileNotFoundError as missing:
        console.print(f"[red]{missing}[/red]")
        console.print("Set QUOOKLY_DATABASE_URL, or pass --database.")
        raise typer.Exit(code=1) from None

    size = written.stat().st_size / 1_000_000
    console.print(f"[green]Backed up[/green] to {written} ({size:.1f} MB)")
    if not from_media.is_dir():
        console.print(f"[yellow]No pictures directory at {from_media}[/yellow] — none included.")


@cli.command()
def restore(
    archive: Annotated[Path, typer.Argument(help="The archive to restore.")],
    into: Annotated[Path, typer.Option(help="The data directory to restore into.")] = DEFAULT_DATA,
    force: Annotated[
        bool, typer.Option(help="Overwrite a data directory that already holds a database.")
    ] = False,
) -> None:
    """Put a backup back. **Stop the instance first.**

    Refuses a directory that already has a database in it unless told twice. Restoring over
    a serving instance is how somebody loses the data they still had.
    """
    if not archive.exists():
        console.print(f"[red]No archive at {archive}[/red]")
        raise typer.Exit(code=1)

    existing = into / "quookly.db"
    if existing.exists() and not force:
        console.print(f"[red]{existing} already exists.[/red]")
        console.print("Stop the instance and pass --force if you mean to replace it.")
        raise typer.Exit(code=1)

    into.mkdir(parents=True, exist_ok=True)
    if force and (into / "media").is_dir():
        shutil.rmtree(into / "media")
    with tarfile.open(archive) as held:
        held.extractall(into, filter="data")
    console.print(f"[green]Restored[/green] into {into}. Start the instance.")
