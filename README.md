# Quookly

A fullstack cooking app: a FastAPI backend, a Typer management CLI and an Angular 22 frontend,
wired together automatically through OpenAPI codegen.

## General information

Quookly is a cooking app targeted at professionally trained home chefs and those who want to become one. It is designed to be a personal cooking assistant that helps you manage your recipes, plan your meals, and keep track of your ingredients and stock.

- Want to plan your meals for the week? Quookly can help you create a meal plan and generate a shopping list based on your recipes and stock.
- No idea what to cook? Quookly can generate recipes for you based on your available ingredients, dietary preferences, and desired cuisine.
- Guests with dietary restrictions? Quookly can help you plan meals that accommodate everyone's needs.
- Want to eat healthier? Quookly can provide nutritional information for your recipes and help you make informed choices about your meals.
- Want to reduce food waste? Quookly can help you keep track of your stock and suggest recipes based on what you have available, so you can use up ingredients before they go bad.
- Cooking for adults, elderly, children, or babies? Quookly can help you adjust your recipes to suit different age groups and dietary needs.
- Annoyed at the text bloat recipes you find online? Quookly can destill the essence of a recipe down to the ingredients, steps, and nutritional information you need to know, without any unnecessary fluff.
- No idea what a kitchen-chargon word means? Quookly can provide definitions for cooking terms and techniques, so you can learn as you cook. 

## Features

- simple user management with JWT authentication
- server onboarding: a fresh instance guides the operator through creating the first admin user
- user onboarding: new accounts are walked through eaters, dietary preferences, units and locale
- sane defaults: ships with a starter ingredient registry and a set of recipes, so the app is usable
  and testable from the first run
- cooking mode: pick a recipe and the eaters, then get a mise-en-place list followed by step-by-step
  guidance, with per-step timers and one-tap access to the academy entry for any jargon on screen
- per-eater appetite multiplier, so portions match the person rather than the head count
- mobile-first: the phone and tablet are the primary targets, installable as a PWA, with the active
  recipe, running cooking session and shopping list usable offline
- theming: light, dark, playful and decorative themes, following the system preference until you
  choose, and extensible by self-hosters without a rebuild
- recipe management with ingredients, steps, tags, variants, images, ratings and comments
- weekly meal planning with shopping list generation
- stock management with automatic stock deduction when planning meals
- private and public recipes
- ingredient registry with nutritional information
- unit conversion and automatic unit conversion when adding ingredients to recipes (e.g., cups to grams, tablespoons to grams, etc). each user can define their own preferred units for each kind of ingredient (e.g. powders -> grams, liquids -> milliliters, solids -> grams, etc).
- recipe import from exported JSON
- AI-powered recipe generation (from ingredients, tags, recipe name, recipe description, user uploaded image, website URL or a combination of these)
  - self hosted AI model (ollama, vllm, etc)
  - byo-api-key for major llm providers (OpenAI/anthropic/open router/etc)
- recipe search with filters and fulltext search
- fully localized frontend with i18n support (en_GB, de_CH, fr_CH)
- learning area with definitions for cooking terms and techniques, as well as tips and tricks for cooking (extensible by the users).
- social cooking:
  - users can follow each other and see each other's recipes and shared meal plans
  - users can comment on each other's recipes and meal plans
  - users can rate each other's recipes
  - users can share their meal plans and recipes with each other
- gamification: users can earn points and badges for completing learning modules and contributing to the learning area (e.g., adding definitions, tips and tricks, etc). The points and badges can be displayed on the user's profile page.
  - Users can also earn points and badges for completing recipes, meal plans, and stock management tasks. The points and badges can be displayed on the user's profile page.
  - leaderboards: users can see how they rank against other users in terms of points and badges earned. The leaderboards can be filtered by time period (e.g., weekly, monthly, all-time), by category (e.g., recipes, meal plans, stock management, learning area contributions) and by user-group (favorites, friends, world).
- Users can assign "regular guests" to their profile, each one with their own dietary preferences and restrictions. When planning meals, the user can select which guests will be attending, and Quookly will automatically filter recipes based on the guests' dietary preferences and restrictions. 
- Pages:
  - LoggedOut/public pages
    - Landing/hero page
    - Public recipe list page with search and filters
    - Academy page with learning area
  - LoggedIn/private pages
    - Dashboard page with meal plan overview and stock overview
    - Recipe list page with search and filters
    - Recipe detail page with ingredients, steps, tags, variants, images, ratings and comments
    - Meal plan page with shopping list generation
    - Stock management page with automatic stock deduction when planning meals
    - Shopping list page with automatic stock deduction when planning meals
    - Ingredient registry page with nutritional information
    - Settings page with user management and unit conversion preferences
    - Cooking mode: mise-en-place, guided steps, timers, inline academy lookup
    - Onboarding flow for new users
    - Social page with user profile, points and badges
    - Academy page with learning area
      - Gamification dashboard
      - Learning modules with definitions for cooking terms and techniques, as well as tips and tricks for cooking (extensible by the users).


## Documentation

Design documentation lives in [`doc/`](doc/README.md):

