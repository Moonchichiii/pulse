"""Dashboard routes — index page, SSE streams, HTMX fragments."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi.responses import Response

    from pulse.correlation import CorrelationEngine
    from pulse.events import EventStore
    from pulse.store import PulseStore

logger = logging.getLogger(__name__)
router = APIRouter()
templates: Jinja2Templates  # assigned by init_templates()


def init_templates(directory: str) -> None:
    """Configure Jinja2Templates and register custom filters."""
    global templates  # noqa: PLW0603
    templates = Jinja2Templates(directory=directory)

    def fmt_price(value: float | None) -> str:
        if value is None:
            return "—"
        if value >= 100:  # noqa: PLR2004
            return f"{value:,.2f}"
        if value >= 1:
            return f"{value:.4f}"
        return f"{value:.6f}"

    def fmt_pct(value: float | None) -> str:
        if value is None:
            return "—"
        return f"{value * 100:+.3f}%"

    def ret_color(value: float | None) -> str:
        if value is None:
            return "text-gray-700"
        pct = abs(value * 100)
        if value > 0:
            if pct >= 1.0:
                return "text-emerald-300 font-semibold"
            if pct >= 0.3:
                return "text-emerald-400"
            return "text-emerald-600"
        if pct >= 1.0:
            return "text-red-300 font-semibold"
        if pct >= 0.3:
            return "text-red-400"
        return "text-red-600"

    def fmt_time(ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=UTC).strftime("%H:%M:%S")

    def abs_filter(value: float) -> float:
        return abs(value)

    templates.env.filters["fmt_price"] = fmt_price
    templates.env.filters["fmt_pct"] = fmt_pct
    templates.env.filters["ret_color"] = ret_color
    templates.env.filters["fmt_time"] = fmt_time
    templates.env.filters["abs"] = abs_filter


def _render(template_name: str, context: dict[object, object]) -> str:
    """Render a Jinja2 template to a string."""
    tmpl = templates.get_template(template_name)
    return str(tmpl.render(context))


async def _pulse_gen(
    store: PulseStore, request: Request
) -> AsyncIterator[dict[str, str]]:
    """SSE generator for pulse updates — yields pulse events."""
    while True:
        if await request.is_disconnected():
            break
        metrics = sorted(store.snapshot().values(), key=lambda m: m.symbol)
        html = _render("fragments/pulse_rows.html", {"metrics": metrics})
        yield {"event": "pulse", "data": html}
        await asyncio.sleep(1.0)


async def _stress_gen(
    event_store: EventStore, request: Request
) -> AsyncIterator[dict[str, str]]:
    """SSE generator for stress events — yields stress events."""
    while True:
        if await request.is_disconnected():
            break
        events = list(reversed(event_store.recent(20)))
        html = _render("fragments/stress_feed.html", {"events": events})
        yield {"event": "stress", "data": html}
        await asyncio.sleep(2.0)


@router.get("/")
async def index(request: Request) -> Response:
    """Render the main dashboard page."""
    store: PulseStore = request.app.state.store
    correlation_engine: CorrelationEngine = request.app.state.correlation_engine
    base_symbol: str = correlation_engine.base_symbol

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "base_symbol": base_symbol,
            "symbol_count": len(store.symbols),
        },
    )


@router.get("/stream/pulse")
async def stream_pulse(request: Request) -> EventSourceResponse:
    """SSE stream: push pulse_rows.html fragment on event 'pulse'."""
    store: PulseStore = request.app.state.store
    return EventSourceResponse(_pulse_gen(store, request))


@router.get("/stream/stress")
async def stream_stress(request: Request) -> EventSourceResponse:
    """SSE stream: push stress_feed.html fragment on event 'stress'."""
    event_store: EventStore = request.app.state.event_store
    return EventSourceResponse(_stress_gen(event_store, request))


@router.get("/fragments/corr")
async def fragment_corr(request: Request) -> Response:
    """HTMX polling fragment: correlation table partial."""
    correlation_engine: CorrelationEngine = request.app.state.correlation_engine
    base_symbol: str = correlation_engine.base_symbol

    correlations: dict[str, float] = {}
    try:
        correlations = correlation_engine.compute()
    except Exception:
        logger.exception("Correlation compute error")

    correlations.pop(base_symbol, None)

    return templates.TemplateResponse(
        request,
        "fragments/correlation_card.html",
        {
            "correlations": correlations,
            "base_symbol": base_symbol,
            "computed_at": time.time(),
        },
    )
