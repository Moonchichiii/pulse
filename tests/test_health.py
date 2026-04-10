"""Tests for the /health endpoint."""

from httpx import AsyncClient


async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health returns 200 with expected payload."""
    response = await client.get("/health")

    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "pulse"
    assert data["version"] == "0.1.0"


async def test_health_content_type(client: AsyncClient) -> None:
    """GET /health returns JSON content type."""
    response = await client.get("/health")

    assert response.headers["content-type"] == "application/json"
