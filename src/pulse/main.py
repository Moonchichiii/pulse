"""FastAPI application factory and top-level routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pulse.config import Settings
from pulse.store import PulseStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

settings = Settings()
store = PulseStore()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start worker on startup, stop on shutdown."""
    from pulse.worker import start_worker, stop_worker

    start_worker(settings, store)
    yield
    stop_worker()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
