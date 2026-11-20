"""Application settings, read from SKARBONKA_* environment variables or `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets never have defaults."""

    model_config = SettingsConfigDict(
        env_prefix="SKARBONKA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    timezone: str = "Europe/Warsaw"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Settings singleton for the running app (tests build their own)."""
    return Settings()
