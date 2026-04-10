"""Event models, store, and stress detection for market events."""

from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pulse.store import SymbolMetrics

logger = logging.getLogger(__name__)

MAX_EVENTS = 500
COOLDOWN_SECONDS = 30.0


class EventType(StrEnum):
    """Types of stress events."""

    MOVE_1M = "move_1m"
    MOVE_5M = "move_5m"
    VOL_SPIKE = "vol_spike"


ASSET_THRESHOLDS: dict[str, dict[EventType, float]] = {
    "crypto": {
        EventType.MOVE_1M: 0.02,
        EventType.MOVE_5M: 0.05,
        EventType.VOL_SPIKE: 0.03,
    },
    "stock": {
        EventType.MOVE_1M: 0.01,
        EventType.MOVE_5M: 0.03,
        EventType.VOL_SPIKE: 0.02,
    },
    "forex": {
        EventType.MOVE_1M: 0.003,
        EventType.MOVE_5M: 0.008,
        EventType.VOL_SPIKE: 0.005,
    },
}

_DEFAULT_THRESHOLDS: dict[EventType, float] = {
    EventType.MOVE_1M: 0.01,
    EventType.MOVE_5M: 0.03,
    EventType.VOL_SPIKE: 0.02,
}


@dataclass(frozen=True)
class StressEvent:
    """A detected market stress event."""

    event_id: str
    symbol: str
    event_type: EventType
    severity: float
    threshold: float
    price: float
    timestamp: float
    asset_class: str

    @staticmethod
    def create(
        *,
        symbol: str,
        event_type: EventType,
        severity: float,
        threshold: float,
        price: float,
        timestamp: float,
        asset_class: str,
    ) -> StressEvent:
        """Factory with auto-generated event ID."""
        return StressEvent(
            event_id=uuid.uuid4().hex[:12],
            symbol=symbol,
            event_type=event_type,
            severity=severity,
            threshold=threshold,
            price=price,
            timestamp=timestamp,
            asset_class=asset_class,
        )


class EventStore:
    """Thread-safe rolling store of stress events."""

    def __init__(self, maxlen: int = MAX_EVENTS) -> None:
        self._lock = threading.Lock()
        self._events: deque[StressEvent] = deque(maxlen=maxlen)

    def add(self, event: StressEvent) -> None:
        """Append an event to the rolling buffer."""
        with self._lock:
            self._events.append(event)

    def recent(self, n: int = 50) -> list[StressEvent]:
        """Return the last *n* events (oldest first)."""
        with self._lock:
            items = list(self._events)
        return items[-n:]

    def since(self, timestamp: float) -> list[StressEvent]:
        """Return events newer than *timestamp*."""
        with self._lock:
            return [e for e in self._events if e.timestamp > timestamp]

    def events_for(self, symbol: str) -> list[StressEvent]:
        """Return all stored events for a given symbol."""
        with self._lock:
            return [e for e in self._events if e.symbol == symbol]

    @property
    def count(self) -> int:
        """Total number of stored events."""
        with self._lock:
            return len(self._events)

    def clear(self) -> None:
        """Remove all events."""
        with self._lock:
            self._events.clear()


class StressDetector:
    """Detect market stress events with per-symbol cooldowns."""

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store
        self._lock = threading.Lock()
        self._cooldowns: dict[tuple[str, EventType], float] = {}

    def check(self, metrics: SymbolMetrics) -> list[StressEvent]:
        """Evaluate metrics against asset-aware thresholds.

        Returns a list of newly created stress events.
        Respects a 30-second cooldown per (symbol, event_type).
        """
        thresholds = ASSET_THRESHOLDS.get(
            metrics.asset_class, _DEFAULT_THRESHOLDS
        )
        now = metrics.timestamp
        events: list[StressEvent] = []

        checks: list[tuple[EventType, float | None]] = [
            (EventType.MOVE_1M, metrics.ret_1m),
            (EventType.MOVE_5M, metrics.ret_5m),
            (EventType.VOL_SPIKE, metrics.volatility),
        ]

        with self._lock:
            for event_type, value in checks:
                if value is None:
                    continue
                threshold = thresholds[event_type]
                if abs(value) <= threshold:
                    continue
                key = (metrics.symbol, event_type)
                last = self._cooldowns.get(key, 0.0)
                if (now - last) < COOLDOWN_SECONDS:
                    continue
                self._cooldowns[key] = now
                event = StressEvent.create(
                    symbol=metrics.symbol,
                    event_type=event_type,
                    severity=value,
                    threshold=threshold,
                    price=metrics.price,
                    timestamp=now,
                    asset_class=metrics.asset_class,
                )
                events.append(event)

        for event in events:
            self._store.add(event)
            logger.info(
                "Stress event: %s %s severity=%.6f threshold=%.6f",
                event.symbol,
                event.event_type,
                event.severity,
                event.threshold,
            )

        return events
