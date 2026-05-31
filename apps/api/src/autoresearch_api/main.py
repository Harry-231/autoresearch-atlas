from fastapi import FastAPI

from autoresearch_api.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Autoresearch Atlas API",
        version="0.1.0",
        description="Control-plane API foundation for database and runtime health.",
    )
    app.include_router(health_router)
    return app


app = create_app()
