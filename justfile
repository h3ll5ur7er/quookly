default:
    @just --list

backend *cmd:
    @cd backend && just {{cmd}}

cli *cmd:
    @cd cli && just {{cmd}}

frontend *cmd:
    @cd frontend && just {{cmd}}

install:
    @just backend install
    @just cli install
    @just frontend install

test:
    @just backend test
    @just cli test
    @just frontend test

lint:
    @just backend lint
    @just cli lint
    @just frontend lint

typecheck:
    @just backend typecheck
    @just cli typecheck
    @just frontend typecheck

format:
    @just backend format
    @just cli format
    @just frontend format

# Links resolve, citations point at something, and the architecture doc names every
# service on disk. Documentation drift is a defect here, and this is what says so.
docs:
    @python3 tools/check-docs.py

check:
    @just docs
    @just backend check
    @just cli check
    @just frontend check

# End to end in a real browser, against the artefact a self-hoster runs. Slower than
# `check` because it builds and drives a browser, so it is a separate gate.
e2e:
    @just frontend e2e

clean:
    @just backend clean
    @just cli clean
    @just frontend clean

build:
    @just install
    @just openapi
    @just lint
    @just typecheck
    @just test
    @just frontend build

openapi:
    @just backend export-openapi
    @just cli generate-openapi-client
    @just frontend generate-openapi-client

# --- running it the way somebody else would -------------------------------------------

# Build the image: the API and the frontend it serves, in one artefact.
image:
    docker build -t quookly:local .

# Bring an instance up from this working tree. Needs a `.env` — copy `.env.example`.
up:
    docker compose up -d --build

# ...with a model beside it.
up-with-model:
    docker compose -f compose.yaml -f compose.ollama.yaml up -d --build

down:
    docker compose down

# What the instance is saying. `just logs -f` to follow.
logs *args:
    docker compose logs {{args}}
