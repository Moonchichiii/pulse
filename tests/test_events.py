"""Tests for EventStore and StressEvent."""

from __future__ import annotations

from pulse.events import EventStore, EventType, StressEvent

_BASE_TS = 1_700_000_000.0


def _event(
    symbol: str = "AAPL",
    event_type: EventType = EventType.MOVE_1M,
    timestamp: float = _BASE_TS,
) -> StressEvent:
    return StressEvent.create(
        symbol=symbol,
        event_type=event_type,
        severity=0.01,
        threshold=0.005,
        price=150.0,
        timestamp=timestamp,
        asset_class="stock",
    )


class TestStressEvent:
    def test_create_generates_id(self) -> None:
        e = _event()
        assert len(e.event_id) == 12
        assert isinstance(e.event_id, str)

    def test_create_unique_ids(self) -> None:
        ids = {_event().event_id for _ in range(100)}
        assert len(ids) == 100

    def test_frozen(self) -> None:
        e = _event()
        try:
            e.symbol = "MSFT"  # type: ignore[misc]
            raised = False
        except AttributeError:
            raised = True
        assert raised


class TestEventStore:
    def test_empty_store(self) -> None:
        es = EventStore()
        assert es.count == 0
        assert es.recent() == []

    def test_add_and_count(self) -> None:
        es = EventStore()
        es.add(_event())
        assert es.count == 1

    def test_recent_default(self) -> None:
        es = EventStore()
        for i in range(10):
            es.add(_event(timestamp=_BASE_TS + i))
        events = es.recent()
        assert len(events) == 10

    def test_recent_limits_to_n(self) -> None:
        es = EventStore()
        for i in range(10):
            es.add(_event(timestamp=_BASE_TS + i))
        events = es.recent(3)
        assert len(events) == 3
        assert events[0].timestamp == _BASE_TS + 7

    def test_since_filters_by_timestamp(self) -> None:
        es = EventStore()
        for i in range(5):
            es.add(_event(timestamp=_BASE_TS + i * 10))
        events = es.since(_BASE_TS + 25)
        assert len(events) == 2
        assert events[0].timestamp == _BASE_TS + 30
        assert events[1].timestamp == _BASE_TS + 40

    def test_events_for_filters_by_symbol(self) -> None:
        es = EventStore()
        es.add(_event(symbol="AAPL"))
        es.add(_event(symbol="MSFT"))
        es.add(_event(symbol="AAPL"))
        assert len(es.events_for("AAPL")) == 2
        assert len(es.events_for("MSFT")) == 1
        assert len(es.events_for("GOOGL")) == 0

    def test_clear(self) -> None:
        es = EventStore()
        es.add(_event())
        es.clear()
        assert es.count == 0

    def test_maxlen_evicts_oldest(self) -> None:
        es = EventStore(maxlen=5)
        for i in range(10):
            es.add(_event(timestamp=_BASE_TS + i))
        assert es.count == 5
        events = es.recent(10)
        assert events[0].timestamp == _BASE_TS + 5
