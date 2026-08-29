import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.routing import APIRoute

from quookly.mcp import AgentSurface

from .access import search
from .access.database import dispose_engine
from .contracts.events import MealCooked
from .managers import pantry
from .managers.seed import (
    place_seeded_foods,
    stock_academy,
    stock_generic_foods,
    stock_nutrition,
    stock_registry,
)
from .routes import (
    academy_router,
    accounts_router,
    cooking_router,
    eaters_router,
    ingredients_router,
    instance_router,
    media_router,
    pantry_router,
    plans_router,
    preferences_router,
    recipes_router,
    setup_router,
    status_router,
)
from .utilities import events
from .utilities.diagnostics import configure_logging, get_logger, use_request_id

REQUEST_ID_HEADER = "X-Request-ID"

request_log = get_logger("request")

FRONTEND_STATIC_DIR = "src/quookly/app/browser/"
API_PREFIX = "/api/v1"

CONTROL_SETS: dict[str | Enum, set[str]] = {}


def endpoint_name_generator(route: APIRoute) -> str:
    name = "".join(
        map(
            lambda arg: arg[1] if arg[0] == 0 else arg[1].capitalize(),
            enumerate(route.name.split("_")),
        )
    )
    for tag in route.tags:
        if tag not in CONTROL_SETS:
            CONTROL_SETS[tag] = set()
        if name in CONTROL_SETS[tag]:
            raise ValueError(f"Duplicate route name: {name}. Please ensure unique route names.")
        CONTROL_SETS[tag].add(name)
    return f"{name}"


def wire_subscriptions() -> None:
    """Say who listens for what.

    Here rather than at the bottom of a manager, because this is where the application is
    assembled and a subscription made as an import side effect is a subscription nobody
    can find. It is also the only place that knows about two managers at once — which is
    exactly what the bus exists to keep out of the managers themselves.
    """
    events.forget_everything()
    events.subscribe(MealCooked, pantry.on_meal_cooked)


#: What is mounted at `/mcp` (ADR-068). Stable, because a mount is; the surface behind it
#: is built by the lifespan, because a transport's session manager may be run once and an
#: application that could only be started once would be a strange thing to ship.
_agents = AgentSurface()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    wire_subscriptions()
    await stock_registry()
    # After the hand-written set, so the starter owns every name it wants. Separate from
    # `stock_registry` because it answers a different question: that one makes sure the
    # starter recipes have ingredients to point at, and a cook being let in needs it. This
    # is the instance's reference data, and it is nobody's dependency.
    await stock_generic_foods()
    # After both registries, because it places what they added. The generic foods arrive
    # already in the tree; the hand-written starter set is the half a recipe actually
    # names, and without this a fresh instance's shopping list has every line under
    # "anything else" (ADR-067).
    await place_seeded_foods()
    await stock_nutrition()
    # Reference material rather than anybody's dependency, like the generic foods:
    # every screen works without it, and a cook meeting an unfamiliar word does not.
    await stock_academy()
    # Derived, so it is rebuilt rather than migrated: a change to what is indexed then
    # costs nothing to roll out and cannot be half-applied.
    await search.reindex()
    # The MCP transport keeps per-session state and wants a lifespan of its own. Run inside
    # this one rather than beside it: there is one process, and that is the whole point of
    # serving an agent from here rather than from a second client (ADR-068).
    async with _agents.running():
        yield
    await dispose_engine()


NAME = "Quookly API"
app = FastAPI(title=NAME, lifespan=lifespan, generate_unique_id_function=endpoint_name_generator)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlate_and_log(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Give every request an id, and log how it went.

    An id supplied upstream is adopted rather than replaced, so a trace that started at
    a proxy stays whole. The request body is never logged — that is what keeps
    passwords out of the log rather than a filter that has to be remembered.
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    started = time.perf_counter()
    with use_request_id(request_id):
        response = await call_next(request)
        request_log.info(
            "%s %s -> %s",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


# Quookly as tools an agent can use, at `/mcp`, over the Streamable HTTP transport. A
# Client like the routers below and at the same layer: its tools call managers, and it
# authenticates with the same bearer token they do (ADR-068).
app.mount("/mcp", _agents)

app.include_router(status_router, prefix=API_PREFIX, tags=["status"])
app.include_router(accounts_router, prefix=API_PREFIX, tags=["accounts"])
app.include_router(recipes_router, prefix=API_PREFIX, tags=["recipes"])
app.include_router(ingredients_router, prefix=API_PREFIX, tags=["ingredients"])
app.include_router(academy_router, prefix=API_PREFIX, tags=["academy"])
app.include_router(media_router, prefix=API_PREFIX, tags=["media"])
app.include_router(eaters_router, prefix=API_PREFIX, tags=["eaters"])
app.include_router(setup_router, prefix=API_PREFIX, tags=["setup"])
app.include_router(pantry_router, prefix=API_PREFIX, tags=["pantry"])
app.include_router(plans_router, prefix=API_PREFIX, tags=["plans"])
app.include_router(cooking_router, prefix=API_PREFIX, tags=["cooking"])
app.include_router(preferences_router, prefix=API_PREFIX, tags=["preferences"])
app.include_router(instance_router, prefix=API_PREFIX, tags=["instance"])


@app.get("/")
def read_root() -> RedirectResponse:
    return RedirectResponse(url="/index.html")


@app.exception_handler(404)
def serve_frontend_or_report_missing(request: Request, exc: Exception) -> Response:
    """Fall back to the single-page application for client-side routes.

    The API is excluded. Turning an API 404 into a page of HTML with a 200 status leaves
    a client unable to tell "no such recipe" from success, and generated clients would
    parse the index page as a response body.
    """
    if request.url.path.startswith(f"{API_PREFIX}/"):
        detail = getattr(exc, "detail", "Not found.")
        return JSONResponse(status_code=404, content={"detail": detail})

    requested = FRONTEND_STATIC_DIR + request.scope["path"].lstrip("/")
    if "." in request.url.path and os.path.isfile(requested):
        return FileResponse(requested)
    return FileResponse(FRONTEND_STATIC_DIR + "index.html")


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("quookly.api:app", host="0.0.0.0", port=port, reload=True)


def _also_say_binary_the_old_way(schema: Any) -> None:
    """Mark a binary property with OpenAPI 3.0's `format` as well as 3.1's.

    FastAPI emits 3.1, which describes an upload as `contentMediaType`. The
    openapi-generator this project uses to build both clients reads 3.0's
    `format: "binary"` and nothing else, so without this it does not recognise a file at
    all: the Angular client URL-encodes the `File` through `HttpParams` and the server
    sees the string `[object File]`.

    Both keys together, rather than downgrading the whole document to 3.0. A 3.1 reader
    ignores `format` here and a 3.0 one ignores `contentMediaType`, so the contract says
    the same thing to both — and every upload endpoint after this one is covered without
    anybody remembering.
    """
    if isinstance(schema, dict):
        if schema.get("contentMediaType") == "application/octet-stream":
            schema.setdefault("format", "binary")
        for value in schema.values():
            _also_say_binary_the_old_way(value)
    elif isinstance(schema, list):
        for value in schema:
            _also_say_binary_the_old_way(value)


def export_openapi() -> None:
    import json

    document = app.openapi()
    _also_say_binary_the_old_way(document)
    print(json.dumps(document, indent=2))
