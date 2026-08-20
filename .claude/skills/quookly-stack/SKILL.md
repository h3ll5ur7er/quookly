---
name: quookly-stack
description: Guidelines, tooling and conventions for the quookly fullstack cooking app (uv + FastAPI backend, Typer CLI, nvm + Angular 21 frontend, wired by OpenAPI codegen and justfiles). Load before adding endpoints, CLI commands, or Angular components, before running builds/tests/lint, and whenever touching dependencies or the openapi.json contract.
---

# Quookly stack

Quookly is a cooking app built as a three-project monorepo: a FastAPI **backend**, a Typer **cli**, and an Angular 21 **frontend**. The three are kept in sync automatically: the backend is the single source of truth for the API, and both clients are **generated** from its OpenAPI schema.

```
quookly/
├── justfile           # root: delegates to sub-justfiles, orchestrates cross-project tasks
├── openapi.json       # generated contract — backend exports it, cli+frontend consume it
├── backend/           # FastAPI, uv, python 3.12 — package `quookly`; also serves the built frontend
├── cli/               # Typer + dependency-injector, uv, python 3.12 — package `quookly_cli`
└── frontend/          # Angular 21, npm via nvm (node v24.15.0)
```

## Non-negotiable tooling rules

**Never bypass the tool managers.** These are hard rules for this repo:

- **Python: uv only.** `pip install`, `uv pip install`, `python -m pip install` and hand-edited `[project.dependencies]` are prohibited. Use `uv add <dep>` / `uv add --dev <dep>` / `uv remove <dep>`, and run everything through `uv run <thing>`. `uv.lock` is committed — let uv update it.
- **Node: nvm only.** Never call `npm`/`ng` from a bare shell; the frontend pins node `v24.15.0` in `.nvmrc` and the justfile sources nvm for every command. Go through `just frontend <cmd>` — its `_nvm` helper does `source "$NVM_DIR/nvm.sh" && nvm use` first. For ad-hoc commands use `just frontend _nvm "<command>"`.
- **just is the entrypoint for everything.** Do not reinvent commands that a recipe already encapsulates. `just --list` (or bare `just`) in any directory shows what's available.

Prerequisites: `uv`, `just`, `nvm`, and a JRE (`openjdk-jre`) — Java is needed **only** for the frontend's openapi-generator-cli, not for developing or running the app.

## Commands

Root recipes fan out to all three projects:

| Command | Effect |
| --- | --- |
| `just install` | installs backend, cli and frontend deps |
| `just openapi` | **full codegen chain** — export schema, then regenerate both clients |
| `just lint` | ruff (backend, cli) + ng lint (frontend) |
| `just typecheck` | mypy (backend, cli) + ngc (frontend, templates included) |
| `just format` | ruff format (backend, cli) + prettier (frontend) |
| `just test` | pytest (backend, cli) + vitest (frontend) |
| `just check` | lint + typecheck + test across all three |
| `just build` | install → openapi → lint → typecheck → test → frontend build |
| `just clean` | drops caches in all three projects |
| `just backend <cmd>` / `just cli <cmd>` / `just frontend <cmd>` | delegate into a sub-justfile |

Per project:

- **backend**: `install`, `run` / `serve`, `export-openapi`, `test`, `lint`, `format`, `typecheck`, `check`, `clean`
- **cli**: `install`, `run [args]`, `test`, `lint`, `format`, `typecheck`, `check`, `generate-openapi-client`, `clean`
- **frontend**: `install`, `serve`, `build`, `test`, `lint`, `format`, `format-check`, `typecheck`, `check`, `generate-openapi-client`, `clean`

Start the app with `just backend run` — uvicorn with `reload=True` on `0.0.0.0:$PORT` (default `8000`). For frontend work, `just frontend serve` gives you the Angular dev server on `:4200` talking to the backend on `:8000` (CORS is wide open in dev).

**Bootstrap a fresh clone with `just install && just openapi`** — both generated clients are gitignored, so without codegen the frontend won't compile and the cli can't reach the API.

## Design documentation

`doc/` holds the design of the product, and it is the authority on *what to build and where it
goes*. Read before adding domain code:

