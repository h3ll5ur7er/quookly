import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.routing import APIRoute

from .routes import accounts_router, status_router

FRONTEND_STATIC_DIR = "src/quookly/app/browser/"

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
    # Perform any startup tasks here
    yield
    # Perform any shutdown tasks here


NAME = "Quookly API"
app = FastAPI(title=NAME, lifespan=lifespan, generate_unique_id_function=endpoint_name_generator)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(status_router, prefix="/api/v1", tags=["status"])
app.include_router(accounts_router, prefix="/api/v1", tags=["accounts"])


@app.get("/")
def read_root() -> RedirectResponse:
    return RedirectResponse(url="/index.html")


@app.exception_handler(404)
def custom_404_handler(request: Request, exc: Exception) -> Response:
    if "." not in request.url.path:
        return FileResponse(FRONTEND_STATIC_DIR + "index.html")
    try:
        path = FRONTEND_STATIC_DIR + request.scope["path"].lstrip("/")
        if not os.path.isfile(path):
            print("File not found:", path)
            return FileResponse(FRONTEND_STATIC_DIR + "index.html")
        return FileResponse(path)
    except Exception as e:
        print("Error serving file:", e)
        return FileResponse(FRONTEND_STATIC_DIR + "index.html")


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("quookly.api:app", host="0.0.0.0", port=port, reload=True)


def export_openapi() -> None:
    import json

    print(json.dumps(app.openapi(), indent=2))
