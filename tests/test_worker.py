"""Tests for the background worker module."""

from __future__ import annotations

import asyncio

import pytest

from pulse.models import AssetClass, Tick
from pulse.store import PulseStore
from pulse.worker import _dispatch


@pytest.fixture
def store() -> PulseStore:
    return PulseStore()


class TestDispatch:
    async def test_dispatch_processes_ticks(self, store: PulseStore) -> None:
        """Dispatcher should read ticks from queue into store."""
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        stop = asyncio.Event()

        tick = Tick(
            symbol="AAPL",
            price=150.0,
            timestamp=1_700_000_000.0,
            volume=100.0,
            asset_class=AssetClass.STOCK,
        )
        await queue.put(tick)

        # Run dispatcher briefly then stop
        task = asyncio.create_task(_dispatch(queue, store, stop))
        await asyncio.sleep(0.1)
        stop.set()
        await task

        assert "AAPL" in store.symbols
        assert store.tick_count("AAPL") == 1

    async def test_dispatch_stops_on_event(self, store: PulseStore) -> None:
        """Dispatcher should exit when stop event is set."""
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        stop = asyncio.Event()

        task = asyncio.create_task(_dispatch(queue, store, stop))
        stop.set()
        await asyncio.wait_for(task, timeout=3.0)

        assert store.symbols == []

    async def test_dispatch_handles_multiple_ticks(
        self, store: PulseStore
    ) -> None:
        """Dispatcher should process all queued ticks."""
        queue: asyncio.Queue[Tick] = asyncio.Queue()
        stop = asyncio.Event()

        for i in range(5):
            tick = Tick(
                symbol="MSFT",
                price=400.0 + i,
                timestamp=1_700_000_000.0 + i,
                volume=None,
                asset_class=AssetClass.STOCK,
            )
            await queue.put(tick)

        task = asyncio.create_task(_dispatch(queue, store, stop))
        await asyncio.sleep(0.2)
        stop.set()
        await task

        assert store.tick_count("MSFT") == 5
