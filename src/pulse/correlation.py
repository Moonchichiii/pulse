"""Correlation module — regime-aware Pearson correlation for stocks."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from pulse.store import Regime

if TYPE_CHECKING:
    from pulse.store import PulseStore, TickRecord

LOOKBACK: dict[Regime, float] = {
    Regime.NORMAL: 3600.0,
    Regime.HIGH_VOL: 900.0,
}

DEFAULT_BUCKET_SIZE = 10.0
DEFAULT_BASE_SYMBOL = "SPY"


def align_ticks(
    tick_data: dict[str, list[TickRecord]],
    bucket_size: float,
    start: float,
    end: float,
) -> tuple[list[float], dict[str, list[float | None]]]:
    """Snap irregular ticks to fixed-width time bins.

    Each bin holds the last price seen at or before the bin timestamp.
    Forward-fill: if no new tick arrives in a bin, carry the previous
    price forward.  Symbols with no tick before a bin get ``None``.

    Returns:
        ``(bucket_timestamps, {symbol: [price | None, ...]})``.
    """
    if bucket_size <= 0 or start > end:
        return [], {}

    buckets: list[float] = []
    t = start
    while t <= end:
        buckets.append(t)
        t += bucket_size

    if not buckets:
        return [], {}

    result: dict[str, list[float | None]] = {}

    for symbol, ticks in tick_data.items():
        sorted_ticks = sorted(ticks, key=lambda tr: tr.timestamp)

        prices: list[float | None] = []
        tick_idx = 0
        last_price: float | None = None

        for bucket_ts in buckets:
            while (
                tick_idx < len(sorted_ticks)
                and sorted_ticks[tick_idx].timestamp <= bucket_ts
            ):
                last_price = sorted_ticks[tick_idx].price
                tick_idx += 1
            prices.append(last_price)

        result[symbol] = prices

    return buckets, result


def build_return_matrix(
    aligned: dict[str, list[float | None]],
    symbols: list[str],
) -> tuple[list[str], list[list[float]]]:
    """Log-returns between consecutive aligned buckets.

    Rows where any symbol has ``None`` or a non-positive price are
    dropped.

    Returns:
        ``(valid_symbols, rows)`` where each row is
        ``[ret_sym0, ret_sym1, ...]``.
    """
    if not symbols or not aligned:
        return [], []

    valid_symbols = [s for s in symbols if s in aligned]
    if not valid_symbols:
        return [], []

    n_buckets = len(aligned[valid_symbols[0]])
    if n_buckets < 2:
        return valid_symbols, []

    rows: list[list[float]] = []

    for i in range(1, n_buckets):
        row: list[float] = []
        valid = True

        for sym in valid_symbols:
            prev = aligned[sym][i - 1]
            curr = aligned[sym][i]

            if prev is None or curr is None or prev <= 0 or curr <= 0:
                valid = False
                break

            row.append(math.log(curr / prev))

        if valid:
            rows.append(row)

    return valid_symbols, rows


def pearson_corr(x: list[float], y: list[float]) -> float | None:
    """Pearson correlation coefficient between two sequences.

    Returns ``None`` if fewer than 3 observations, mismatched lengths,
    or zero variance in either series.
    """
    n = len(x)
    if n < 3 or n != len(y):
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    var_x = sum((x[i] - mean_x) ** 2 for i in range(n))
    var_y = sum((y[i] - mean_y) ** 2 for i in range(n))

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return None

    return cov / denom


def compute_correlations(
    symbols: list[str],
    rows: list[list[float]],
    base_symbol: str,
) -> dict[str, float]:
    """Pearson correlation of each symbol against *base_symbol*.

    The base symbol itself maps to ``1.0``.  Symbols whose correlation
    cannot be computed are omitted from the result.
    """
    if not symbols or not rows or base_symbol not in symbols:
        return {}

    base_idx = symbols.index(base_symbol)
    base_returns = [row[base_idx] for row in rows]

    result: dict[str, float] = {}

    for i, sym in enumerate(symbols):
        if sym == base_symbol:
            result[sym] = 1.0
            continue

        sym_returns = [row[i] for row in rows]
        corr = pearson_corr(base_returns, sym_returns)
        if corr is not None:
            result[sym] = corr

    return result


class CorrelationEngine:
    """Regime-aware correlation engine for stock symbols.

    Lookback adapts to the base symbol's regime:
    - ``normal``: 60 min
    - ``high_vol``: 15 min
    """

    def __init__(
        self,
        store: PulseStore,
        base_symbol: str = DEFAULT_BASE_SYMBOL,
        bucket_size: float = DEFAULT_BUCKET_SIZE,
    ) -> None:
        self._store = store
        self.base_symbol = base_symbol
        self.bucket_size = bucket_size

    def compute(self) -> dict[str, float]:
        """Return ``{symbol: correlation}`` for all tracked stocks."""
        regime = self._store.get_regime(self.base_symbol)
        lookback = LOOKBACK.get(regime, LOOKBACK[Regime.NORMAL])

        now = time.time()
        since = now - lookback

        stock_symbols = self._store.get_stock_symbols()
        if not stock_symbols or self.base_symbol not in stock_symbols:
            return {}

        tick_data: dict[str, list[TickRecord]] = {}
        for sym in stock_symbols:
            ticks = self._store.get_ticks(sym, since=since)
            if ticks:
                tick_data[sym] = ticks

        if self.base_symbol not in tick_data:
            return {}

        _, aligned = align_ticks(tick_data, self.bucket_size, since, now)

        symbols, rows = build_return_matrix(aligned, stock_symbols)

        return compute_correlations(symbols, rows, self.base_symbol)
