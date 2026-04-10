"""Tests for the background worker dispatch loop."""

from __future__ import annotations

import asyncio

from pulse.detector import StressDetector
from pulse.events import EventStore
from pulse.models import AssetClass, Tick
from pulse.store import PulseStore
from pulse.worker import _dispatch

_BASE_TS = 1_700_000_000.0


def _tick(
    symbol: str = "AAPL",
    price: float = 150.0,
    timestamp: float = _BASE_TS,
) -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        timestamp=timestamp,
        volume=100.0,
        asset_class=AssetClass.STOCK,
    )


class TestDispatch:
    async def test_dispatch_processes_ticks(self) -> None:
        store = PulseStore()
        detector = StressDetector(EventStore())
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        stop = asyncio.Event()

        await queue.put(_tick())

        task = asyncio.create_task(_dispatch(queue, store, detector, stop))
        await asyncio.sleep(0.05)
        stop.set()
        await task

        assert "AAPL" in store.symbols
        assert store.tick_count("AAPL") == 1

    async def test_dispatch_stops_on_event(self) -> None:
        store = PulseStore()
        detector = StressDetector(EventStore())
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        stop = asyncio.Event()
        stop.set()

        await _dispatch(queue, store, detector, stop)

        assert store.symbols == []

    async def test_dispatch_handles_multiple_ticks(self) -> None:
        store = PulseStore()
        detector = StressDetector(EventStore())
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        stop = asyncio.Event()

        for i in range(5):
            await queue.put(_tick(price=150.0 + i, timestamp=_BASE_TS + i))

        task = asyncio.create_task(_dispatch(queue, store, detector, stop))
        await asyncio.sleep(0.05)
        stop.set()
        await task

        assert store.tick_count("AAPL") == 5

    async def test_dispatch_triggers_stress_detection(self) -> None:
        store = PulseStore()
        es = EventStore()
        detector = StressDetector(es)
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        stop = asyncio.Event()

        # Two ticks with a huge price jump to trigger move_1m
        await queue.put(_tick(price=100.0, timestamp=_BASE_TS))
        await queue.put(_tick(price=200.0, timestamp=_BASE_TS + 30))

        task = asyncio.create_task(_dispatch(queue, store, detector, stop))
        await asyncio.sleep(0.05)
        stop.set()
        await task

        assert es.count >= 1
