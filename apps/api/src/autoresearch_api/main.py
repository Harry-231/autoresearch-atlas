from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from autoresearch_api.db.errors import DataConflictError, DataNotFoundError
from autoresearch_api.db.resources import AppResources
from autoresearch_api.health import router as health_router
from autoresearch_api.programs.router import router as programs_router
from autoresearch_api.programs.service import InvalidCursorError
from autoresearch_api.settings import get_settings
from autoresearch_api.tools.router import router as tools_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    resources = await AppResources.create(get_settings())
    app.state.resources = resources
    try:
        yield
    finally:
        await resources.close()


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": message})


def create_app() -> FastAPI:
    app = FastAPI(
        title="Autoresearch Atlas API",
        version="0.1.0",
        description="Control-plane API for programs, the hypothesis DAG, and health.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(programs_router)
    app.include_router(tools_router)

    @app.exception_handler(DataNotFoundError)
    async def _handle_not_found(_: Request, exc: DataNotFoundError) -> JSONResponse:
        return _error_response(404, str(exc))

    @app.exception_handler(DataConflictError)
    async def _handle_conflict(_: Request, exc: DataConflictError) -> JSONResponse:
        return _error_response(409, str(exc))

    @app.exception_handler(InvalidCursorError)
    async def _handle_bad_cursor(_: Request, exc: InvalidCursorError) -> JSONResponse:
        return _error_response(400, str(exc))

    return app


app = create_app()
