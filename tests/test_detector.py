"""Tests for StressDetector — threshold checks, cooldown, and regime."""

from __future__ import annotations

from pulse.detector import (
    COOLDOWN_SECONDS,
    REGIME_MULTIPLIERS,
    THRESHOLDS,
    StressDetector,
)
from pulse.events import EventStore, EventType
from pulse.store import Regime, SymbolMetrics

_BASE_TS = 1_700_000_000.0


def _metrics(
    symbol: str = "AAPL",
    asset_class: str = "stock",
    price: float = 150.0,
    timestamp: float = _BASE_TS,
    ret_1m: float | None = None,
    ret_5m: float | None = None,
    ret_15m: float | None = None,
    volatility: float | None = None,
    trend: float | None = None,
    regime: Regime = Regime.NORMAL,
) -> SymbolMetrics:
    return SymbolMetrics(
        symbol=symbol,
        asset_class=asset_class,
        price=price,
        timestamp=timestamp,
        ret_1m=ret_1m,
        ret_5m=ret_5m,
        ret_15m=ret_15m,
        volatility=volatility,
        trend=trend,
        regime=regime,
    )


class TestNoEvents:
    def test_none_metrics_produce_no_events(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        events = det.check(_metrics())
        assert events == []
        assert es.count == 0

    def test_below_threshold_produces_no_events(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        events = det.check(_metrics(ret_1m=0.001, ret_5m=0.005))
        assert events == []


class TestMove1m:
    def test_fires_on_large_positive_move(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.MOVE_1M]
        events = det.check(_metrics(ret_1m=thresh + 0.001))
        assert len(events) == 1
        assert events[0].event_type == EventType.MOVE_1M
        assert events[0].symbol == "AAPL"
        assert es.count == 1

    def test_fires_on_large_negative_move(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.MOVE_1M]
        events = det.check(_metrics(ret_1m=-(thresh + 0.001)))
        assert len(events) == 1
        assert events[0].event_type == EventType.MOVE_1M

    def test_severity_is_absolute_value(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.MOVE_1M]
        events = det.check(_metrics(ret_1m=-(thresh + 0.01)))
        assert len(events) == 1
        assert events[0].severity > 0


class TestMove5m:
    def test_fires_on_large_5m_move(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.MOVE_5M]
        events = det.check(_metrics(ret_5m=thresh + 0.001))
        assert len(events) == 1
        assert events[0].event_type == EventType.MOVE_5M


class TestVolSpike:
    def test_fires_on_vol_spike(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.VOL_SPIKE]
        events = det.check(_metrics(volatility=thresh + 0.001))
        assert len(events) == 1
        assert events[0].event_type == EventType.VOL_SPIKE


class TestCooldown:
    def test_prevents_duplicate_within_window(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.MOVE_1M]
        big = thresh + 0.01

        events1 = det.check(_metrics(ret_1m=big, timestamp=_BASE_TS))
        assert len(events1) == 1

        events2 = det.check(_metrics(ret_1m=big, timestamp=_BASE_TS + 10))
        assert len(events2) == 0

    def test_fires_again_after_cooldown_expires(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.MOVE_1M]
        big = thresh + 0.01

        det.check(_metrics(ret_1m=big, timestamp=_BASE_TS))
        events = det.check(
            _metrics(
                ret_1m=big,
                timestamp=_BASE_TS + COOLDOWN_SECONDS + 1,
            )
        )
        assert len(events) == 1

    def test_different_event_types_independent(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        m1 = THRESHOLDS["stock"][EventType.MOVE_1M]
        m5 = THRESHOLDS["stock"][EventType.MOVE_5M]

        events = det.check(
            _metrics(
                ret_1m=m1 + 0.01,
                ret_5m=m5 + 0.01,
                timestamp=_BASE_TS,
            )
        )
        assert len(events) == 2

    def test_different_symbols_independent(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        thresh = THRESHOLDS["stock"][EventType.MOVE_1M]
        big = thresh + 0.01

        det.check(_metrics(symbol="AAPL", ret_1m=big, timestamp=_BASE_TS))
        events = det.check(
            _metrics(
                symbol="MSFT",
                ret_1m=big,
                timestamp=_BASE_TS + 5,
            )
        )
        assert len(events) == 1
        assert events[0].symbol == "MSFT"


class TestAssetThresholds:
    def test_crypto_higher_threshold_than_stock(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        stock_events = det.check(
            _metrics(
                symbol="AAPL",
                asset_class="stock",
                ret_1m=0.01,
                timestamp=_BASE_TS,
            )
        )
        crypto_events = det.check(
            _metrics(
                symbol="BTC-USD",
                asset_class="crypto",
                ret_1m=0.01,
                timestamp=_BASE_TS,
            )
        )
        assert len(stock_events) == 1
        assert len(crypto_events) == 0

    def test_forex_lower_threshold_than_stock(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        forex_events = det.check(
            _metrics(
                symbol="EURUSD",
                asset_class="forex",
                ret_1m=0.002,
                timestamp=_BASE_TS,
            )
        )
        stock_events = det.check(
            _metrics(
                symbol="AAPL",
                asset_class="stock",
                ret_1m=0.002,
                timestamp=_BASE_TS,
            )
        )
        assert len(forex_events) == 1
        assert len(stock_events) == 0

    def test_unknown_asset_uses_default(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        events = det.check(
            _metrics(
                symbol="X",
                asset_class="unknown",
                ret_1m=0.01,
                timestamp=_BASE_TS,
            )
        )
        assert len(events) == 1


class TestRegimeAwareThresholds:
    """High-vol regime raises thresholds by 1.5x."""

    def test_normal_regime_uses_base_threshold(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        base = THRESHOLDS["stock"][EventType.MOVE_1M]
        # Just above base → fires in normal
        events = det.check(_metrics(ret_1m=base + 0.001, regime=Regime.NORMAL))
        assert len(events) == 1
        assert events[0].threshold == base * REGIME_MULTIPLIERS["normal"]

    def test_high_vol_raises_threshold(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        base = THRESHOLDS["stock"][EventType.MOVE_1M]
        # Above base but below base*1.5 → should NOT fire in high_vol
        move = base * 1.2
        events = det.check(_metrics(ret_1m=move, regime=Regime.HIGH_VOL))
        assert len(events) == 0

    def test_high_vol_fires_on_extreme_move(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        base = THRESHOLDS["stock"][EventType.MOVE_1M]
        mult = REGIME_MULTIPLIERS["high_vol"]
        # Above base*1.5 → fires even in high_vol
        move = base * mult + 0.001
        events = det.check(_metrics(ret_1m=move, regime=Regime.HIGH_VOL))
        assert len(events) == 1
        assert events[0].regime == "high_vol"
        assert events[0].threshold == base * mult

    def test_high_vol_suppresses_vol_spike(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        base = THRESHOLDS["stock"][EventType.VOL_SPIKE]
        # Between base and base*1.5 → fires normal, not high_vol
        vol = base * 1.2

        normal_events = det.check(
            _metrics(
                symbol="A",
                volatility=vol,
                regime=Regime.NORMAL,
                timestamp=_BASE_TS,
            )
        )
        high_events = det.check(
            _metrics(
                symbol="B",
                volatility=vol,
                regime=Regime.HIGH_VOL,
                timestamp=_BASE_TS,
            )
        )
        assert len(normal_events) == 1
        assert len(high_events) == 0

    def test_event_carries_regime_tag(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        events = det.check(_metrics(ret_1m=0.05, regime=Regime.HIGH_VOL))
        assert len(events) == 1
        assert events[0].regime == "high_vol"

    def test_event_carries_normal_regime(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        events = det.check(_metrics(ret_1m=0.05, regime=Regime.NORMAL))
        assert len(events) == 1
        assert events[0].regime == "normal"

    def test_5m_move_regime_aware(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        base = THRESHOLDS["stock"][EventType.MOVE_5M]
        # Between base and base*mult → fires normal, not high_vol
        move = base * 1.2
        normal = det.check(
            _metrics(
                symbol="A",
                ret_5m=move,
                regime=Regime.NORMAL,
                timestamp=_BASE_TS,
            )
        )
        high = det.check(
            _metrics(
                symbol="B",
                ret_5m=move,
                regime=Regime.HIGH_VOL,
                timestamp=_BASE_TS,
            )
        )
        assert len(normal) == 1
        assert len(high) == 0


class TestMultipleEventsPerCheck:
    def test_all_three_fire_at_once(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        events = det.check(
            _metrics(
                ret_1m=0.05,
                ret_5m=0.10,
                volatility=0.05,
                timestamp=_BASE_TS,
            )
        )
        assert len(events) == 3
        types = {e.event_type for e in events}
        assert types == {
            EventType.MOVE_1M,
            EventType.MOVE_5M,
            EventType.VOL_SPIKE,
        }
        assert es.count == 3

    def test_event_fields_populated(self) -> None:
        es = EventStore()
        det = StressDetector(es)
        events = det.check(
            _metrics(
                ret_1m=0.05,
                price=155.0,
                timestamp=_BASE_TS,
            )
        )
        assert len(events) == 1
        e = events[0]
        assert e.price == 155.0
        assert e.timestamp == _BASE_TS
        assert e.asset_class == "stock"
        assert e.regime == "normal"
        assert len(e.event_id) == 12