| Document | What it answers |
| --- | --- |
| [Vision](doc/01-vision.md) | Why this exists, who it is for, what it refuses to be |
| [Requirements](doc/02-requirements.md) | Actors, use cases, functional and non-functional requirements |
| [Volatility analysis](doc/03-volatility-analysis.md) | What changes, and why the feature list is not the architecture |
| [Architecture](doc/04-architecture.md) | Services, layers, call rules, code layout |
| [Use case flows](doc/05-use-case-flows.md) | How services interact to satisfy the requirements |
| [Domain model](doc/06-domain-model.md) | The concepts and their relationships |
| [Decisions](doc/07-decisions.md) | Design decisions and what is still open |
| [Roadmap](doc/08-roadmap.md) | Delivery order |
| [Installation](doc/09-installation.md) | Running and self-hosting |
| [Development](doc/10-development.md) | Working on Quookly, and contributing |
| [Design language](doc/11-design-language.md) | How it should look and feel, and the theming system |

Start with [the volatility analysis](doc/03-volatility-analysis.md) before judging the
architecture — the code deliberately does not mirror the feature list above.

## Running your own

One container serves the API and the frontend. Everything an instance keeps — the database
and the pictures — lives in one volume, so backing it up is copying one thing.

```bash
curl -O https://raw.githubusercontent.com/h3ll5ur7er/quookly/master/compose.yaml
curl -o .env https://raw.githubusercontent.com/h3ll5ur7er/quookly/master/.env.example

# The one setting with no default. Shipping one would give every instance the same
# signing key, which is worse than refusing to start.
sed -i "s|^QUOOKLY_SECRET_KEY=|QUOOKLY_SECRET_KEY=$(openssl rand -base64 48)|" .env

docker compose up -d
```

Then open <http://localhost:8000>. The first account you make is the administrator's;
everybody after that applies and is let in by them.

`.env.example` documents every setting, including the ones with sensible defaults.

### With a model beside it

Quookly works without one. What it cannot do without a model is read a recipe off a blog
that publishes no structured data, write one from a description, adapt one to a change,
translate one into your language, or explain a word nobody on the instance has explained.
Every other screen works, and each of those says so plainly rather than failing as though
something broke.

```bash
curl -O https://raw.githubusercontent.com/h3ll5ur7er/quookly/master/compose.ollama.yaml
docker compose -f compose.yaml -f compose.ollama.yaml up -d
docker compose exec ollama ollama pull llama3.1:8b
```

Or point `QUOOKLY_INFERENCE_BASE_URL` at anything OpenAI-compatible you already run.

### With an assistant plugged into it

Quookly speaks [MCP](https://modelcontextprotocol.io), so an agent can look at your pantry,
find something that needs no shopping trip, and write a recipe from what is about to go off.
It is mounted in the instance itself at `/mcp` — one process, one database, one event bus.

Authentication is the API's: an agent is a cook holding a token, and it sees what that cook
sees. Point a host that speaks HTTP straight at it:

```json
{"mcpServers": {"quookly": {
  "url": "http://your-instance:8000/mcp",
  "headers": {"Authorization": "Bearer <your token>"}
}}}
```

For a host that speaks only stdio, the CLI carries a bridge — a relay, with no logic in it:

```bash
BASE_URL=http://your-instance:8000 QUOOKLY_TOKEN=<your token> python -m quookly_cli mcp
```

Recipes an agent writes are stored as generated, unapproved and private. They are yours to
read and approve, and nothing leaves the instance because nothing here ever does.

### Backing it up

Two things live in the volume, not one: the database, and a directory of pictures beside
it. A backup of the `.db` alone restores an instance whose pages have holes in them.

```bash
docker compose exec app quookly-cli data take-backup /data/backup.tar.gz
```

Safe against a serving instance — it asks SQLite for a consistent snapshot rather than
copying the file, which is what makes `tar` of a live database a backup that looks fine
until the day you need it. `quookly-cli data restore` puts one back, and refuses to
overwrite an instance that still has data unless you say `--force`.

### From this working tree

```bash
cp .env.example .env    # then set QUOOKLY_SECRET_KEY
just up                 # builds and runs what is checked out
just logs -f
just down
```

## Tools

- management CLI built with Typer
- fully automated wiring of backend, frontend and cli via openapi and codegen
- justfiles that encapsulate all important commands for development

## Prerequisites

For running an instance: **docker** and nothing else.

For developing:

- uv
- just
- nvm
- openjdk-jre (only for codegen, not required for developing or running the app)

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

### Development practice

Test-driven, with quality gates per unit of work rather than per pull request:

1. read the spec, 2. write the failing test, 3. implement until green, 4. refactor.

Then, before moving on: `just check`, review and refactor, confirm the change sits where the
architecture says it should, and update the documentation. Details in
[doc/10-development.md](doc/10-development.md#the-development-loop); rationale in
[ADR-017](doc/07-decisions.md#adr-017-test-driven-development-with-per-unit-quality-gates).

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

Full detail in [doc/04-architecture.md](doc/04-architecture.md); the analysis behind it is in
[doc/03-volatility-analysis.md](doc/03-volatility-analysis.md).

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
