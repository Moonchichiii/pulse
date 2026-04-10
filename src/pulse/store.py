"""PulseStore — in-memory rolling buffer with computed metrics."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pulse.models import Tick

BUFFER_SECONDS = 3600
RETURN_WINDOWS = (60, 300, 900)
VOL_WINDOW = 900
TREND_WINDOW = 900
VOL_HISTORY_SIZE = 200
REGIME_PERCENTILE = 0.80


class Regime(StrEnum):
    """Market regime for a symbol."""

    NORMAL = "normal"
    HIGH_VOL = "high_vol"


@dataclass
class TickRecord:
    """Lightweight tick stored in the deque."""

    price: float
    timestamp: float
    volume: float | None = None


@dataclass
class SymbolMetrics:
    """Computed metrics for a single symbol."""

    symbol: str
    asset_class: str
    price: float
    timestamp: float
    ret_1m: float | None = None
    ret_5m: float | None = None
    ret_15m: float | None = None
    volatility: float | None = None
    trend: float | None = None
    regime: Regime = Regime.NORMAL


@dataclass
class _SymbolBuffer:
    """Internal rolling buffer + vol history for one symbol."""

    asset_class: str
    ticks: deque[TickRecord] = field(default_factory=deque)
    vol_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=VOL_HISTORY_SIZE)
    )
    last_regime: Regime = field(default=Regime.NORMAL)


def _return_over_window(
    ticks: deque[TickRecord],
    now: float,
    window_secs: int,
) -> float | None:
    """Log return from the oldest tick within window to now."""
    if len(ticks) < 2:
        return None
    cutoff = now - window_secs
    old_price: float | None = None
    for t in ticks:
        if t.timestamp >= cutoff:
            old_price = t.price
            break
    if old_price is None or old_price <= 0:
        return None
    cur = ticks[-1].price
    if cur <= 0:
        return None
    return math.log(cur / old_price)


def _volatility(
    ticks: deque[TickRecord],
    now: float,
    window_secs: int,
) -> float | None:
    """Volatility from tick-to-tick log returns in window."""
    cutoff = now - window_secs
    prices: list[float] = [
        t.price for t in ticks if t.timestamp >= cutoff and t.price > 0
    ]
    if len(prices) < 10:
        return None
    log_rets: list[float] = [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
        if prices[i - 1] > 0
    ]
    if len(log_rets) < 5:
        return None
    mean = sum(log_rets) / len(log_rets)
    var = sum((r - mean) ** 2 for r in log_rets) / len(log_rets)
    return math.sqrt(var)


def _trend_slope(
    ticks: deque[TickRecord],
    now: float,
    window_secs: int,
) -> float | None:
    """Linear regression slope of log-price over time window."""
    cutoff = now - window_secs
    points: list[tuple[float, float]] = [
        (t.timestamp, math.log(t.price))
        for t in ticks
        if t.timestamp >= cutoff and t.price > 0
    ]
    n = len(points)
    if n < 10:
        return None
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    sum_xy = sum(p[0] * p[1] for p in points)
    sum_x2 = sum(p[0] ** 2 for p in points)
    denom = n * sum_x2 - sum_x**2
    if denom == 0:
        return None
    return (n * sum_xy - sum_x * sum_y) / denom


def _detect_regime(
    vol_history: deque[float],
    current_vol: float | None,
) -> Regime:
    """Compare current volatility to 80th percentile of history."""
    if current_vol is None or len(vol_history) < 20:
        return Regime.NORMAL
    sorted_hist = sorted(vol_history)
    idx = int(REGIME_PERCENTILE * len(sorted_hist))
    idx = min(idx, len(sorted_hist) - 1)
    threshold = sorted_hist[idx]
    if current_vol > threshold:
        return Regime.HIGH_VOL
    return Regime.NORMAL


class PulseStore:
    """Thread-safe in-memory store for live tick data and metrics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffers: dict[str, _SymbolBuffer] = {}

    def update(self, tick: Tick) -> SymbolMetrics:
        """Ingest a tick, prune stale data, recompute metrics."""
        now = tick.timestamp
        record = TickRecord(
            price=tick.price,
            timestamp=tick.timestamp,
            volume=tick.volume,
        )

        with self._lock:
            buf = self._buffers.get(tick.symbol)
            if buf is None:
                buf = _SymbolBuffer(asset_class=tick.asset_class.value)
                self._buffers[tick.symbol] = buf

            buf.ticks.append(record)

            cutoff = now - BUFFER_SECONDS
            while buf.ticks and buf.ticks[0].timestamp < cutoff:
                buf.ticks.popleft()

            ret_1m = _return_over_window(buf.ticks, now, RETURN_WINDOWS[0])
            ret_5m = _return_over_window(buf.ticks, now, RETURN_WINDOWS[1])
            ret_15m = _return_over_window(buf.ticks, now, RETURN_WINDOWS[2])
            vol = _volatility(buf.ticks, now, VOL_WINDOW)
            trend = _trend_slope(buf.ticks, now, TREND_WINDOW)

            if vol is not None:
                buf.vol_history.append(vol)

            regime = _detect_regime(buf.vol_history, vol)
            buf.last_regime = regime

            return SymbolMetrics(
                symbol=tick.symbol,
                asset_class=buf.asset_class,
                price=tick.price,
                timestamp=now,
                ret_1m=ret_1m,
                ret_5m=ret_5m,
                ret_15m=ret_15m,
                volatility=vol,
                trend=trend,
                regime=regime,
            )

    def snapshot(self) -> dict[str, SymbolMetrics]:
        """Return current metrics for all tracked symbols."""
        now = time.time()
        results: dict[str, SymbolMetrics] = {}

        with self._lock:
            for symbol, buf in self._buffers.items():
                if not buf.ticks:
                    continue

                latest = buf.ticks[-1]
                ret_1m = _return_over_window(buf.ticks, now, RETURN_WINDOWS[0])
                ret_5m = _return_over_window(buf.ticks, now, RETURN_WINDOWS[1])
                ret_15m = _return_over_window(buf.ticks, now, RETURN_WINDOWS[2])
                vol = _volatility(buf.ticks, now, VOL_WINDOW)
                trend = _trend_slope(buf.ticks, now, TREND_WINDOW)
                regime = _detect_regime(buf.vol_history, vol)

                results[symbol] = SymbolMetrics(
                    symbol=symbol,
                    asset_class=buf.asset_class,
                    price=latest.price,
                    timestamp=latest.timestamp,
                    ret_1m=ret_1m,
                    ret_5m=ret_5m,
                    ret_15m=ret_15m,
                    volatility=vol,
                    trend=trend,
                    regime=regime,
                )

        return results

    def get_regime(self, symbol: str) -> Regime:
        """Return the last computed regime for *symbol*."""
        with self._lock:
            buf = self._buffers.get(symbol)
            if buf is None:
                return Regime.NORMAL
            return buf.last_regime

    @property
    def symbols(self) -> list[str]:
        """List of currently tracked symbols."""
        with self._lock:
            return list(self._buffers.keys())

    def tick_count(self, symbol: str) -> int:
        """Number of ticks in buffer for a symbol."""
        with self._lock:
            buf = self._buffers.get(symbol)
            if buf is None:
                return 0
            return len(buf.ticks)

    def get_ticks(
        self, symbol: str, *, since: float | None = None
    ) -> list[TickRecord]:
        """Return tick records for a symbol, optionally since a timestamp."""
        with self._lock:
            buf = self._buffers.get(symbol)
            if buf is None:
                return []
            if since is None:
                return list(buf.ticks)
            return [t for t in buf.ticks if t.timestamp >= since]

    def get_stock_symbols(self) -> list[str]:
        """Return symbols whose asset class is 'stock'."""
        with self._lock:
            return [
                s for s, b in self._buffers.items() if b.asset_class == "stock"
            ]
