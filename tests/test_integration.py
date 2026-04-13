"""End-to-end integration test."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from pulse.config import Settings
from pulse.correlation import CorrelationEngine
from pulse.detector import StressDetector
from pulse.events import EventStore
from pulse.main import create_app
from pulse.models import AssetClass, Tick
from pulse.store import PulseStore

if TYPE_CHECKING:
    from fastapi import FastAPI


@pytest.fixture
def test_settings() -> Settings:
    """Settings for integration test (no real API key needed)."""
    return Settings(
        eodhd_api_key="test_key",
        stock_symbols="AAPL,MSFT",
        forex_symbols="EURUSD",
        crypto_symbols="BTC-USD",
    )


@pytest.fixture
async def integration_app(test_settings: Settings) -> FastAPI:
    """Create app without starting background worker."""
    app = create_app()

    # Override state with fresh instances
    app.state.store = PulseStore()
    app.state.event_store = EventStore()
    app.state.detector = StressDetector(app.state.event_store)
    app.state.correlation_engine = CorrelationEngine(app.state.store)

    return app


@pytest.mark.asyncio
async def test_full_flow(integration_app: FastAPI) -> None:
    """Test complete flow: ingest → metrics → events → HTTP."""
    store: PulseStore = integration_app.state.store
    detector: StressDetector = integration_app.state.detector

    # Inject synthetic ticks
    now = time.time()
    ticks = [
        Tick(
            symbol="AAPL",
            price=150.0,
            timestamp=now - 60,
            asset_class=AssetClass.STOCK,
        ),
        Tick(
            symbol="AAPL",
            price=151.5,
            timestamp=now - 30,
            asset_class=AssetClass.STOCK,
        ),
        Tick(
            symbol="AAPL",
            price=155.0,
            timestamp=now,
            asset_class=AssetClass.STOCK,
        ),
        Tick(
            symbol="MSFT",
            price=300.0,
            timestamp=now - 60,
            asset_class=AssetClass.STOCK,
        ),
        Tick(
            symbol="MSFT",
            price=301.0,
            timestamp=now - 30,
            asset_class=AssetClass.STOCK,
        ),
        Tick(
            symbol="MSFT",
            price=302.0,
            timestamp=now,
            asset_class=AssetClass.STOCK,
        ),
    ]

    for tick in ticks:
        metrics = store.update(tick)
        detector.check(metrics)

    # Verify store state
    snapshot = store.snapshot()
    assert len(snapshot) == 2
    assert "AAPL" in snapshot
    assert "MSFT" in snapshot
    assert snapshot["AAPL"].price == 155.0
    assert snapshot["AAPL"].ret_1m is not None

    # Verify HTTP endpoints work
    async with AsyncClient(
        transport=ASGITransport(app=integration_app),
        base_url="http://test",
    ) as client:
        # Test index page
        response = await client.get("/")
        assert response.status_code == 200
        assert "Market Pulse" in response.text

        # Test correlation fragment
        response = await client.get("/fragments/corr?base_symbol=AAPL")
        assert response.status_code == 200
        assert "AAPL" in response.text or "Accumulating" in response.text


@pytest.mark.asyncio
async def test_sse_pulse_stream(integration_app: FastAPI) -> None:
    """Test pulse SSE stream emits HTML."""
    from unittest.mock import AsyncMock

    from pulse.routes import _pulse_gen

    store: PulseStore = integration_app.state.store

    # Add tick
    now = time.time()
    tick = Tick(
        symbol="AAPL",
        price=150.0,
        timestamp=now,
        asset_class=AssetClass.STOCK,
    )
    store.update(tick)

    # Mock request
    mock_request = AsyncMock()
    mock_request.is_disconnected = AsyncMock(return_value=False)
    mock_request.app.state.store = store

    gen = _pulse_gen(store, mock_request)

    # Get first event (with timeout)
    try:
        event = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
        assert event["event"] == "pulse"
        assert "AAPL" in event["data"]
    except TimeoutError:
        pytest.fail("SSE stream did not emit event within 2 seconds")


@pytest.mark.asyncio
async def test_stress_detection_in_flow(integration_app: FastAPI) -> None:
    """Test stress events fire and appear in EventStore."""
    store: PulseStore = integration_app.state.store
    detector: StressDetector = integration_app.state.detector
    event_store: EventStore = integration_app.state.event_store

    # Inject large move
    now = time.time()
    ticks = [
        Tick(
            symbol="BTC-USD",
            price=40000.0,
            timestamp=now - 60,
            asset_class=AssetClass.CRYPTO,
        ),
        Tick(
            symbol="BTC-USD",
            price=42000.0,
            timestamp=now,
            asset_class=AssetClass.CRYPTO,
        ),
    ]

    for tick in ticks:
        metrics = store.update(tick)
        detector.check(metrics)

    # Verify event fired
    events = event_store.recent(10)
    assert len(events) > 0
    assert events[0].symbol == "BTC-USD"


@pytest.mark.asyncio
async def test_correlation_engine_integration(
    integration_app: FastAPI,
) -> None:
    """Test correlation engine with real store data."""
    store: PulseStore = integration_app.state.store

    # Add correlated data
    now = time.time()
    for i in range(20):
        ts = now - (19 - i) * 10  # 10s intervals
        price_aapl = 100.0 + i * 0.5
        price_msft = 200.0 + i * 0.5

        store.update(
            Tick(
                symbol="AAPL",
                price=price_aapl,
                timestamp=ts,
                asset_class=AssetClass.STOCK,
            )
        )
        store.update(
            Tick(
                symbol="MSFT",
                price=price_msft,
                timestamp=ts,
                asset_class=AssetClass.STOCK,
            )
        )

    # Compute correlation
    engine = CorrelationEngine(store, base_symbol="AAPL", bucket_size=10)
    result = engine.compute()

    assert len(result) > 0
    assert "MSFT" in result
    # Should be highly correlated (both rising together)
    assert result["MSFT"] > 0.9
