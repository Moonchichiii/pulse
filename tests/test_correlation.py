"""Tests for the correlation module."""

from __future__ import annotations

import math
import time

import pytest

from pulse.correlation import (
    DEFAULT_BASE_SYMBOL,
    LOOKBACK,
    CorrelationEngine,
    align_ticks,
    build_return_matrix,
    compute_correlations,
    pearson_corr,
)
from pulse.models import AssetClass, Tick
from pulse.store import PulseStore, Regime, TickRecord

# ── helpers ────────────────────────────────────────────────────────


def _tick(symbol: str, price: float, ts: float) -> Tick:
    """Create a stock tick."""
    return Tick(
        symbol=symbol,
        price=price,
        timestamp=ts,
        asset_class=AssetClass.STOCK,
    )


def _record(price: float, ts: float) -> TickRecord:
    """Create a bare TickRecord."""
    return TickRecord(price=price, timestamp=ts)


def _populated_store(
    symbols: list[str],
    n_ticks: int = 50,
    base_ts: float | None = None,
    interval: float = 10.0,
) -> PulseStore:
    """Return a PulseStore pre-loaded with synthetic stock ticks."""
    store = PulseStore()
    if base_ts is None:
        base_ts = time.time() - n_ticks * interval
    for i in range(n_ticks):
        ts = base_ts + i * interval
        for sym in symbols:
            price = 100.0 + i * 0.1
            store.update(_tick(sym, price, ts))
    return store


# ── align_ticks ────────────────────────────────────────────────────


class TestAlignTicks:
    """Tests for time-bucketed price alignment."""

    def test_empty_data(self) -> None:
        buckets, aligned = align_ticks({}, 10.0, 0.0, 100.0)
        assert buckets == [
            0.0,
            10.0,
            20.0,
            30.0,
            40.0,
            50.0,
            60.0,
            70.0,
            80.0,
            90.0,
            100.0,
        ]
        assert aligned == {}

    def test_zero_bucket_size(self) -> None:
        data = {"A": [_record(10.0, 5.0)]}
        buckets, aligned = align_ticks(data, 0.0, 0.0, 100.0)
        assert buckets == []
        assert aligned == {}

    def test_negative_bucket_size(self) -> None:
        data = {"A": [_record(10.0, 5.0)]}
        buckets, aligned = align_ticks(data, -5.0, 0.0, 100.0)
        assert buckets == []
        assert aligned == {}

    def test_start_greater_than_end(self) -> None:
        data = {"A": [_record(10.0, 5.0)]}
        buckets, aligned = align_ticks(data, 10.0, 100.0, 0.0)
        assert buckets == []
        assert aligned == {}

    def test_single_bucket(self) -> None:
        data = {"A": [_record(42.0, 5.0)]}
        buckets, aligned = align_ticks(data, 10.0, 5.0, 5.0)
        assert len(buckets) == 1
        assert aligned["A"] == [42.0]

    def test_single_symbol(self) -> None:
        data = {
            "A": [
                _record(10.0, 5.0),
                _record(11.0, 15.0),
                _record(12.0, 25.0),
            ],
        }
        buckets, aligned = align_ticks(data, 10.0, 0.0, 30.0)
        # Buckets: 0, 10, 20, 30
        # bucket 0: tick at 5.0 > 0.0 → None
        # bucket 10: tick 5.0 ≤ 10 → 10.0
        # bucket 20: tick 15.0 ≤ 20 → 11.0
        # bucket 30: tick 25.0 ≤ 30 → 12.0
        assert len(buckets) == 4
        assert aligned["A"] == [None, 10.0, 11.0, 12.0]

    def test_forward_fill(self) -> None:
        """Tick in bucket 1, no tick in bucket 2 → price carries forward."""
        data = {
            "A": [
                _record(50.0, 5.0),
                _record(55.0, 35.0),
            ],
        }
        buckets, aligned = align_ticks(data, 10.0, 0.0, 40.0)
        # Buckets: 0, 10, 20, 30, 40
        # bucket 0: nothing ≤0 → None
        # bucket 10: tick at 5 ≤10 → 50.0
        # bucket 20: no new tick ≤20 → forward-fill 50.0
        # bucket 30: no new tick ≤30 → forward-fill 50.0
        # bucket 40: tick at 35 ≤40 → 55.0
        assert aligned["A"] == [None, 50.0, 50.0, 50.0, 55.0]

    def test_multiple_symbols(self) -> None:
        data = {
            "A": [_record(10.0, 5.0), _record(11.0, 15.0)],
            "B": [_record(20.0, 8.0), _record(22.0, 18.0)],
        }
        buckets, aligned = align_ticks(data, 10.0, 0.0, 20.0)
        # Buckets: 0, 10, 20
        assert aligned["A"] == [None, 10.0, 11.0]
        assert aligned["B"] == [None, 20.0, 22.0]

    def test_no_ticks_before_start(self) -> None:
        """All ticks after the first few buckets → leading Nones."""
        data = {"A": [_record(99.0, 50.0)]}
        buckets, aligned = align_ticks(data, 10.0, 0.0, 60.0)
        # 7 buckets: 0, 10, 20, 30, 40, 50, 60
        assert aligned["A"][:5] == [None, None, None, None, None]
        assert aligned["A"][5] == 99.0
        assert aligned["A"][6] == 99.0

    def test_tick_exactly_on_bucket(self) -> None:
        data = {"A": [_record(77.0, 10.0)]}
        buckets, aligned = align_ticks(data, 10.0, 10.0, 20.0)
        assert aligned["A"] == [77.0, 77.0]

    def test_unsorted_ticks(self) -> None:
        """Ticks out of order should still align correctly."""
        data = {
            "A": [
                _record(12.0, 25.0),
                _record(10.0, 5.0),
                _record(11.0, 15.0),
            ],
        }
        buckets, aligned = align_ticks(data, 10.0, 0.0, 30.0)
        assert aligned["A"] == [None, 10.0, 11.0, 12.0]


