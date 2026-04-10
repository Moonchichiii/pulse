"""Shared test fixtures."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from pulse.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Async test client for the FastAPI application."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as ac:
        yield ac
