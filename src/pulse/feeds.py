"""EODHD WebSocket feed consumers.

Each consumer connects to one asset-class feed, subscribes to the
configured symbols, parses incoming ticks, and pushes them onto a
shared asyncio queue for downstream processing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import TYPE_CHECKING

from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, WebSocketException

if TYPE_CHECKING:
    from collections.abc import Callable

from pulse.models import AssetClass, Tick

logger = logging.getLogger(__name__)

EODHD_WS_BASE = "wss://ws.eodhistoricaldata.com/ws"

FEED_PATHS: dict[AssetClass, str] = {
    AssetClass.STOCK: "us",
    AssetClass.FOREX: "forex",
    AssetClass.CRYPTO: "crypto",
}

_BASE_DELAY = 1.0
_MAX_DELAY = 60.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_float(v: object) -> float:
    """Narrow an unknown JSON value to float (mypy-safe)."""
    if isinstance(v, float):
        return v
    if isinstance(v, int):
        return float(v)
    return float(str(v))


def _as_str(v: object) -> str:
    """Narrow an unknown JSON value to str (mypy-safe)."""
    if isinstance(v, str):
        return v
    return str(v)


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter."""
    delay = float(min(_BASE_DELAY * (2**attempt), _MAX_DELAY))
    jitter = delay * 0.1 * random.random()  # noqa: S311
    return delay + jitter


# ---------------------------------------------------------------------------
# Parsers — one per asset class, pure functions for easy testing
# ---------------------------------------------------------------------------


def parse_stock_tick(raw: dict[str, object]) -> Tick | None:
    """Parse an EODHD stock tick message."""
    try:
        symbol = _as_str(raw["s"]).split(".")[0]
        price = _as_float(raw["p"])
        timestamp = _as_float(raw["t"]) / 1000.0
        vol_raw = raw.get("v")
        volume = _as_float(vol_raw) if vol_raw is not None else None
        return Tick(
            symbol=symbol,
            price=price,
            timestamp=timestamp,
            volume=volume,
            asset_class=AssetClass.STOCK,
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("Bad stock tick: %s — %s", raw, exc)
        return None


def parse_forex_tick(raw: dict[str, object]) -> Tick | None:
    """Parse an EODHD forex tick message (mid-price from bid/ask)."""
    try:
        symbol = _as_str(raw["s"]).split(".")[0]
        ask = _as_float(raw["a"])
        bid = _as_float(raw["b"])
        price = (ask + bid) / 2.0
        timestamp = _as_float(raw["t"]) / 1000.0
        return Tick(
            symbol=symbol,
            price=price,
            timestamp=timestamp,
            volume=None,
            asset_class=AssetClass.FOREX,
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("Bad forex tick: %s — %s", raw, exc)
        return None


def parse_crypto_tick(raw: dict[str, object]) -> Tick | None:
    """Parse an EODHD crypto tick message."""
    try:
        symbol = _as_str(raw["s"]).split(".")[0]
        price = _as_float(raw["p"])
        timestamp = _as_float(raw["t"]) / 1000.0
        qty_raw = raw.get("q")
        volume = _as_float(qty_raw) if qty_raw is not None else None
        return Tick(
            symbol=symbol,
            price=price,
            timestamp=timestamp,
            volume=volume,
            asset_class=AssetClass.CRYPTO,
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("Bad crypto tick: %s — %s", raw, exc)
        return None


PARSERS: dict[AssetClass, Callable[[dict[str, object]], Tick | None]] = {
    AssetClass.STOCK: parse_stock_tick,
    AssetClass.FOREX: parse_forex_tick,
    AssetClass.CRYPTO: parse_crypto_tick,
}


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------


async def consume_feed(
    asset_class: AssetClass,
    symbols: list[str],
    queue: asyncio.Queue[Tick],
    api_key: str,
    *,
    max_retries: int = -1,
) -> None:
    """Connect to an EODHD WebSocket feed and push ticks to *queue*.

    Reconnects with exponential backoff on failure.
    ``max_retries=-1`` means retry forever (production default).
    """
    path = FEED_PATHS[asset_class]
    url = f"{EODHD_WS_BASE}/{path}?api_token={api_key}"
    parser = PARSERS[asset_class]
    attempt = 0

    while max_retries == -1 or attempt <= max_retries:
        try:
            async with ws_connect(url) as ws:
                logger.info(
                    "Connected to %s feed (%d symbols)",
                    asset_class.value,
                    len(symbols),
                )
                attempt = 0  # reset on successful connect

                subscribe_msg = json.dumps(
                    {
                        "action": "subscribe",
                        "symbols": ",".join(symbols),
                    }
                )
                await ws.send(subscribe_msg)
                logger.debug(
                    "Subscribed %s: %s",
                    asset_class.value,
                    ",".join(symbols),
                )

                async for message in ws:
                    text = (
                        message
                        if isinstance(message, str)
                        else message.decode("utf-8")
                    )

                    try:
                        data: dict[str, object] = json.loads(text)
                    except json.JSONDecodeError:
                        logger.debug("Non-JSON message: %.100s", text)
                        continue

                    if not isinstance(data, dict):
                        continue

                    # Skip EODHD status / heartbeat messages
                    if "status_code" in data or "message" in data:
                        logger.debug("Status: %s", data)
                        continue

                    tick = parser(data)
                    if tick is not None:
                        await queue.put(tick)

        except ConnectionClosed as exc:
            logger.warning("%s feed closed: %s", asset_class.value, exc)
        except (WebSocketException, OSError) as exc:
            logger.warning("%s feed error: %s", asset_class.value, exc)

        attempt += 1
        if max_retries != -1 and attempt > max_retries:
            logger.error(
                "%s feed exhausted %d retries",
                asset_class.value,
                max_retries,
            )
            return

        delay = _backoff_delay(attempt)
        logger.info(
            "%s feed reconnecting in %.1fs (attempt %d)",
            asset_class.value,
            delay,
            attempt,
        )
        await asyncio.sleep(delay)
