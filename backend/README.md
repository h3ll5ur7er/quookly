# Quookly Backend

FastAPI service for Quookly. It owns the API contract (everything in `openapi.json` is generated
from here) and, in production, also serves the compiled Angular frontend.

## Commands

Run these from this directory, or as `just backend <cmd>` from the repo root.

| Command | Description |
| --- | --- |
| `just install` | sync dependencies with uv |
| `just run` / `just serve` | start uvicorn with reload on `$PORT` (default `8000`) |
| `just export-openapi` | write the OpenAPI schema to `../openapi.json` |
| `just test` | pytest |
| `just lint` / `just format` | ruff check / ruff format |
| `just typecheck` | mypy (strict) |
| `just check` | lint + typecheck + test |
| `just clean` | remove `__pycache__` and tool caches |

## Layout

```
src/quookly/
├── api.py        # app construction, CORS, lifespan, operationId generator, SPA fallback
├── routes/       # one module per APIRouter, re-exported from __init__.py
└── app/          # build output of the Angular frontend (gitignored)
```

## Adding an endpoint

1. Add or extend a router in `routes/`, export it from `routes/__init__.py`.
2. Register it in `api.py` with `app.include_router(x_router, prefix="/api/v1", tags=["x"])` —
   the tag is required, the operationId uniqueness check is keyed on it.
3. Define a pydantic `BaseModel` and pass `response_model=`; that model is what reaches the
   generated clients.
4. Regenerate the clients from the repo root: `just openapi`.

The route **function name** becomes the client method name — `def get_status()` turns into
`getStatus()` in Angular and `get_status.asyncio(...)` in the CLI. Names must be unique per tag.

## Notes

- `FRONTEND_STATIC_DIR` is a relative path, so the server must run with `backend/` as the working
  directory. `just run` handles this.
- CORS is wide open (`allow_origins=["*"]`) for local development — tighten it before deploying.
- `pytest-asyncio` runs in `asyncio_mode = "auto"`, so async tests need no explicit marker.
