"""FastAPI application factory."""

from fastapi import FastAPI

from skarbonka import __version__
from skarbonka.api.categorization import router as categorization_router
from skarbonka.api.imports import router as imports_router
from skarbonka.api.transactions import router as transactions_router


def create_app() -> FastAPI:
    """Build the API app. Routers are added here as milestones land."""
    app = FastAPI(title="Skarbonka", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(imports_router)
    app.include_router(categorization_router)
    app.include_router(transactions_router)
    return app


app = create_app()
