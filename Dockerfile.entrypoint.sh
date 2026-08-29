#!/bin/sh
# Bring the database up to date, then serve — or run whatever was asked for instead.
#
# Migrations run here rather than in the application's lifespan: an instance that migrates
# itself on every boot is one where two containers starting together race each other, and
# where a failed migration looks like a failed start-up. Here it fails loudly, before
# anything is listening.
#
# A command passed to `docker run` is run **instead**, without migrating. That is what
# makes a one-off operator command possible — `docker run --rm -v quookly-data:/data
# quookly quookly-cli data take-backup /data/backup.tar.gz` — and it is why this honours
# "$@" rather than always serving. Without it, asking the image to take a backup starts a
# second web server against the volume, which is the opposite of what was asked for
# (ADR-071). No migration, deliberately: backing up a database is not a reason to change
# its schema, and an operator reaching for a backup may be reaching for it *because* an
# upgrade went wrong.
set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "quookly: applying migrations"
alembic upgrade head

echo "quookly: serving on :${PORT:-8000}"
exec uvicorn quookly.api:app --host 0.0.0.0 --port "${PORT:-8000}"
