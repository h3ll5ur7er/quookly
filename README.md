# Fullstack webapp template

## Tools

- management cli via 
- fully automated wiring of backend, frontend and cli via openapi and codegen
- justfiles that encapsulate all important commands for development

## Prerequisites

- uv
- just
- nvm
- openjdk-jre (only for codegen, not required for development or running the app)

## Developemnt

### getting started

- install prerequisites
- install dependencies: `just install`
- start the backend: `just backend run`

### uv

The python projects are managed by uv, therefor the usage of "pip install", "uv pip install", "python -m pip install" are prohibited.

To install dependecies use `uv add <dep>`
To run things use `uv run <thing>`

### just commands

All tools and entrypoints you might need commonly are encapsulated in justfiles:

#### `just <cmd>`

- `just`: list available commands
- `just backed <cmd>`: backend related commands
- `just cli <cmd>`: cli related commands
- `just frontend <cmd>`: frontend related commands
- `just test`: run all test
- `just lint`: lint all projects
- `just openapi`: generate openapi client for all projects
- `just build`: codegen, typecheck, lint, test and build all projects

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
- `just frontend check`: checks frontend code (lint, typecheck, run tests)
- `just frontend generate-openapi-client`: generate openapi client

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
