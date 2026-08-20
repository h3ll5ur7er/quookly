# Quookly

A fullstack cooking app: a FastAPI backend, a Typer management CLI and an Angular 21 frontend,
wired together automatically through OpenAPI codegen.

## Tools

- management CLI built with Typer
- fully automated wiring of backend, frontend and cli via openapi and codegen
- justfiles that encapsulate all important commands for development

## Prerequisites

- uv
- just
- nvm
- openjdk-jre (only for codegen, not required for development or running the app)

## Development

### getting started

- install prerequisites
- install dependencies: `just install`
- generate the API clients: `just openapi` (required — both clients are gitignored)
- start the backend: `just backend run`
- for frontend work, start the dev server too: `just frontend serve`

### uv

The python projects are managed by uv, therefore the usage of "pip install", "uv pip install", "python -m pip install" is prohibited.

To install dependencies use `uv add <dep>` (or `uv add --dev <dep>`)
To run things use `uv run <thing>`

### just commands

All tools and entrypoints you might need commonly are encapsulated in justfiles:

#### `just <cmd>`

- `just`: list available commands
- `just backend <cmd>`: backend related commands
- `just cli <cmd>`: cli related commands
- `just frontend <cmd>`: frontend related commands
- `just test`: run all tests
- `just lint`: lint all projects
- `just typecheck`: typecheck all projects
- `just format`: format all projects
- `just check`: lint, typecheck and test all projects
- `just openapi`: regenerate the openapi schema and both clients
- `just build`: install, codegen, lint, typecheck, test and build all projects
- `just clean`: remove caches and build output in all projects

#### `just backend <cmd>`

- `just backend`: list all backend related commands
- `just backend install`: install backend dependencies
- `just backend run`: run backend commands
- `just backend test`: run backend tests
- `just backend lint`: lints backend code
- `just backend format`: formats backend code
- `just backend typecheck`: typechecks backend code
- `just backend check`: checks backend code (lint, typecheck, run tests)

#### `just cli <cmd>`

- `just cli`: list all cli related commands
- `just cli install`: install cli dependencies
- `just cli run`: run cli commands
- `just cli test`: run cli tests
- `just cli lint`: lints cli code
- `just cli format`: formats cli code
- `just cli typecheck`: typechecks cli code
- `just cli check`: checks cli code (lint, typecheck, run tests)
- `just cli generate-openapi-client`: generate openapi client

#### `just frontend <cmd>`

- `just frontend`: list all frontend related commands
- `just frontend install`: install frontend dependencies
- `just frontend serve`: serve frontend code
- `just frontend build`: build frontend code
- `just frontend test`: run frontend tests
- `just frontend lint`: lints frontend code
- `just frontend format`: formats frontend code
- `just frontend typecheck`: typechecks frontend code (including Angular templates)
- `just frontend format-check`: checks formatting without writing
- `just frontend check`: checks frontend code (lint, typecheck, run tests)
- `just frontend generate-openapi-client`: generate openapi client

### The OpenAPI contract

The backend is the single source of truth for the API. Both clients are **generated** — never
hand-write HTTP calls or DTOs in the cli or the frontend, and never edit generated code.

```
backend routes + pydantic models
  └─ just backend export-openapi   →  openapi.json
       ├─ just cli generate-openapi-client       → cli/src/quookly_cli/api_client/
       └─ just frontend generate-openapi-client  → frontend/src/api/
```

Run `just openapi` after every backend API change. Both generated directories are gitignored, so a
fresh clone needs `just install && just openapi` before the frontend will compile.

A route's **function name** determines the generated client method name (`get_status` → `getStatus`),
and must be unique within its tag.

### Architecture

The architecture strictly follows the iDesign Method. The code is not broken down by features, but volatilities. Requirements are not represented by subsystems, but by the interaction of services. Each service encapsulates a single volatility and is responsible for it. There are the following "flavors" of services:

- Client services: Entrypoints that initiate interactions with the system, e.g. api routes, etc.
- Manager services: Encapsulate parts of business logic that has a state.
- Engine services: Encapsulate parts of business logic that are stateless.
- Resource access services: Encapsulate access to resources, e.g. database access, file system access, etc.
- Helper services: Cross-cutting services that are used by other services, e.g. logging, configuration, pubsub, etc.

Client services interact with manager and engine services, which in turn interact with resource access services. Helper services can be used by any service.
Manager services can interact with engine services, but not with other manager services. Engine services can interact with other engine services, but not with manager services.
Resource access services should not interact with manager or engine services, but only with other resource access services.
Helper services should not interact with services of other flavors, but can be used by any service.
