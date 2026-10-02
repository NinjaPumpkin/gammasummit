"""Settings (tree: core/config.py) — card E2.1.

Config law (docs/build/code-structure-and-release.md §3): pydantic-settings,
env prefix `GAMMASUMMIT_`; `.env` gitignored; `.env.example` holds placeholder
lines for every field (scaffold test enforces the sync). No secrets ever get
defaults here.

Lives in core/ per ultraplan P1 (the boring spine every module imports);
`backend/api/deps.py` re-exports it for the API layer.
"""
from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field maps 1:1 to a GAMMASUMMIT_* key in
    `.env.example`. No secrets ever get defaults here."""

    model_config = SettingsConfigDict(
        env_prefix="GAMMASUMMIT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    env: str = "dev"
    log_level: str = "INFO"
    cors_origins: str = ""
    database_url: Optional[str] = None

    # --- DB pool (core/db.py) ---
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10
    db_command_timeout_s: float = 30.0

    # --- Unusual Whales (UW) data source (production source of truth) ---
    uw_url: Optional[str] = None
    uw_service_key: Optional[str] = None
    uw_api_key: Optional[str] = None

    # --- Skylit API: temporary RE tool only (sub ends ~Nov 2026) ---
    skylit_api_key: Optional[str] = None

    # --- Feature flags (kill switches survive rollbacks) ---
    ff_analyst: bool = False
    ff_exec_gate: bool = False
    ff_nexus: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


def get_settings() -> Settings:
    """Accessor with a fresh read of the environment (test-friendly)."""
    return Settings()
