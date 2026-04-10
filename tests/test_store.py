"""Tests for PulseStore — rolling buffers, metrics, and regime detection."""

from __future__ import annotations

import math
import threading
import time
from collections import deque

import pytest

from pulse.models import AssetClass, Tick
from pulse.store import (
    BUFFER_SECONDS,
    REGIME_PERCENTILE,
    PulseStore,
    Regime,
    SymbolMetrics,
    TickRecord,
    _detect_regime,
    _return_over_window,
    _trend_slope,
    _volatility,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_TS = 1_700_000_000.0


def _tick(
    symbol: str = "AAPL",
    price: float = 150.0,
    timestamp: float = _BASE_TS,
    volume: float | None = 100.0,
    asset_class: AssetClass = AssetClass.STOCK,
) -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        timestamp=timestamp,
        volume=volume,
        asset_class=asset_class,
    )


def _build_deque(
    prices: list[float],
    start_ts: float = _BASE_TS,
    interval: float = 1.0,
) -> deque[TickRecord]:
    """Build a deque of TickRecords from a price list."""
    d: deque[TickRecord] = deque()
    for i, p in enumerate(prices):
        d.append(TickRecord(price=p, timestamp=start_ts + i * interval))
    return d


# ---------------------------------------------------------------------------
# _return_over_window
# ---------------------------------------------------------------------------


class TestReturnOverWindow:
    def test_returns_none_with_fewer_than_two_ticks(self) -> None:
        d = _build_deque([100.0])
        assert _return_over_window(d, _BASE_TS, 60) is None

    def test_returns_none_when_no_tick_in_window(self) -> None:
        d = _build_deque([100.0, 110.0], start_ts=_BASE_TS - 200)
        now = _BASE_TS
        assert _return_over_window(d, now, 60) is None

    def test_positive_return(self) -> None:
        d = _build_deque([100.0, 110.0], start_ts=_BASE_TS, interval=10.0)
        now = _BASE_TS + 10.0
        ret = _return_over_window(d, now, 60)
        assert ret is not None
        assert ret == pytest.approx(math.log(110.0 / 100.0))

    def test_negative_return(self) -> None:
        d = _build_deque([100.0, 90.0], start_ts=_BASE_TS, interval=10.0)
        now = _BASE_TS + 10.0
        ret = _return_over_window(d, now, 60)
        assert ret is not None
        assert ret == pytest.approx(math.log(90.0 / 100.0))

    def test_zero_return_when_prices_unchanged(self) -> None:
        d = _build_deque([100.0, 100.0, 100.0], start_ts=_BASE_TS, interval=5.0)
        now = _BASE_TS + 10.0
        ret = _return_over_window(d, now, 60)
        assert ret is not None
        assert ret == pytest.approx(0.0)

    def test_uses_only_ticks_within_window(self) -> None:
        d = _build_deque([50.0], start_ts=_BASE_TS)
        d.append(TickRecord(price=100.0, timestamp=_BASE_TS + 50))
        d.append(TickRecord(price=110.0, timestamp=_BASE_TS + 100))
        now = _BASE_TS + 100
        ret = _return_over_window(d, now, 60)
        assert ret is not None
        assert ret == pytest.approx(math.log(110.0 / 100.0))

    def test_returns_none_for_zero_old_price(self) -> None:
        d = _build_deque([0.0, 100.0], start_ts=_BASE_TS, interval=10.0)
        now = _BASE_TS + 10.0
        assert _return_over_window(d, now, 60) is None

    def test_returns_none_for_zero_current_price(self) -> None:
        d = _build_deque([100.0, 0.0], start_ts=_BASE_TS, interval=10.0)
        now = _BASE_TS + 10.0
        assert _return_over_window(d, now, 60) is None


# ---------------------------------------------------------------------------
# _volatility
# ---------------------------------------------------------------------------