| Document | Read it when |
| --- | --- |
| `doc/03-volatility-analysis.md` | Placing any new feature — it defines the 16 volatilities and the procedure for placing work |
| `doc/04-architecture.md` | Adding a service — service catalog, layers, call rules, code layout |
| `doc/05-use-case-flows.md` | Implementing a use case — sequence diagrams per flow |
| `doc/06-domain-model.md` | Touching the data model |
| `doc/07-decisions.md` | Before revisiting a settled decision, or when one is marked Open |
| `doc/08-roadmap.md` | Deciding what comes next |

Rules from those documents that are easy to violate and expensive to unwind:

1. **Suitability and allergen conclusions are computed from structured ingredients, never taken
   from model-generated text.** `SuitabilityEngine` is a pure function with no I/O and no model
   access. This is safety-critical — see `doc/07-decisions.md` ADR-006.
2. **Managers never call managers.** Cross-manager reactions go through the event bus.
3. **Rule engines are pure.** No I/O; reference data arrives as arguments. An engine that grows a
   resource-access call has stopped being a rule engine.
4. **The phone is the design target.** Author layouts at the narrow viewport and widen. Never the
   reverse.

## How to work: test-first, gate per unit

This project treats quality, architecture, and documentation as part of every unit of work, not a
phase at the end (ADR-017). Follow this loop:

1. **Read the spec** — the use case in `doc/02-requirements.md`, the flow in
   `doc/05-use-case-flows.md`, the volatility in `doc/03-volatility-analysis.md`.
2. **Write the failing test first.** Run it; confirm it fails for the right reason.
3. **Implement** until green — the simplest thing that passes.
4. **Refactor** with the test green.
5. **Run the gate** before moving on:

```bash
just check
```

Then verify, every time:

- lint and typecheck green, with no suppressions added
- the whole test suite passes, not only the tests you touched
- the code has been re-read and refactored — duplication, unclear names, functions doing two things
- it sits in the layer the architecture says it does, with no Manager→Manager call and no rule engine
  doing I/O
- **the documentation is updated in the same commit** if this changed a decision, volatility, flow,
  or requirement

Documentation drift is a defect, exactly like a failing test. Do not batch the gate to the end of a
task — a layer violation caught immediately is a one-line fix; caught later it is a refactor.

Rule engines are pure functions, which makes their tests a table of inputs and expected outputs with
no fixtures, database, or mocks. Use that; it is why the decomposition is shaped this way.

If a change is awkward to place, do **not** force it into the nearest service. Report which it is: a
new volatility, a misplaced one, or a requirement that is not yet understood.

## Architecture: iDesign, decomposed by volatility

The codebase is **not** organized by feature. It is decomposed by *volatility* — each service encapsulates one thing that is likely to change and owns it. Requirements are satisfied by the *interaction* of services, not by a subsystem per requirement. When adding a recipe/pantry/meal-plan capability, resist creating a `recipes` vertical slice that spans all layers; ask instead which volatility is new. `doc/03-volatility-analysis.md` has the four-question procedure for this, and lists what was deliberately *not* made a service.

Service flavors and their call rules:

- **Client** — entrypoints that initiate interaction: API routes, CLI commands, Angular components/pages.
- **Manager** — stateful business logic; orchestrates a use case.
- **Engine** — stateless business logic; pure rules and computation.
- **Resource Access** — access to a resource: database, file system, third-party API.
- **Helper** — cross-cutting: logging, configuration, pubsub.

Allowed calls (enforce these in review):

```
Client   → Manager, Engine
Manager  → Engine, ResourceAccess        (never another Manager)
Engine   → Engine, ResourceAccess        (never a Manager)
ResourceAccess → ResourceAccess          (never Manager or Engine)
Helper   → nothing else                  (but anyone may use a Helper)
```

Calls flow strictly downward. A Manager calling a Manager, or a Resource Access reaching up into business logic, is a defect.

## The OpenAPI contract — how the three projects stay wired

This is the backbone of the template. **The backend is the only place an API shape is authored.** Both clients are generated; hand-writing HTTP calls or DTOs in the cli or frontend defeats the design.

