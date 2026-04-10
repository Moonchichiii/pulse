"""FastAPI application entry point."""

from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pulse.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title="Pulse",
        description="Real-time multi-asset market dashboard",
        version="0.1.0",
        debug=settings.debug,
    )

    application.mount(
        "/static",
        StaticFiles(directory="static"),
        name="static",
    )

    @application.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": "0.1.0",
        }

    return application


app: FastAPI = create_app()
