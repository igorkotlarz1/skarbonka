"""FastAPI application factory."""

from fastapi import FastAPI

from skarbonka import __version__


def create_app() -> FastAPI:
    """Build the API app. Routers are added here as milestones land."""
    app = FastAPI(title="Skarbonka", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
