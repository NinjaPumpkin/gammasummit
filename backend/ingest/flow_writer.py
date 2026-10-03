"""Flow + dark-pool writers (tree: ingest/flow_writer.py) — card E2.2.

Maps PHX `/api/flow/alerts` alert rows onto `flow_print` (the flow T0 source UW
serves without a paid key) and `/api/flow/dark-pool` trades onto
`darkpool_print`. Shapes RE-verified 2026-10-02 (live probe evidence in
docs/build/e2.2-ingest-shadow.md).

Alerts are alert-level flow records, not raw prints — the `source` column keeps
that provenance (`phx_flow_alerts`), so downstream rollups never confuse the
two. Rows that cannot satisfy the schema constraints (occ / ts / price /
opt_right) are dropped and counted, never synthesized.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

from backend.core.db import Database
from backend.ingest.t0_writer import parse_ts, to_float, to_int, write_rows

FLOW_SOURCE = "phx_flow_alerts"
DARKPOOL_SOURCE = "phx_flow_dark_pool"


def map_flow_rows(
    alerts: Sequence[Mapping[str, Any]], *, source: str = FLOW_SOURCE
) -> tuple[list[dict[str, Any]], int]:
    """→ (rows, dropped_count). ts = alert created_at (stable across refetch)."""
    rows: list[dict[str, Any]] = []
    dropped = 0
    for a in alerts:
        occ = str(a.get("option_chain") or "").replace(" ", "").replace("_", "").upper()
        ts = parse_ts(a.get("created_at")) or parse_ts(a.get("start_time"))
        price = to_float(a.get("price"))
        opt_type = str(a.get("type") or "").lower()
        right = "C" if opt_type.startswith("c") else ("P" if opt_type.startswith("p") else "")
        expiry = str(a.get("expiry") or "")[:10]
        strike = to_float(a.get("strike"))
        ticker = str(a.get("ticker") or "").strip().upper()
        if not (
            occ and ts and price is not None and right and expiry
            and strike is not None and ticker
        ):
            dropped += 1
            continue
        rows.append(
            {
                "occ": occ,
                "ts": ts,
                "seq": 0,
                "ticker": ticker,
                "expiry": dt.date.fromisoformat(expiry),
                "strike": strike,
                "opt_right": right,
                "price": price,
                "size": to_int(a.get("total_size")) or 0,
                "premium": to_float(a.get("total_premium")),
                "side": None,  # bid/ask-side split exists upstream as premium
                                # aggregates; per-print side is not served
                "bid": to_float(a.get("bid")),
                "ask": to_float(a.get("ask")),
                "spot": to_float(a.get("underlying_price")),
                "is_sweep": bool(a.get("has_sweep")),
                "is_multileg": bool(a.get("has_multileg")),
                "source": source,
            }
        )
    return rows, dropped


def map_darkpool_rows(
    trades: Sequence[Mapping[str, Any]], *, source: str = DARKPOOL_SOURCE
) -> tuple[list[dict[str, Any]], int]:
    """→ (rows, dropped_count). seq = tracking_id (unique within the second).
    Canceled prints are dropped — upstream marks them, we never invent them."""
    rows: list[dict[str, Any]] = []
    dropped = 0
    for t in trades:
        if t.get("canceled"):
            dropped += 1
            continue
        ticker = str(t.get("ticker") or "").strip().upper()
        ts = parse_ts(t.get("executed_at")) or parse_ts(t.get("created_at"))
        price = to_float(t.get("price"))
        if not (ticker and ts and price is not None):
            dropped += 1
            continue
        rows.append(
            {
                "ticker": ticker,
                "ts": ts,
                "seq": to_int(t.get("tracking_id")) or 0,
                "price": price,
                "size": to_int(t.get("size")) or 0,
                "premium": to_float(t.get("premium")),
                "venue": t.get("market_center"),
                "source": source,
            }
        )
    return rows, dropped


async def write_flow_prints(db: Database, rows: Sequence[Mapping[str, Any]]) -> int:
    return await write_rows(db, "flow_print", rows)


async def write_darkpool_prints(db: Database, rows: Sequence[Mapping[str, Any]]) -> int:
    return await write_rows(db, "darkpool_print", rows)
