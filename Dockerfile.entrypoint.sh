#!/bin/sh
# Bring the database up to date, then serve.
#
# Migrations run here rather than in the application's lifespan: an instance that migrates
# itself on every boot is one where two containers starting together race each other, and
# where a failed migration looks like a failed start-up. Here it fails loudly, before
# anything is listening.
set -eu

echo "quookly: applying migrations"
alembic upgrade head

echo "quookly: serving on :${PORT:-8000}"
exec uvicorn quookly.api:app --host 0.0.0.0 --port "${PORT:-8000}"
