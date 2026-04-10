"""Event models and store for market stress events."""

from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass
from enum import StrEnum

MAX_EVENTS = 500


class EventType(StrEnum):
    """Types of stress events."""

    MOVE_1M = "move_1m"
    MOVE_5M = "move_5m"
    VOL_SPIKE = "vol_spike"


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
