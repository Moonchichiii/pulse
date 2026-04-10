"""Domain models for market tick data."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class AssetClass(StrEnum):
    """Supported asset classes."""

    STOCK = "stock"
    FOREX = "forex"
    CRYPTO = "crypto"


class Tick(BaseModel, frozen=True):
    """A single price tick from a market feed."""

    symbol: str
    price: float
    timestamp: float
    volume: float | None = None
    asset_class: AssetClass
