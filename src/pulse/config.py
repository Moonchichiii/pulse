"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Pulse application settings.

    All values can be overridden via environment variables
    or a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "pulse"
    debug: bool = False

    # EODHD
    eodhd_api_key: str = ""
    stock_symbols: str = "AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META,JPM,V,SPY"
    forex_symbols: str = "EURUSD,EURSEK,USDSEK"
    crypto_symbols: str = "BTC-USD,ETH-USD,SOL-USD,XRP-USD,ADA-USD"


def parse_symbols(csv: str) -> list[str]:
    """Split a comma-separated symbol string into a list."""
    return [s.strip() for s in csv.split(",") if s.strip()]


def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
