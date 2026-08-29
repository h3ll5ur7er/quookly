# syntax=docker/dockerfile:1

# Quookly in one image: the API and the frontend it serves.
#
# One artefact rather than two (NFR-2). The backend already serves the built frontend from
# inside its own package, so splitting them would mean running a second web server to
# serve files the first one is holding.

# --- the frontend ---------------------------------------------------------------------
# Built first and separately, so a backend-only change does not reinstall node_modules.
FROM node:24.15.0-bookworm-slim AS frontend

# The generated client is built by openapi-generator-cli, which is a Java program. The JRE
# is installed here and goes no further: the runtime image below is Python only.
RUN apt-get update \
 && apt-get install --no-install-recommends -y default-jre-headless \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build/frontend
# The lockfile alone first: `npm ci` is the slow layer and it depends on nothing else, so
# it stays cached until a dependency actually changes.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# `openapi.json` sits beside the frontend because the generate script reads `../openapi.json`
# — the same path it has in the repository, so this builds what a developer builds.
COPY openapi.json /build/openapi.json
COPY frontend/ ./
RUN npm run generate-openapi && npm run build

# --- the python dependencies ------------------------------------------------------------
FROM python:3.12-slim-bookworm AS backend

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies before source, for the same reason as `npm ci` above.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# The CLI, into the same environment. It is how an operator backs the instance up, and a
# backup has to run where the data is — inside this container, not on somebody's laptop
# (ADR-071).
#
# With its dependencies: the backend has neither typer nor rich, so a `--no-deps` install
# would put a command in the image that cannot start. The *generated* API client is not
# here and is not wanted — nothing in a container needs to reach the API over HTTP from
# inside the container — and the CLI already guards that import, which is what makes the
# local-filesystem commands work without it.
COPY cli/pyproject.toml cli/uv.lock cli/README.md /app/cli/
COPY cli/src /app/cli/src
RUN --mount=type=cache,target=/root/.cache/uv uv pip install /app/cli

# --- what actually runs -----------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Not root. Nothing here needs it, and an instance somebody else runs should not be the
# place that discovers otherwise.
RUN useradd --create-home --uid 10001 quookly

WORKDIR /app/backend
COPY --from=backend --chown=quookly:quookly /app /app
# Into the backend package, which is where the 404 handler looks. `FRONTEND_STATIC_DIR` is
# a path relative to the working directory, which is why that is set below and not moved.
# Angular writes to `../backend/src/quookly/app/` relative to its own workspace, which in
# that stage is `/build/backend/...`.
COPY --from=frontend --chown=quookly:quookly /build/backend/src/quookly/app /app/backend/src/quookly/app
COPY --chown=quookly:quookly Dockerfile.entrypoint.sh /usr/local/bin/quookly-start

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    QUOOKLY_ENVIRONMENT=production \
    # Both under one directory on purpose. Pictures live beside the database rather than
    # inside it, so backing an instance up is copying two things — and one volume is how
    # that stops being a footgun (ADR-057).
    QUOOKLY_DATABASE_URL=sqlite+aiosqlite:////data/quookly.db \
    QUOOKLY_MEDIA_DIR=/data/media \
    PORT=8000

RUN chmod +x /usr/local/bin/quookly-start && install -d -o quookly -g quookly /data
VOLUME ["/data"]
USER quookly
EXPOSE 8000

# Answers before the first request and keeps answering. `/api/v1/status` touches no
# database, so it says the process is up rather than that the disk is happy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",8000)}/api/v1/status').read()"

ENTRYPOINT ["quookly-start"]
