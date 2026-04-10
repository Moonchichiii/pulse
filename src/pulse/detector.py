"""StressDetector — asset-aware threshold checks with cooldown."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pulse.events import EventType, StressEvent

if TYPE_CHECKING:
    from pulse.events import EventStore
    from pulse.store import SymbolMetrics

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 30.0

THRESHOLDS: dict[str, dict[EventType, float]] = {
    "stock": {
        EventType.MOVE_1M: 0.005,
        EventType.MOVE_5M: 0.015,
        EventType.VOL_SPIKE: 0.003,
    },
    "forex": {
        EventType.MOVE_1M: 0.001,
        EventType.MOVE_5M: 0.003,
        EventType.VOL_SPIKE: 0.0005,
    },
    "crypto": {
        EventType.MOVE_1M: 0.02,
        EventType.MOVE_5M: 0.05,
        EventType.VOL_SPIKE: 0.01,
    },
}

_DEFAULT_THRESHOLDS: dict[EventType, float] = {
    EventType.MOVE_1M: 0.005,
    EventType.MOVE_5M: 0.015,
    EventType.VOL_SPIKE: 0.003,
}


class StressDetector:
    """Check metrics against asset-aware thresholds and emit events."""

    def __init__(self, event_store: EventStore) -> None:
        self._event_store = event_store
        self._last_fired: dict[tuple[str, EventType], float] = {}

    def _on_cooldown(
        self,
        symbol: str,
        event_type: EventType,
        timestamp: float,
    ) -> bool:
        """Return True if this (symbol, event_type) fired recently."""
        key = (symbol, event_type)
        last = self._last_fired.get(key)
        return last is not None and (timestamp - last) < COOLDOWN_SECONDS

    def _fire(
        self,
        *,
        symbol: str,
        event_type: EventType,
        severity: float,
        threshold: float,
        price: float,
        timestamp: float,
        asset_class: str,
    ) -> StressEvent:
        """Create event, store it, update cooldown, return it."""
        event = StressEvent.create(
            symbol=symbol,
            event_type=event_type,
            severity=severity,
            threshold=threshold,
            price=price,
            timestamp=timestamp,
            asset_class=asset_class,
        )
        self._event_store.add(event)
        self._last_fired[(symbol, event_type)] = timestamp
        logger.info(
            "Stress event: %s %s severity=%.6f threshold=%.6f",
            symbol,
            event_type.value,
            severity,
            threshold,
        )
        return event

    def check(self, metrics: SymbolMetrics) -> list[StressEvent]:
        """Evaluate metrics and return any fired stress events."""
        asset_thresholds = THRESHOLDS.get(
            metrics.asset_class, _DEFAULT_THRESHOLDS
        )
        events: list[StressEvent] = []

        # 1-minute move
        if metrics.ret_1m is not None:
            thresh = asset_thresholds[EventType.MOVE_1M]
            severity = abs(metrics.ret_1m)
            if severity > thresh and not self._on_cooldown(
                metrics.symbol, EventType.MOVE_1M, metrics.timestamp
            ):
                events.append(
                    self._fire(
                        symbol=metrics.symbol,
                        event_type=EventType.MOVE_1M,
                        severity=severity,
                        threshold=thresh,
                        price=metrics.price,
                        timestamp=metrics.timestamp,
                        asset_class=metrics.asset_class,
                    )
                )

        # 5-minute move
        if metrics.ret_5m is not None:
            thresh = asset_thresholds[EventType.MOVE_5M]
            severity = abs(metrics.ret_5m)
            if severity > thresh and not self._on_cooldown(
                metrics.symbol, EventType.MOVE_5M, metrics.timestamp
            ):
                events.append(
                    self._fire(
                        symbol=metrics.symbol,
                        event_type=EventType.MOVE_5M,
                        severity=severity,
                        threshold=thresh,
                        price=metrics.price,
                        timestamp=metrics.timestamp,
                        asset_class=metrics.asset_class,
                    )
                )

        # Volatility spike
        if metrics.volatility is not None:
            thresh = asset_thresholds[EventType.VOL_SPIKE]
            if metrics.volatility > thresh and not self._on_cooldown(
                metrics.symbol,
                EventType.VOL_SPIKE,
                metrics.timestamp,
            ):
                events.append(
                    self._fire(
                        symbol=metrics.symbol,
                        event_type=EventType.VOL_SPIKE,
                        severity=metrics.volatility,
                        threshold=thresh,
                        price=metrics.price,
                        timestamp=metrics.timestamp,
                        asset_class=metrics.asset_class,
                    )
                )

        return events
