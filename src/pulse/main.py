"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pulse.config import get_settings
from pulse.correlation import CorrelationEngine
from pulse.detector import StressDetector
from pulse.events import EventStore
from pulse.routes import init_templates, router
from pulse.store import PulseStore
from pulse.worker import start_worker, stop_worker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

settings = get_settings()
store = PulseStore()
event_store = EventStore()
detector = StressDetector(event_store)
correlation_engine = CorrelationEngine(store)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start worker on startup, stop on shutdown."""
    start_worker(settings, store, detector)
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

    # ── Static files (skip if directory absent — e.g. during tests) ──────────
    _static_dir = os.path.join(os.getcwd(), "static")
    if os.path.isdir(_static_dir):
        application.mount(
            "/static",
            StaticFiles(directory=_static_dir),
            name="static",
        )

    # ── Jinja2 templates ─────────────────────────────────────────────────────
    _pkg_dir = os.path.dirname(__file__)
    _template_dir = os.path.join(_pkg_dir, "templates")
    init_templates(_template_dir)

    # ── App state ─────────────────────────────────────────────────────────────
    application.state.store = store
    application.state.event_store = event_store
    application.state.detector = detector
    application.state.correlation_engine = correlation_engine

    # ── Routers ───────────────────────────────────────────────────────────────
    application.include_router(router)

    # ── Built-in endpoints ───────────────────────────────────────────────────
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
