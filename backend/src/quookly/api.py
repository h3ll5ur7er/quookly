import os
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.routing import APIRoute

from .access.database import dispose_engine
from .managers.seed import stock_registry
from .routes import (
    accounts_router,
    eaters_router,
    ingredients_router,
    instance_router,
    pantry_router,
    preferences_router,
    recipes_router,
    setup_router,
    status_router,
)
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await stock_registry()
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


app.include_router(status_router, prefix=API_PREFIX, tags=["status"])
app.include_router(accounts_router, prefix=API_PREFIX, tags=["accounts"])
app.include_router(recipes_router, prefix=API_PREFIX, tags=["recipes"])
app.include_router(ingredients_router, prefix=API_PREFIX, tags=["ingredients"])
app.include_router(eaters_router, prefix=API_PREFIX, tags=["eaters"])
app.include_router(setup_router, prefix=API_PREFIX, tags=["setup"])
app.include_router(pantry_router, prefix=API_PREFIX, tags=["pantry"])
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


def export_openapi() -> None:
    import json

    print(json.dumps(app.openapi(), indent=2))