class TestVolatility:
    def test_returns_none_with_fewer_than_10_prices(self) -> None:
        d = _build_deque([100.0 + i for i in range(9)])
        now = _BASE_TS + 8.0
        assert _volatility(d, now, 900) is None

    def test_returns_float_with_enough_prices(self) -> None:
        prices = [100.0 + 0.1 * i for i in range(50)]
        d = _build_deque(prices, interval=1.0)
        now = _BASE_TS + 49.0
        vol = _volatility(d, now, 900)
        assert vol is not None
        assert vol > 0

    def test_zero_volatility_for_flat_prices(self) -> None:
        prices = [100.0] * 50
        d = _build_deque(prices, interval=1.0)
        now = _BASE_TS + 49.0
        vol = _volatility(d, now, 900)
        assert vol is not None
        assert vol == pytest.approx(0.0)

    def test_higher_vol_for_larger_moves(self) -> None:
        small = [100.0 + 0.01 * i for i in range(50)]
        d_small = _build_deque(small, interval=1.0)
        vol_small = _volatility(d_small, _BASE_TS + 49, 900)

        large = [100.0 + (1.0 if i % 2 == 0 else -1.0) for i in range(50)]
        d_large = _build_deque(large, interval=1.0)
        vol_large = _volatility(d_large, _BASE_TS + 49, 900)

        assert vol_small is not None
        assert vol_large is not None
        assert vol_large > vol_small

    def test_ignores_ticks_outside_window(self) -> None:
        prices_old = [100.0 + i for i in range(20)]
        d = _build_deque(prices_old, start_ts=_BASE_TS, interval=1.0)
        for i in range(15):
            d.append(
                TickRecord(
                    price=200.0 + 0.1 * i,
                    timestamp=_BASE_TS + 1000 + i,
                )
            )
        now = _BASE_TS + 1014
        vol = _volatility(d, now, 60)
        assert vol is not None
        assert vol > 0

    def test_skips_zero_prices(self) -> None:
        prices = [0.0] * 5 + [100.0 + 0.1 * i for i in range(15)]
        d = _build_deque(prices, interval=1.0)
        now = _BASE_TS + 19.0
        vol = _volatility(d, now, 900)
        assert vol is not None


# ---------------------------------------------------------------------------
# _trend_slope
# ---------------------------------------------------------------------------


class TestTrendSlope:
    """Use small timestamps to avoid float64 cancellation in regression."""

    def test_returns_none_with_fewer_than_10_points(self) -> None:
        d = _build_deque([100.0 + i for i in range(9)], start_ts=0.0)
        now = 8.0
        assert _trend_slope(d, now, 900) is None

    def test_positive_slope_for_rising_prices(self) -> None:
        prices = [100.0 + i * 0.5 for i in range(50)]
        d = _build_deque(prices, start_ts=0.0, interval=1.0)
        now = 49.0
        slope = _trend_slope(d, now, 900)
        assert slope is not None
        assert slope > 0

    def test_negative_slope_for_falling_prices(self) -> None:
        prices = [200.0 - i * 0.5 for i in range(50)]
        d = _build_deque(prices, start_ts=0.0, interval=1.0)
        now = 49.0
        slope = _trend_slope(d, now, 900)
        assert slope is not None
        assert slope < 0

    def test_near_zero_slope_for_flat_prices(self) -> None:
        prices = [100.0] * 50
        d = _build_deque(prices, start_ts=0.0, interval=1.0)
        now = 49.0
        slope = _trend_slope(d, now, 900)
        assert slope is not None
        assert slope == pytest.approx(0.0, abs=1e-10)

    def test_ignores_zero_prices(self) -> None:
        prices = [0.0] * 3 + [100.0 + 0.1 * i for i in range(20)]
        d = _build_deque(prices, start_ts=0.0, interval=1.0)
        now = 22.0
        slope = _trend_slope(d, now, 900)
        assert slope is not None


# ---------------------------------------------------------------------------
# _detect_regime
# ---------------------------------------------------------------------------


class TestDetectRegime:
    def test_normal_when_vol_is_none(self) -> None:
        hist: deque[float] = deque([0.01] * 30)
        assert _detect_regime(hist, None) == Regime.NORMAL

    def test_normal_when_history_too_short(self) -> None:
        hist: deque[float] = deque([0.01] * 10)
        assert _detect_regime(hist, 0.05) == Regime.NORMAL

    def test_normal_when_vol_below_threshold(self) -> None:
        hist: deque[float] = deque([0.01] * 30)
        assert _detect_regime(hist, 0.005) == Regime.NORMAL

    def test_high_vol_when_above_threshold(self) -> None:
        hist: deque[float] = deque([0.001] * 30)
        assert _detect_regime(hist, 0.1) == Regime.HIGH_VOL

    def test_percentile_boundary(self) -> None:
        hist: deque[float] = deque(sorted([i * 0.001 for i in range(1, 101)]))
        idx = int(REGIME_PERCENTILE * len(hist))
        idx = min(idx, len(hist) - 1)
        threshold = sorted(hist)[idx]
        assert _detect_regime(hist, threshold + 0.001) == Regime.HIGH_VOL
        assert _detect_regime(hist, threshold - 0.001) == Regime.NORMAL