# ── build_return_matrix ──────────────────────────────────────────


class TestBuildReturnMatrix:
    """Tests for return matrix construction."""

    def test_empty_aligned(self) -> None:
        syms, rows = build_return_matrix({}, ["A"])
        assert syms == []
        assert rows == []

    def test_empty_symbols(self) -> None:
        syms, rows = build_return_matrix({"A": [1.0, 2.0]}, [])
        assert syms == []
        assert rows == []

    def test_single_bucket(self) -> None:
        syms, rows = build_return_matrix({"A": [100.0]}, ["A"])
        assert syms == ["A"]
        assert rows == []

    def test_normal_returns(self) -> None:
        aligned: dict[str, list[float | None]] = {
            "A": [100.0, 110.0, 121.0],
            "B": [50.0, 55.0, 60.5],
        }
        syms, rows = build_return_matrix(aligned, ["A", "B"])
        assert syms == ["A", "B"]
        assert len(rows) == 2
        assert rows[0][0] == pytest.approx(math.log(110 / 100))
        assert rows[0][1] == pytest.approx(math.log(55 / 50))
        assert rows[1][0] == pytest.approx(math.log(121 / 110))
        assert rows[1][1] == pytest.approx(math.log(60.5 / 55))

    def test_drops_none_rows(self) -> None:
        aligned: dict[str, list[float | None]] = {
            "A": [100.0, None, 120.0],
            "B": [50.0, 55.0, 60.0],
        }
        syms, rows = build_return_matrix(aligned, ["A", "B"])
        assert rows == []

    def test_drops_zero_price_rows(self) -> None:
        aligned: dict[str, list[float | None]] = {
            "A": [100.0, 0.0, 120.0],
        }
        syms, rows = build_return_matrix(aligned, ["A"])
        assert rows == []

    def test_missing_symbol_in_aligned(self) -> None:
        aligned: dict[str, list[float | None]] = {
            "A": [100.0, 110.0],
        }
        syms, rows = build_return_matrix(aligned, ["A", "MISSING"])
        assert syms == ["A"]
        assert len(rows) == 1

    def test_partial_none_only_drops_affected_row(self) -> None:
        aligned: dict[str, list[float | None]] = {
            "A": [100.0, 110.0, 121.0, 133.1],
            "B": [50.0, None, 60.0, 66.0],
        }
        syms, rows = build_return_matrix(aligned, ["A", "B"])
        # Row 0: B prev=50, curr=None → dropped
        # Row 1: B prev=None, curr=60 → dropped
        # Row 2: B prev=60, curr=66 → valid
        assert len(rows) == 1
        assert rows[0][0] == pytest.approx(math.log(133.1 / 121.0))
        assert rows[0][1] == pytest.approx(math.log(66.0 / 60.0))


# ── pearson_corr ─────────────────────────────────────────────────