```
backend routes + pydantic models
  └─ just backend export-openapi   →  openapi.json  (uv run export_openapi > ../openapi.json)
       ├─ just cli generate-openapi-client       → cli/src/quookly_cli/api_client/  (openapi-python-client)
       └─ just frontend generate-openapi-client  → frontend/src/api/                (openapi-generator-cli, needs Java)
```

**Run `just openapi` after every backend API change.** Skipping it leaves the clients stale and the frontend build referencing methods that no longer exist.

Two consequences to keep in mind:

1. **Both generated client directories are gitignored** (`cli/**/api_client/*`, `frontend/src/api`). The cli defensively try/excepts these imports and prints *"Unable to import api client. Did you run the codegen?"* — treat that message as "run codegen", not as a bug to patch.
2. **Never edit generated code.** `frontend/src/api/**` is excluded from eslint and prettier, and `cli/src/quookly_cli/api_client/**` from ruff, mypy and git, for exactly this reason. Any change there is erased on the next codegen run.

### Operation IDs decide client method names

`backend/src/quookly/api.py` installs a `generate_unique_id_function` that turns the route's **function name** into a camelCase operationId (`get_status` → `getStatus`) and asserts uniqueness **per tag** (duplicates raise `ValueError` at schema-generation time).

So the Python function name you choose *is* the public client API: `def get_status()` becomes `StatusService.getStatus()` in Angular and `get_status.asyncio(...)` in the cli. Name route handlers deliberately — `create_recipe`, `list_recipes`, `get_recipe` — and keep them unique within their tag.

## Backend (`backend/`)

FastAPI on python `>=3.12`, packaged with `uv_build`, distribution name `quookly`, source under `src/quookly/`.

- `api.py` — app construction, CORS, lifespan, router registration, the operationId generator, and the SPA fallback.
- `routes/` — one module per router; each exports `router`, re-exported from `routes/__init__.py`. Register with `app.include_router(x_router, prefix="/api/v1", tags=["x"])`. **Always tag** (the operationId uniqueness check is keyed on tags) and keep the `/api/v1` prefix.
- Define an explicit pydantic `BaseModel`, pass `response_model=`, **and annotate the handler's return type** — mypy runs in strict mode, and the model is what lands in the generated clients. Return the model instance, not a bare dict.
- Console scripts: `quookly` (serves the app) and `export_openapi` (prints the schema to stdout).
- `lifespan` is an `@asynccontextmanager`; add startup work before the `yield` and shutdown work after it.

**The backend also serves the frontend in production.** `angular.json` sets `outputPath` to `backend/src/quookly/app/`, and the backend's 404 handler falls back to `src/quookly/app/browser/index.html` so Angular client-side routes resolve. Two implications: the built frontend lives inside the backend package (gitignored via `**/app/*`), and `FRONTEND_STATIC_DIR` is a **relative** path — the backend must be started with `backend/` as the working directory, which `just backend run` guarantees.

Tooling config lives in `pyproject.toml`: ruff (line length 100, `E,F,I,UP,B,SIM`), mypy `strict = true` over `src` and `tests`, pytest with `asyncio_mode = "auto"` (async tests need **no** explicit marker) and `testpaths = ["tests"]`.

## CLI (`cli/`)

Typer app, distribution name `quookly-cli`, package `quookly_cli`, entrypoint `src/quookly_cli/cli.py:main`, wired with `no_args_is_help=True`.

- **Subcommands** live in `subcommands/`, each exposing a `cli = Typer(...)`, re-exported through `subcommands/__init__.py` and mounted in `cli.py` with `app.add_typer(sub_cli, name="...", help="...")`.
- **Async commands** use the `coro` decorator from `helpers/` (wraps `asyncio.run`), applied *below* `@cli.command()`. It is typed with PEP 695 generics, so the wrapped signature is preserved.
- **DI** via `dependency-injector`: `di/container.py` holds `AppContainer` with an `api_client` singleton built from settings; get it via `get_container()`. Use the client as a context manager: `with get_container().api_client() as client:`.
- **Settings** via `pydantic-settings` in `di/settings.py`. The nesting is *not* delimiter-based — `ApiSettings` is itself a `BaseSettings` instantiated as the default, so the env var that overrides the API base URL is **`BASE_URL`**, not `API__BASE_URL`. It is read at import time, so it must be present in the environment before the process starts: `BASE_URL=http://127.0.0.1:8123 just cli run status get-status`.
- Generated client calls return `T | None`; **handle the `None` case** (strict mypy will force you to) — an unreachable API is a normal outcome for a CLI.
- Output uses `rich.Console` for styled terminal output.

