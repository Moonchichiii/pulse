"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pulse.config import get_settings
from pulse.store import PulseStore
from pulse.worker import start_worker, stop_worker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

settings = get_settings()
store = PulseStore()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start worker on startup, stop on shutdown."""
    start_worker(settings, store)
    yield
    stop_worker()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title=settings.app_name,
        description="Real-time multi-asset market dashboard",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    application.mount(
        "/static",
        StaticFiles(directory="static"),
        name="static",
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        """Health check endpoint."""
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": "0.1.0",
        }

    return application


app: FastAPI = create_app()
