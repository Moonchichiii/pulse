"""Background worker — daemon thread running the async event loop.

Spawns one WebSocket consumer per asset class, reads ticks from a
shared queue, and feeds them into PulseStore.  The main FastAPI
process calls ``start_worker()`` on startup and ``stop_worker()``
on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

from pulse.config import parse_symbols
from pulse.feeds import consume_feed
from pulse.models import AssetClass, Tick

if TYPE_CHECKING:
    from pulse.config import Settings
    from pulse.store import PulseStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_thread: threading.Thread | None = None
_loop: asyncio.AbstractEventLoop | None = None
_stop_event: asyncio.Event | None = None


# ---------------------------------------------------------------------------
# Queue dispatcher
# ---------------------------------------------------------------------------


async def _dispatch(
    queue: asyncio.Queue[Tick],
    store: PulseStore,
    stop: asyncio.Event,
) -> None:
    """Read ticks from the queue and push them into the store."""
    while not stop.is_set():
        try:
            tick = await asyncio.wait_for(queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        try:
            store.update(tick)
        except Exception:
            logger.exception("Error updating store for %s", tick.symbol)


# ---------------------------------------------------------------------------
# Async entry point (runs inside the daemon thread)
# ---------------------------------------------------------------------------


async def _run(settings: Settings, store: PulseStore) -> None:
    """Main async function executed in the background thread."""
    stop = asyncio.Event()

    # Make stop event accessible for shutdown
    global _stop_event  # noqa: PLW0603
    _stop_event = stop

    queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=10_000)

    tasks: list[asyncio.Task[None]] = []

    # Dispatcher
    tasks.append(asyncio.create_task(_dispatch(queue, store, stop)))

    # Feed consumers
    stock_syms = parse_symbols(settings.stock_symbols)
    forex_syms = parse_symbols(settings.forex_symbols)
    crypto_syms = parse_symbols(settings.crypto_symbols)

    if settings.eodhd_api_key and stock_syms:
        tasks.append(
            asyncio.create_task(
                consume_feed(
                    AssetClass.STOCK,
                    stock_syms,
                    queue,
                    settings.eodhd_api_key,
                )
            )
        )
        logger.info("Started stock feed: %s", stock_syms)

    if settings.eodhd_api_key and forex_syms:
        tasks.append(
            asyncio.create_task(
                consume_feed(
                    AssetClass.FOREX,
                    forex_syms,
                    queue,
                    settings.eodhd_api_key,
                )
            )
        )
        logger.info("Started forex feed: %s", forex_syms)

    if settings.eodhd_api_key and crypto_syms:
        tasks.append(
            asyncio.create_task(
                consume_feed(
                    AssetClass.CRYPTO,
                    crypto_syms,
                    queue,
                    settings.eodhd_api_key,
                )
            )
        )
        logger.info("Started crypto feed: %s", crypto_syms)

    if not settings.eodhd_api_key:
        logger.warning("EODHD_API_KEY not set — no feeds will connect")

    # Wait until stop is signalled
    await stop.wait()

    # Cancel all tasks
    for task in tasks:
        task.cancel()

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Worker stopped cleanly")


# ---------------------------------------------------------------------------
# Thread entry point
# ---------------------------------------------------------------------------


def _thread_target(settings: Settings, store: PulseStore) -> None:
    """Entry point for the daemon thread."""
    global _loop  # noqa: PLW0603
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_run(settings, store))
    finally:
        _loop.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_worker(settings: Settings, store: PulseStore) -> None:
    """Start the background worker thread.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _thread  # noqa: PLW0603
    if _thread is not None and _thread.is_alive():
        logger.debug("Worker already running")
        return

    _thread = threading.Thread(
        target=_thread_target,
        args=(settings, store),
        daemon=True,
        name="pulse-worker",
    )
    _thread.start()
    logger.info("Worker thread started")


def stop_worker() -> None:
    """Signal the worker to stop and wait for the thread to join."""
    global _thread, _loop, _stop_event  # noqa: PLW0603

    if _stop_event is not None and _loop is not None:
        _loop.call_soon_threadsafe(_stop_event.set)

    if _thread is not None:
        _thread.join(timeout=5.0)
        if _thread.is_alive():
            logger.warning("Worker thread did not stop in time")
        else:
            logger.info("Worker thread joined")

    _thread = None
    _loop = None
    _stop_event = None