# ---------------------------------------------------------------------------
# PulseStore.update
# ---------------------------------------------------------------------------


class TestPulseStoreUpdate:
    def test_single_tick_ingestion(self) -> None:
        store = PulseStore()
        tick = _tick()
        metrics = store.update(tick)

        assert metrics.symbol == "AAPL"
        assert metrics.asset_class == "stock"
        assert metrics.price == 150.0
        assert metrics.timestamp == _BASE_TS
        assert "AAPL" in store.symbols
        assert store.tick_count("AAPL") == 1

    def test_metrics_none_for_single_tick(self) -> None:
        store = PulseStore()
        metrics = store.update(_tick())

        assert metrics.ret_1m is None
        assert metrics.ret_5m is None
        assert metrics.ret_15m is None
        assert metrics.volatility is None
        assert metrics.trend is None
        assert metrics.regime == Regime.NORMAL

    def test_return_computed_with_two_ticks(self) -> None:
        store = PulseStore()
        store.update(_tick(price=100.0, timestamp=_BASE_TS))
        metrics = store.update(_tick(price=110.0, timestamp=_BASE_TS + 30))

        assert metrics.ret_1m is not None
        assert metrics.ret_1m == pytest.approx(math.log(110.0 / 100.0))

    def test_return_windows_respect_time(self) -> None:
        store = PulseStore()
        store.update(_tick(price=100.0, timestamp=_BASE_TS))
        metrics = store.update(_tick(price=110.0, timestamp=_BASE_TS + 90))

        # 1m window: cutoff = 90 - 60 = 30. Tick at t=0 < 30 → skipped.
        # Only tick at t=90 in window → old_price=110, cur=110 → ret=0
        assert metrics.ret_1m == pytest.approx(0.0)

        # 5m window: cutoff = 90 - 300 = -210. Tick at t=0 ≥ -210 →
        # old_price=100
        assert metrics.ret_5m is not None
        assert metrics.ret_5m == pytest.approx(math.log(110.0 / 100.0))

    def test_vol_and_trend_with_enough_ticks(self) -> None:
        store = PulseStore()
        for i in range(50):
            store.update(
                _tick(
                    price=100.0 + 0.1 * i,
                    timestamp=_BASE_TS + i,
                )
            )

        metrics = store.update(_tick(price=105.0, timestamp=_BASE_TS + 50))

        assert metrics.volatility is not None
        assert metrics.volatility > 0
        assert metrics.trend is not None
        assert metrics.trend > 0

    def test_multiple_symbols(self) -> None:
        store = PulseStore()
        store.update(_tick(symbol="AAPL", price=150.0, timestamp=_BASE_TS))
        store.update(
            _tick(
                symbol="BTC-USD",
                price=50000.0,
                timestamp=_BASE_TS,
                asset_class=AssetClass.CRYPTO,
            )
        )

        assert sorted(store.symbols) == ["AAPL", "BTC-USD"]
        assert store.tick_count("AAPL") == 1
        assert store.tick_count("BTC-USD") == 1

    def test_different_asset_classes_tracked(self) -> None:
        store = PulseStore()
        m1 = store.update(_tick(symbol="AAPL", asset_class=AssetClass.STOCK))
        m2 = store.update(_tick(symbol="EURUSD", asset_class=AssetClass.FOREX))
        m3 = store.update(
            _tick(symbol="BTC-USD", asset_class=AssetClass.CRYPTO)
        )

        assert m1.asset_class == "stock"
        assert m2.asset_class == "forex"
        assert m3.asset_class == "crypto"


# ---------------------------------------------------------------------------
# PulseStore buffer pruning
# ---------------------------------------------------------------------------


class TestPulseStoreBufferPruning:
    def test_old_ticks_pruned(self) -> None:
        store = PulseStore()
        store.update(_tick(price=100.0, timestamp=_BASE_TS))
        store.update(
            _tick(
                price=200.0,
                timestamp=_BASE_TS + BUFFER_SECONDS + 1,
            )
        )

        assert store.tick_count("AAPL") == 1

    def test_recent_ticks_kept(self) -> None:
        store = PulseStore()
        for i in range(100):
            store.update(_tick(price=100.0 + i, timestamp=_BASE_TS + i))

        assert store.tick_count("AAPL") == 100


