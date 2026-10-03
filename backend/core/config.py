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

    # --- UW PHX fetchers (ingest daemon, E2.2) ---
    phx_url: str = "https://phx.unusualwhales.com"
    phx_auth_token: Optional[str] = None
    # Rate law (hard rule: rate limits are NEVER hit): PHX documented 4 req/s →
    # paced at ≤50% (0.55s min gap ≈ 1.8 rps) with a daily call cap on top.
    ingest_pace_s: float = 0.55
    ingest_daily_cap: int = 4000
    ingest_max_expiries: int = 8

    # --- Skylit API: temporary RE tool only (sub ends ~Nov 2026) ---
    skylit_api_key: Optional[str] = None

    # --- Tiering / retention (E2.2 T0 retention, E2.3 tier jobs) ---
    t3_root: str = "/Volumes/X10 Pro/gammasummit/t3"
    # Raw T0 retention is owner-locked 24–48h (docs/ops/data-tiering.md);
    # retention.py rejects values outside that range.
    retention_raw_hours: int = 48
    backfill_max_attempts: int = 5
    # T2 (expiry_rollup_hourly, strike_eod) retention window, owner-locked
    # 90d–1yr by docs/ops/data-tiering.md — export_cold.py rejects outside.
    # T1 (gamma_bucket_5m) is fixed at 30d (law, not configurable).
    retention_t2_days: int = 365
    # Cold-copy leg (topology-linkage.md R2 plan): rclone remote name + bucket.
    # Empty remote = copy leg disabled (export runs local-only and says so).
    t3_rclone_remote: str = ""
    t3_rclone_bucket: str = "gammasummit-cold"
    # Owner DSN for partition DDL (pg_partman run_maintenance) and manifest-
    # verified retention deletes — app roles hold no DELETE on tier tables
    # (0004). The single scheduler (jobs/scheduler.py) is its only consumer.
    db_owner_url: Optional[str] = None

    # --- Freshness metric + alarms (E2.4, docs/ops/operations.md) ---
    # Thresholds mirror the ops alerts verbatim: T0 payload-ts staleness during
    # market hours, downsampler lag T0->T1, retention/export job window.
    freshness_t0_stale_minutes: int = 15
    freshness_downsampler_lag_minutes: int = 30
    freshness_retention_late_hours: int = 48
    # Hot-set budget (risks-and-toolkit.md "5-10 GB is snappy" -> 10 GB cap).
    hot_set_budget_bytes: int = 10_000_000_000
    # Uptime Kuma push-monitor URLs (push tokens are secrets: env only).
    kuma_push_overall: Optional[str] = None
    kuma_push_t0_freshness: Optional[str] = None
    kuma_push_downsampler_lag: Optional[str] = None
    kuma_push_retention_jobs: Optional[str] = None

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
