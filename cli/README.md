# Quookly CLI

Typer-based management CLI for Quookly. It talks to the backend through a generated HTTP client,
so the backend must be reachable (and the client generated) for most commands.

## Commands

Run these from this directory, or as `just cli <cmd>` from the repo root.

| Command | Description |
| --- | --- |
| `just install` | sync dependencies with uv |
| `just run <args>` | run the CLI (`uv run quookly-cli <args>`) |
| `just generate-openapi-client` | regenerate `src/quookly_cli/api_client/` from `../openapi.json` |
| `just test` | pytest |
| `just lint` / `just format` | ruff check / ruff format |
| `just typecheck` | mypy (strict) |
| `just check` | lint + typecheck + test |
| `just clean` | remove `__pycache__` and tool caches |

## Generating the API client

The client is **gitignored** and must be generated before the CLI can talk to the API:

```bash
just cli generate-openapi-client
```

It reads the committed `../openapi.json`. To refresh that first, run `just openapi` from the repo
root. Until codegen has run, commands that need the client print
*"Unable to import api client. Did you run the codegen?"*.

## Usage

```bash
just cli run status get-status
```

Point the CLI at a different backend with the `BASE_URL` environment variable. It is read at import
time, so it must be set in the environment before the process starts:

```bash
BASE_URL=https://quookly.example.com just cli run status get-status
```

## Layout

```
src/quookly_cli/
├── cli.py          # Typer root app; mounts subcommands
├── subcommands/    # one Typer app per command group, re-exported from __init__.py
├── di/             # dependency-injector container + pydantic-settings
├── helpers/        # cross-cutting helpers (e.g. the `coro` async adapter)
└── api_client/     # generated (gitignored)
```

## Adding a subcommand

1. Create `subcommands/<name>.py` exposing `cli = Typer(name="<name>", no_args_is_help=True, help=...)`.
2. Re-export it from `subcommands/__init__.py`.
3. Mount it in `cli.py` with `app.add_typer(<name>_cli, name="<name>", help=...)`.
4. For async commands, apply `@coro` from `..helpers` **below** `@cli.command()`.