Same tooling config as the backend, plus `ignore_errors` for the generated `api_client` package.

## Frontend (`frontend/`)

Angular 21, standalone/signals-first, strict TypeScript, SCSS, Vitest.

**`frontend/AGENTS.md` is the authoritative Angular style guide.** It is auto-loaded for Claude via `frontend/CLAUDE.md`, which imports it with `@AGENTS.md` — subdirectory CLAUDE.md files load on demand when files in that directory are read. `.github/copilot-instructions.md` is a symlink to the same file, so all three tools read one source. **Edit `AGENTS.md`, never the symlink.**

Its key rules:

- Standalone components only; never set `standalone: true` (it's the default in v20+).
- `input()` / `output()` functions, not decorators. Host bindings in the `host` object, never `@HostBinding`/`@HostListener`.
- Signals for state, `computed()` for derived state; `set`/`update`, never `mutate`.
- `ChangeDetectionStrategy.OnPush`; small single-responsibility components.
- Native control flow `@if` / `@for` / `@switch` — not `*ngIf` / `*ngFor` / `*ngSwitch`.
- `class` and `style` bindings — not `ngClass` / `ngStyle`.
- `inject()` over constructor injection; services `providedIn: 'root'`.
- Reactive forms over template-driven. `NgOptimizedImage` for static images.
- Accessibility is a requirement: WCAG AA minimums and passing AXE checks (the eslint config enables `templateAccessibility`).

Structural conventions:

- `src/app/core/` for shared/cross-cutting components, `src/app/features/` for routed feature areas. Routes in `app.routes.ts` use `loadComponent` — **lazy-load every feature route**.
- Providers go in `app.config.ts`. `provideApi(window.location.origin)` points the generated client at the serving origin. `HttpClient` needs no explicit `provideHttpClient()` — Angular 21 provides it in root.
- Import generated API services via the **`@api` path alias** (`import { StatusService } from '@api'`), mapped in `tsconfig.json` to `src/api/index.ts`. Don't use deep relative paths into `src/api`.
- Component selectors are `app-` prefixed kebab-case; directives `app-` camelCase (enforced by eslint).
- Formatting: prettier, 100 cols, single quotes, angular parser for HTML; `.prettierignore` excludes the generated client. Editor settings in `.editorconfig` (2-space indent).
- `just frontend typecheck` runs `ngc --noEmit` over both tsconfigs, so it catches **template** type errors (`strictTemplates`) that plain `tsc` misses. Use it, not `tsc`.
- Angular CLI MCP server is configured in `.vscode/mcp.json` for schematics assistance.

## Working agreements

1. **Backend API change → `just openapi` → update clients.** Never let the contract drift.
2. **Add dependencies through the manager**: `uv add` / `uv add --dev` for python, `just frontend _nvm "npm install <pkg>"` for the frontend.
3. **Before declaring work done**, run the checks for what you touched — `just backend check`, `just cli check`, `just frontend check` — or `just build` for the whole chain.
4. **Respect the iDesign call rules** when placing new code, and put it where its volatility belongs rather than next to related features.
5. **Never hand-edit generated code** (`frontend/src/api/**`, `cli/src/quookly_cli/api_client/**`, `backend/src/quookly/app/**`, `openapi.json`).
6. **Both python projects are strict-mypy clean — keep them that way.** Annotate every function, including tests.

## Verified baseline

As of the template cleanup, all of the following pass from a clean tree:

- `just backend check` — ruff, strict mypy, pytest
- `just cli check` — ruff, strict mypy, pytest
- `just frontend check` — ng lint, ngc typecheck (app + spec), vitest
- `just build` — full chain, frontend bundle emitted to `backend/src/quookly/app`
- `just openapi` — reproduces both clients; backend serves `/api/v1/status`, `/index.html` and the SPA fallback; `just cli run status get-status` reaches a live backend

If one of these fails, it is something in the working tree — not a known template defect.
