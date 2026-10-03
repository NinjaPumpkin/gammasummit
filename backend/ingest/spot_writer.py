"""Spot tick writer (tree: ingest/spot_writer.py) — card E2.2.

Maps PHX `/api/ticker/{T}/price/v2` session prices (regular / pre / post, each
with its own tape_time) onto `spot_tick` rows. One row per session price whose
tape time parses — ts is the upstream tape time, so re-fetching an unchanged
price is a no-op upsert (idempotent).

PHX `prev` is deliberately NOT written: it is a previous close, not a tick,
and its shape is unstable (string OR dict — RE pitfall, verified).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

from backend.core.db import Database
from backend.ingest.t0_writer import parse_ts, to_float, write_rows

SOURCE = "phx_price_v2"
_SESSIONS = ("regular", "pre", "post")


def map_spot_rows(
    ticker: str, price_payload: Mapping[str, Any], *, source: str = SOURCE
) -> list[dict[str, Any]]:
    ticker = (ticker or "").strip().upper()
    rows: list[dict[str, Any]] = []
    for session in _SESSIONS:
        block = price_payload.get(session)
        if not isinstance(block, Mapping):
            continue
        price = to_float(block.get("close"))
        ts = parse_ts(block.get("tape_time"))
        if price is None or ts is None:
            continue
        rows.append(
            {
                "ticker": ticker,
                "ts": ts,
                "seq": 0,
                "price": price,
                "size": None,
                "source": f"{source}:{session}",
            }
        )
    return rows


def latest_payload_ts(price_payload: Mapping[str, Any]) -> dt.datetime | None:
    stamps = [
        parse_ts(price_payload.get(s, {}).get("tape_time"))
        for s in _SESSIONS
        if isinstance(price_payload.get(s), Mapping)
    ]
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


async def write_spot_ticks(db: Database, rows: Sequence[Mapping[str, Any]]) -> int:
    return await write_rows(db, "spot_tick", rows)
