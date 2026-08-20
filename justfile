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

check:
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
