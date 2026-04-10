"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Pulse application settings.

    All values can be overridden via environment variables
    or a .env file.
    """

    app_name: str = "pulse"
    debug: bool = False
    eodhd_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