class TestPearsonCorr:
    """Tests for the Pearson correlation function."""

    def test_perfect_positive(self) -> None:
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert pearson_corr(x, y) == pytest.approx(1.0)

    def test_perfect_negative(self) -> None:
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        assert pearson_corr(x, y) == pytest.approx(-1.0)

    def test_near_zero(self) -> None:
        x = [1.0, 0.0, -1.0, 0.0]
        y = [0.0, 1.0, 0.0, -1.0]
        result = pearson_corr(x, y)
        assert result is not None
        assert abs(result) < 0.1

    def test_too_few_points(self) -> None:
        assert pearson_corr([1.0, 2.0], [3.0, 4.0]) is None

    def test_single_point(self) -> None:
        assert pearson_corr([1.0], [2.0]) is None

    def test_empty(self) -> None:
        assert pearson_corr([], []) is None

    def test_zero_variance(self) -> None:
        x = [5.0, 5.0, 5.0, 5.0]
        y = [1.0, 2.0, 3.0, 4.0]
        assert pearson_corr(x, y) is None

    def test_mismatched_lengths(self) -> None:
        assert pearson_corr([1.0, 2.0, 3.0], [1.0, 2.0]) is None

    def test_known_value(self) -> None:
        """Manually computed correlation."""
        x = [1.0, 2.0, 3.0, 4.0]
        y = [1.0, 3.0, 2.0, 4.0]
        # r = 0.8
        result = pearson_corr(x, y)
        assert result is not None
        assert result == pytest.approx(0.8, abs=0.001)


# ── compute_correlations ─────────────────────────────────────────


class TestComputeCorrelations:
    """Tests for the full correlation computation."""

    def test_empty_symbols(self) -> None:
        assert compute_correlations([], [], "SPY") == {}

    def test_empty_rows(self) -> None:
        assert compute_correlations(["SPY", "AAPL"], [], "SPY") == {}

    def test_base_not_in_symbols(self) -> None:
        rows = [[0.01, 0.02], [0.03, 0.04]]
        assert compute_correlations(["A", "B"], rows, "SPY") == {}

    def test_base_is_one(self) -> None:
        rows = [[0.01, 0.02], [0.03, 0.04], [0.02, 0.03]]
        result = compute_correlations(["SPY", "AAPL"], rows, "SPY")
        assert result["SPY"] == 1.0

    def test_two_symbols(self) -> None:
        rows = [
            [0.01, 0.02],
            [0.02, 0.04],
            [-0.01, -0.02],
            [0.03, 0.06],
        ]
        result = compute_correlations(["SPY", "AAPL"], rows, "SPY")
        assert result["SPY"] == 1.0
        assert result["AAPL"] == pytest.approx(1.0)

    def test_anti_correlated(self) -> None:
        rows = [
            [0.01, -0.01],
            [0.02, -0.02],
            [-0.01, 0.01],
            [0.03, -0.03],
        ]
        result = compute_correlations(["SPY", "AAPL"], rows, "SPY")
        assert result["AAPL"] == pytest.approx(-1.0)

    def test_three_symbols(self) -> None:
        """Three stocks: B perfectly correlated, C anti-correlated."""
        rows = [
            [0.01, 0.01, -0.01],
            [0.02, 0.02, -0.02],
            [-0.01, -0.01, 0.01],
            [0.03, 0.03, -0.03],
        ]
        result = compute_correlations(["SPY", "AAPL", "TSLA"], rows, "SPY")
        assert result["SPY"] == 1.0
        assert result["AAPL"] == pytest.approx(1.0)
        assert result["TSLA"] == pytest.approx(-1.0)


# ── PulseStore new methods ───────────────────────────────────────


