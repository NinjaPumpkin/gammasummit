"""Shared T0 batch-upsert writer (tree: ingest/t0_writer.py) — card E2.2.

Thin glue over `backend.core.db.upsert_rows`: coercion helpers for PHX payload
types (PHX sends numerics as strings in several endpoints) and one write path
every T0 writer uses. Idempotent by conflict key — a retried batch overwrites
identical rows instead of duplicating them (hard rule: T0 writer batch-upsert
idempotent).

Pure mapping + async write: no env reads, no network. Python 3.10 floor.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Optional, Sequence

from backend.core.db import Database, upsert_rows

# Conflict keys per T0 table (must match the PRIMARY KEYs of
# db/migrations/0003_partitioned_schema.sql).
CONFLICT_KEYS: dict[str, tuple[str, ...]] = {
    "gamma_snapshot": ("ticker", "expiry", "strike", "ts"),
    "spot_tick": ("ticker", "ts", "seq"),
    "flow_print": ("occ", "ts", "seq"),
    "darkpool_print": ("ticker", "ts", "seq"),
}


def parse_ts(value: Any) -> Optional[dt.datetime]:
    """ISO-8601 (…Z or ±HH:MM) or epoch milliseconds → aware datetime (UTC).

    PHX mixes both shapes (`created_at` ISO, `start_time` epoch ms). Returns
    None on empty/unparseable input — callers decide whether that is fatal.
    """
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


async def write_rows(db: Database, table: str, rows: Sequence[Mapping[str, Any]]) -> int:
    """Batch-upsert mapped rows into one T0 table. Returns rows written."""
    keys = CONFLICT_KEYS.get(table)
    if keys is None:
        raise ValueError(f"unknown T0 table: {table}")
    return await upsert_rows(db, table, rows, keys)
