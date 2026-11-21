"""Application settings, read from SKARBONKA_* environment variables or `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The repo keeps one `.env` at its root (shared with docker compose), while commands run from
# `backend/`. Read the root file first; a `.env` in the working directory overrides it.
# Missing files are ignored, so an installed package simply falls back to the environment.
REPO_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Runtime configuration. Secrets never have defaults."""

    model_config = SettingsConfigDict(
        env_prefix="SKARBONKA_",
        env_file=(REPO_ENV_FILE, ".env"),
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