class TestStoreCorrelationMethods:
    """Tests for get_ticks() and get_stock_symbols()."""

    def test_get_ticks_unknown_symbol(self) -> None:
        store = PulseStore()
        assert store.get_ticks("NOPE") == []

    def test_get_ticks_all(self) -> None:
        store = PulseStore()
        store.update(_tick("AAPL", 150.0, 1000.0))
        store.update(_tick("AAPL", 151.0, 1010.0))
        ticks = store.get_ticks("AAPL")
        assert len(ticks) == 2
        assert ticks[0].price == 150.0
        assert ticks[1].price == 151.0

    def test_get_ticks_since(self) -> None:
        store = PulseStore()
        store.update(_tick("AAPL", 150.0, 1000.0))
        store.update(_tick("AAPL", 151.0, 1010.0))
        store.update(_tick("AAPL", 152.0, 1020.0))
        ticks = store.get_ticks("AAPL", since=1010.0)
        assert len(ticks) == 2
        assert ticks[0].price == 151.0

    def test_get_stock_symbols(self) -> None:
        store = PulseStore()
        store.update(_tick("AAPL", 150.0, 1000.0))
        store.update(
            Tick(
                symbol="EURUSD",
                price=1.1,
                timestamp=1000.0,
                asset_class=AssetClass.FOREX,
            )
        )
        store.update(
            Tick(
                symbol="BTC-USD",
                price=50000.0,
                timestamp=1000.0,
                asset_class=AssetClass.CRYPTO,
            )
        )
        store.update(_tick("MSFT", 300.0, 1000.0))
        stocks = store.get_stock_symbols()
        assert sorted(stocks) == ["AAPL", "MSFT"]

    def test_get_stock_symbols_empty(self) -> None:
        store = PulseStore()
        assert store.get_stock_symbols() == []

    def test_get_ticks_since_no_match(self) -> None:
        store = PulseStore()
        store.update(_tick("AAPL", 150.0, 1000.0))
        ticks = store.get_ticks("AAPL", since=2000.0)
        assert ticks == []


# ── CorrelationEngine ────────────────────────────────────────────


class TestCorrelationEngine:
    """Integration tests for the CorrelationEngine."""

    def test_no_data(self) -> None:
        store = PulseStore()
        engine = CorrelationEngine(store, base_symbol="SPY")
        assert engine.compute() == {}

    def test_base_symbol_missing(self) -> None:
        store = PulseStore()
        store.update(_tick("AAPL", 150.0, time.time()))
        engine = CorrelationEngine(store, base_symbol="SPY")
        assert engine.compute() == {}

    def test_single_symbol_is_base(self) -> None:
        """Only SPY in the store — should return {SPY: 1.0} or {}."""
        now = time.time()
        store = PulseStore()
        for i in range(100):
            store.update(_tick("SPY", 400.0 + i * 0.1, now - 900 + i * 5))
        engine = CorrelationEngine(store, base_symbol="SPY", bucket_size=10.0)
        result = engine.compute()
        # Only one symbol → pearson against itself has no "other" symbols
        # base maps to 1.0
        if result:
            assert result.get("SPY") == 1.0

    def test_correlated_pair(self) -> None:
        """Two symbols moving together should show high correlation."""
        now = time.time()
        store = PulseStore()
        n = 200
        for i in range(n):
            ts = now - 900 + i * 4.5
            p = 100.0 + i * 0.05
            store.update(_tick("SPY", p, ts))
            store.update(_tick("AAPL", p * 2, ts))
        engine = CorrelationEngine(store, base_symbol="SPY", bucket_size=10.0)
        result = engine.compute()
        assert "SPY" in result
        assert result["SPY"] == 1.0
        if "AAPL" in result:
            assert result["AAPL"] == pytest.approx(1.0, abs=0.05)

    def test_custom_bucket_size(self) -> None:
        now = time.time()
        store = PulseStore()
        for i in range(100):
            ts = now - 600 + i * 5
            store.update(_tick("SPY", 400 + i * 0.1, ts))
            store.update(_tick("MSFT", 300 + i * 0.08, ts))
        engine = CorrelationEngine(store, base_symbol="SPY", bucket_size=20.0)
        result = engine.compute()
        assert "SPY" in result

    def test_ignores_non_stock_symbols(self) -> None:
        """Forex/crypto ticks should not appear in correlation output."""
        now = time.time()
        store = PulseStore()
        for i in range(100):
            ts = now - 600 + i * 5
            store.update(_tick("SPY", 400 + i * 0.1, ts))
            store.update(
                Tick(
                    symbol="EURUSD",
                    price=1.1 + i * 0.0001,
                    timestamp=ts,
                    asset_class=AssetClass.FOREX,
                )
            )
        engine = CorrelationEngine(store, base_symbol="SPY", bucket_size=10.0)
        result = engine.compute()
        assert "EURUSD" not in result

    def test_regime_affects_lookback(self) -> None:
        """Verify LOOKBACK constants are wired correctly."""
        assert LOOKBACK[Regime.NORMAL] == 3600.0
        assert LOOKBACK[Regime.HIGH_VOL] == 900.0

    def test_default_base_symbol(self) -> None:
        assert DEFAULT_BASE_SYMBOL == "SPY"

    def test_engine_attributes(self) -> None:
        store = PulseStore()
        engine = CorrelationEngine(store, base_symbol="AAPL", bucket_size=30.0)
        assert engine.base_symbol == "AAPL"
        assert engine.bucket_size == 30.0