# ---------------------------------------------------------------------------
# PulseStore regime detection end-to-end
# ---------------------------------------------------------------------------


class TestPulseStoreRegime:
    def test_regime_normal_initially(self) -> None:
        store = PulseStore()
        metrics = store.update(_tick())
        assert metrics.regime == Regime.NORMAL

    def test_regime_transitions_to_high_vol(self) -> None:
        store = PulseStore()
        # Build vol history with low-vol steady prices
        for i in range(250):
            store.update(
                _tick(
                    price=100.0 + 0.001 * i,
                    timestamp=_BASE_TS + i * 0.1,
                )
            )

        # Inject high-volatility ticks (big swings)
        base_ts = _BASE_TS + 30
        metrics = None
        for i in range(60):
            price = 100.0 + (10.0 if i % 2 == 0 else -10.0)
            metrics = store.update(
                _tick(price=price, timestamp=base_ts + i * 0.1)
            )

        assert metrics is not None
        assert metrics.regime == Regime.HIGH_VOL


# ---------------------------------------------------------------------------
# PulseStore.snapshot
# ---------------------------------------------------------------------------


class TestPulseStoreSnapshot:
    def test_snapshot_empty_store(self) -> None:
        store = PulseStore()
        snap = store.snapshot()
        assert snap == {}

    def test_snapshot_returns_all_symbols(self) -> None:
        store = PulseStore()
        now = time.time()
        store.update(_tick(symbol="AAPL", timestamp=now))
        store.update(_tick(symbol="MSFT", price=400.0, timestamp=now))

        snap = store.snapshot()
        assert "AAPL" in snap
        assert "MSFT" in snap
        assert isinstance(snap["AAPL"], SymbolMetrics)
        assert isinstance(snap["MSFT"], SymbolMetrics)

    def test_snapshot_reflects_latest_price(self) -> None:
        store = PulseStore()
        now = time.time()
        store.update(_tick(price=100.0, timestamp=now - 5))
        store.update(_tick(price=150.0, timestamp=now - 1))

        snap = store.snapshot()
        assert snap["AAPL"].price == 150.0

    def test_snapshot_metrics_structure(self) -> None:
        store = PulseStore()
        now = time.time()
        store.update(_tick(timestamp=now))

        snap = store.snapshot()
        m = snap["AAPL"]
        assert m.symbol == "AAPL"
        assert m.asset_class == "stock"
        assert m.price == 150.0


# ---------------------------------------------------------------------------
# PulseStore.symbols and tick_count
# ---------------------------------------------------------------------------


class TestPulseStoreAccessors:
    def test_symbols_initially_empty(self) -> None:
        store = PulseStore()
        assert store.symbols == []

    def test_tick_count_unknown_symbol(self) -> None:
        store = PulseStore()
        assert store.tick_count("NOPE") == 0

    def test_tick_count_increments(self) -> None:
        store = PulseStore()
        for i in range(10):
            store.update(_tick(price=100.0 + i, timestamp=_BASE_TS + i))
        assert store.tick_count("AAPL") == 10


# ---------------------------------------------------------------------------
# Thread safety smoke test
# ---------------------------------------------------------------------------


class TestPulseStoreThreadSafety:
    def test_concurrent_updates(self) -> None:
        store = PulseStore()
        errors: list[Exception] = []

        def writer(symbol: str, offset: int) -> None:
            try:
                for i in range(100):
                    store.update(
                        _tick(
                            symbol=symbol,
                            price=100.0 + i * 0.1,
                            timestamp=_BASE_TS + offset + i,
                        )
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("AAPL", 0)),
            threading.Thread(target=writer, args=("MSFT", 1000)),
            threading.Thread(target=writer, args=("GOOGL", 2000)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert store.tick_count("AAPL") == 100
        assert store.tick_count("MSFT") == 100
        assert store.tick_count("GOOGL") == 100

    def test_concurrent_read_write(self) -> None:
        store = PulseStore()
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(200):
                    store.update(
                        _tick(
                            price=100.0 + i * 0.01,
                            timestamp=_BASE_TS + i,
                        )
                    )
            except Exception as e:
                errors.append(e)

        def reader() -> None:
            try:
                for _ in range(50):
                    store.snapshot()
                    _ = store.symbols
                    store.tick_count("AAPL")
            except Exception as e:
                errors.append(e)

        w = threading.Thread(target=writer)
        r = threading.Thread(target=reader)
        w.start()
        r.start()
        w.join()
        r.join()

        assert errors == []
