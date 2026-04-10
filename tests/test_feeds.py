"""Tests for EODHD feed tick parsers."""

from __future__ import annotations

from pulse.feeds import (
    parse_crypto_tick,
    parse_forex_tick,
    parse_stock_tick,
)
from pulse.models import AssetClass

# -- Stock parser -----------------------------------------------------------


class TestParseStockTick:
    def test_valid_tick(self) -> None:
        raw: dict[str, object] = {
            "s": "AAPL.US",
            "p": 150.25,
            "t": 1_700_000_000_000,
            "v": 100,
        }
        tick = parse_stock_tick(raw)
        assert tick is not None
        assert tick.symbol == "AAPL"
        assert tick.price == 150.25
        assert tick.timestamp == 1_700_000_000.0
        assert tick.volume == 100.0
        assert tick.asset_class == AssetClass.STOCK

    def test_no_volume(self) -> None:
        raw: dict[str, object] = {
            "s": "MSFT.US",
            "p": 400.0,
            "t": 1_700_000_000_000,
        }
        tick = parse_stock_tick(raw)
        assert tick is not None
        assert tick.volume is None

    def test_missing_price_returns_none(self) -> None:
        raw: dict[str, object] = {
            "s": "AAPL.US",
            "t": 1_700_000_000_000,
        }
        assert parse_stock_tick(raw) is None

    def test_missing_symbol_returns_none(self) -> None:
        raw: dict[str, object] = {
            "p": 150.0,
            "t": 1_700_000_000_000,
        }
        assert parse_stock_tick(raw) is None


# -- Forex parser -----------------------------------------------------------


class TestParseForexTick:
    def test_valid_tick(self) -> None:
        raw: dict[str, object] = {
            "s": "EURSEK.FOREX",
            "a": 11.2340,
            "b": 11.2300,
            "t": 1_700_000_000_000,
        }
        tick = parse_forex_tick(raw)
        assert tick is not None
        assert tick.symbol == "EURSEK"
        assert tick.price == (11.2340 + 11.2300) / 2.0
        assert tick.timestamp == 1_700_000_000.0
        assert tick.volume is None
        assert tick.asset_class == AssetClass.FOREX

    def test_missing_bid_returns_none(self) -> None:
        raw: dict[str, object] = {
            "s": "EURSEK.FOREX",
            "a": 11.2340,
            "t": 1_700_000_000_000,
        }
        assert parse_forex_tick(raw) is None

    def test_missing_ask_returns_none(self) -> None:
        raw: dict[str, object] = {
            "s": "USDSEK.FOREX",
            "b": 10.8500,
            "t": 1_700_000_000_000,
        }
        assert parse_forex_tick(raw) is None


# -- Crypto parser ----------------------------------------------------------


class TestParseCryptoTick:
    def test_valid_tick(self) -> None:
        raw: dict[str, object] = {
            "s": "BTC-USD.CC",
            "p": 50000.0,
            "t": 1_700_000_000_000,
            "q": 1.5,
        }
        tick = parse_crypto_tick(raw)
        assert tick is not None
        assert tick.symbol == "BTC-USD"
        assert tick.price == 50000.0
        assert tick.volume == 1.5
        assert tick.asset_class == AssetClass.CRYPTO

    def test_no_quantity(self) -> None:
        raw: dict[str, object] = {
            "s": "ETH-USD.CC",
            "p": 3000.0,
            "t": 1_700_000_000_000,
        }
        tick = parse_crypto_tick(raw)
        assert tick is not None
        assert tick.volume is None

    def test_missing_price_returns_none(self) -> None:
        raw: dict[str, object] = {
            "s": "BTC-USD.CC",
            "t": 1_700_000_000_000,
        }
        assert parse_crypto_tick(raw) is None
