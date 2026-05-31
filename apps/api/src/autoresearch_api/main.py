from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from autoresearch_api.db.resources import AppResources
from autoresearch_api.health import router as health_router
from autoresearch_api.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    resources = await AppResources.create(get_settings())
    app.state.resources = resources
    try:
        yield
    finally:
        await resources.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Autoresearch Atlas API",
        version="0.1.0",
        description="Control-plane API foundation for database and runtime health.",
        lifespan=lifespan,
    )
    app.include_router(health_router)
    return app


app = create_app()
