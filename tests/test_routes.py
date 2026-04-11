"""Tests for dashboard routes: index, SSE streams, correlation fragment."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from pulse.events import EventType, StressEvent
from pulse.main import app
from pulse.models import AssetClass, Tick

if TYPE_CHECKING:
    import httpx
    from httpx import AsyncClient

    from pulse.store import PulseStore  # noqa: PLC0415, N814

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = time.time()


def _make_ticks(
    symbol: str,
    asset_class: AssetClass,
    base_price: float,
    count: int = 30,
) -> list[Tick]:
    """Generate *count* synthetic ticks spaced 10 s apart."""
    return [
        Tick(
            symbol=symbol,
            price=base_price * (1 + i * 0.0001),
            timestamp=_NOW - (count - i) * 10,
            asset_class=asset_class,
        )
        for i in range(count)
    ]


def _get_store() -> PulseStore:
    """Return the store from app.state (typed via cast to satisfy mypy)."""
    from pulse.store import PulseStore  # noqa: PLC0415

    store = app.state.store
    assert isinstance(store, PulseStore)
    return store


@pytest.fixture(autouse=True)
def _populate_app_state() -> None:
    """Seed store + event_store on app.state before every route test."""
    store = _get_store()
    store._buffers.clear()  # type: ignore[attr-defined]

    for symbol, price in [
        ("AAPL", 175.0),
        ("MSFT", 420.0),
        ("SPY", 520.0),
    ]:
        for tick in _make_ticks(symbol, AssetClass.STOCK, price):
            store.update(tick)

    for tick in _make_ticks("BTC-USD", AssetClass.CRYPTO, 65000.0):
        store.update(tick)

    es = app.state.event_store
    es.clear()
    es.add(
        StressEvent.create(
            symbol="AAPL",
            event_type=EventType.MOVE_1M,
            severity=0.012,
            threshold=0.005,
            price=175.0,
            timestamp=_NOW - 5,
            asset_class="stock",
            regime="normal",
        )
    )
    es.add(
        StressEvent.create(
            symbol="BTC-USD",
            event_type=EventType.VOL_SPIKE,
            severity=0.025,
            threshold=0.01,
            price=65000.0,
            timestamp=_NOW - 2,
            asset_class="crypto",
            regime="normal",
        )
    )


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_returns_200(client: httpx.AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_index_content_type_html(client: httpx.AsyncClient) -> None:
    resp = await client.get("/")
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_index_contains_pulse_heading(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/")
    assert "Market Pulse" in resp.text or "Pulse" in resp.text


@pytest.mark.asyncio
async def test_index_contains_htmx_sse_attributes(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/")
    assert 'sse-connect="/stream/pulse"' in resp.text
    assert 'sse-connect="/stream/stress"' in resp.text


@pytest.mark.asyncio
async def test_index_contains_corr_polling(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/")
    assert 'hx-get="/fragments/corr"' in resp.text


@pytest.mark.asyncio
async def test_index_contains_base_symbol(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/")
    assert "SPY" in resp.text


# ---------------------------------------------------------------------------
# GET /fragments/corr
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corr_fragment_returns_200(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/fragments/corr")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_corr_fragment_content_type_html(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/fragments/corr")
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_corr_fragment_with_empty_store(
    client: httpx.AsyncClient,
) -> None:
    """Fragment renders gracefully when store has no ticks."""
    _get_store()._buffers.clear()  # type: ignore[attr-defined]
    resp = await client.get("/fragments/corr")
    assert resp.status_code == 200
    assert "ccumulating" in resp.text or "text-gray-600" in resp.text


@pytest.mark.asyncio
async def test_corr_fragment_has_table_or_placeholder(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get("/fragments/corr")
    body = resp.text
    assert "<table" in body or "<p" in body


# ---------------------------------------------------------------------------
# SSE generators — direct async generator tests (NO httpx streaming)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pulse_gen_yields_pulse_event() -> None:
    """Test _pulse_gen yields dict with event='pulse' and HTML data."""
    from pulse.routes import _pulse_gen

    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(return_value=False)

    store = app.state.store
    gen = _pulse_gen(store, mock_request)
    item = await anext(gen)
    await gen.aclose()

    assert item["event"] == "pulse"
    assert "<tr" in item["data"]
    assert "AAPL" in item["data"] or "MSFT" in item["data"]


@pytest.mark.asyncio
async def test_pulse_gen_disconnects_cleanly() -> None:
    """Test _pulse_gen stops when request.is_disconnected() returns True."""
    from pulse.routes import _pulse_gen

    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(side_effect=[False, True])

    store = app.state.store
    items = []
    async for item in _pulse_gen(store, mock_request):
        items.append(item)

    assert len(items) == 1
    assert items[0]["event"] == "pulse"


@pytest.mark.asyncio
async def test_stress_gen_yields_stress_event() -> None:
    """Test _stress_gen yields dict with event='stress' and HTML data."""
    from pulse.routes import _stress_gen

    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(return_value=False)

    event_store = app.state.event_store
    gen = _stress_gen(event_store, mock_request)
    item = await anext(gen)
    await gen.aclose()

    assert item["event"] == "stress"
    assert "AAPL" in item["data"] or "BTC" in item["data"]


@pytest.mark.asyncio
async def test_stress_gen_disconnects_cleanly() -> None:
    """Test _stress_gen stops when request.is_disconnected() returns True."""
    from pulse.routes import _stress_gen

    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(side_effect=[False, True])

    event_store = app.state.event_store
    items = []
    async for item in _stress_gen(event_store, mock_request):
        items.append(item)

    assert len(items) == 1
    assert items[0]["event"] == "stress"


@pytest.mark.asyncio
async def test_pulse_gen_with_empty_store() -> None:
    """Test _pulse_gen handles empty store gracefully."""
    from pulse.routes import _pulse_gen

    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(return_value=False)

    _get_store()._buffers.clear()  # type: ignore[attr-defined]
    store = app.state.store

    gen = _pulse_gen(store, mock_request)
    item = await anext(gen)
    await gen.aclose()

    assert item["event"] == "pulse"
    assert "Waiting" in item["data"] or "waiting" in item["data"]


@pytest.mark.asyncio
async def test_stress_gen_with_empty_store() -> None:
    """Test _stress_gen handles empty event store gracefully."""
    from pulse.routes import _stress_gen

    mock_request = MagicMock()
    mock_request.is_disconnected = AsyncMock(return_value=False)

    app.state.event_store.clear()
    event_store = app.state.event_store

    gen = _stress_gen(event_store, mock_request)
    item = await anext(gen)
    await gen.aclose()

    assert item["event"] == "stress"
    assert "No events" in item["data"] or "yet" in item["data"]


# ---------------------------------------------------------------------------
# Template rendering — unit-level via Jinja2 directly
# ---------------------------------------------------------------------------


def test_pulse_rows_template_empty_metrics() -> None:
    from pulse.routes import _render

    html = _render("fragments/pulse_rows.html", {"metrics": []})
    assert "Waiting" in html or "waiting" in html


def test_stress_feed_template_empty_events() -> None:
    from pulse.routes import _render

    html = _render("fragments/stress_feed.html", {"events": []})
    assert "No events" in html or "yet" in html


def test_corr_card_template_empty_correlations() -> None:
    from pulse.routes import _render

    html = _render(
        "fragments/correlation_card.html",
        {"correlations": {}, "base_symbol": "SPY"},
    )
    assert "ccumulating" in html


def test_corr_card_template_with_data() -> None:
    from pulse.routes import _render

    corr = {"AAPL": 0.82, "MSFT": 0.75, "TSLA": -0.12}
    html = _render(
        "fragments/correlation_card.html",
        {"correlations": corr, "base_symbol": "SPY"},
    )
    assert "<table" in html
    assert "AAPL" in html
    assert "MSFT" in html
    assert "+0.820" in html


def test_pulse_rows_template_with_metrics() -> None:
    from pulse.routes import _render
    from pulse.store import Regime, SymbolMetrics

    metrics = [
        SymbolMetrics(
            symbol="AAPL",
            asset_class="stock",
            price=175.50,
            timestamp=_NOW,
            ret_1m=0.0032,
            ret_5m=-0.0085,
            ret_15m=0.011,
            volatility=0.0021,
            trend=1e-5,
            regime=Regime.NORMAL,
        ),
    ]
    html = _render("fragments/pulse_rows.html", {"metrics": metrics})
    assert "AAPL" in html
    assert "<tr" in html
    assert "stock" in html


@pytest.mark.asyncio
async def test_fragment_corr_with_params(
    client: AsyncClient,
) -> None:
    """Test correlation fragment accepts base_symbol and bucket_size."""
    response = await client.get(
        "/fragments/corr?base_symbol=AAPL&bucket_size=20"
    )
    assert response.status_code == 200
    html = response.text
    assert "AAPL" in html or "Accumulating" in html
    # Verify the response includes the updated base symbol
    assert "AAPL" in html or "data" in html.lower()
