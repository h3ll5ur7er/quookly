#!/usr/bin/env bash
# Serve the built application from a fresh, empty instance.
#
# Fresh matters: the first-admin bootstrap closes permanently once any account exists,
# so a database left over from a previous run would skip the journey these tests exist
# to cover.
set -euo pipefail

cd "$(dirname "$0")/../.."

DATABASE="$PWD/backend/e2e-run.db"
rm -f "$DATABASE"

export QUOOKLY_DATABASE_URL="sqlite+aiosqlite:///$DATABASE"
export QUOOKLY_SECRET_KEY="an-end-to-end-signing-key-of-sufficient-length"
# The URL import fetches from the *server*, so the pages under test are served from a
# second local server — which means lifting the guard that stops an instance fetching its
# own network (ADR-027). Exercising that setting is itself worth something: this is the
# configuration a self-hoster with a recipe box on their LAN runs.
export QUOOKLY_ALLOW_PRIVATE_FETCH=true

cd backend
uv run alembic upgrade head >/dev/null
# Directly, without the reloader: a supervised subprocess outlives the signal Playwright
# sends when the suite finishes.
exec uv run uvicorn quookly.api:app --host 127.0.0.1 --port 8181
