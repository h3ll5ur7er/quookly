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
    

clean:
    @just backend clean
    @just cli clean
    @just frontend clean

build:
    @just install
    @just openapi
    @just lint
    @just test
    @just frontend build

    
openapi:
    @just backend export-openapi
    @just cli generate-openapi-client
    @just frontend generate-openapi-client
    