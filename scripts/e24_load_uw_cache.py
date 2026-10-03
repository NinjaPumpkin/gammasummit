#!/usr/bin/env python3
"""e24_load_uw_cache.py — real UW chain snapshots (data/e02/uw_cache) -> T0.

The E0.2 capture archive holds real UW gamma-batch rows per ticker per capture
moment (strike cells with call/put OI, volume, gex, dex, iv, spot). Those rows
are exactly the T0 cell shape (chain_writer merges call/put per strike the same
way), so this loader round-trips them into `gamma_snapshot` + `spot_tick` —
the documented rebuild path, nothing synthesized:

  cell fields  ->  gamma_snapshot columns, 1:1 where the source serves them
  call_dex/put_dex -> call_delta/put_delta (UW's own per-side deltas)
  iv           ->  NOT mapped: UW serves ONE blended iv per cell, the schema
                   has per-side call_iv/put_iv. Both stay NULL (E2.2 rule:
                   nothing invented).
  gamma/vega/theta, bid/ask prices -> NULL (not served by this endpoint).

source = 'uw_gamma_v2' on every row for provenance.

Dry-run is DEFAULT (per-date counts, zero writes); --execute upserts
(idempotent conflict keys — re-running overwrites identical rows).

CLI:
  python3 scripts/e24_load_uw_cache.py --dry-run
  python3 scripts/e24_load_uw_cache.py --execute [--dates 2026-09-28,2026-09-29]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import glob
import gzip
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from backend.core.config import get_settings  # noqa: E402
from backend.core.db import Database, upsert_rows  # noqa: E402

DEFAULT_CACHE = os.path.join(REPO, "data", "e02", "uw_cache")
SOURCE = "uw_gamma_v2"

GAMMA_KEYS = ("ticker", "expiry", "strike", "ts", "spot",
              "call_oi", "put_oi", "call_volume", "put_volume",
              "call_delta", "put_delta", "source")
GAMMA_CONFLICT = ("ticker", "expiry", "strike", "ts")
SPOT_KEYS = ("ticker", "ts", "seq", "price", "size", "source")
SPOT_CONFLICT = ("ticker", "ts", "seq")


def load_rows(path: str) -> list[dict]:
    with gzip.open(path, "rt") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and all(isinstance(r, dict) for r in v):
                return v
    return []


def map_row(row: dict) -> dict:
    return {
        "ticker": row["ticker"],
        "expiry": dt.date.fromisoformat(row["expiry_date"]),
        "strike": float(row["strike"]),
        "ts": dt.datetime.fromisoformat(row["timestamp"]),
        "spot": row.get("spot_price"),
        "call_oi": row.get("call_oi"),
        "put_oi": row.get("put_oi"),
        "call_volume": row.get("call_volume"),
        "put_volume": row.get("put_volume"),
        "call_delta": row.get("call_dex"),
        "put_delta": row.get("put_dex"),
        "source": SOURCE,
    }


def map_spot(row: dict) -> dict:
    return {
        "ticker": row["ticker"],
        "ts": dt.datetime.fromisoformat(row["timestamp"]),
        "seq": 0,
        "price": row.get("spot_price"),
        "size": None,
        "source": SOURCE,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description="UW cache snapshots -> T0 (real rows)")
    ap.add_argument("--dry-run", action="store_true", help="counts only (default)")
    ap.add_argument("--execute", action="store_true", help="upsert rows into T0")
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument("--dates", default="", help="comma list of payload dates to load (default: all)")
    ap.add_argument("--report", default="")
    args = ap.parse_args()
    execute = args.execute and not args.dry_run
    want = {d.strip() for d in args.dates.split(",") if d.strip()}

    gamma_rows: list[dict] = []
    spot_rows: list[dict] = []
    seen_spot: set[tuple] = set()
    per_date: Counter = Counter()
    empty_files = 0
    files = sorted(glob.glob(os.path.join(args.cache, "*.json.gz")))
    for path in files:
        rows = load_rows(path)
        if not rows:
            empty_files += 1
            continue
        for row in rows:
            g = map_row(row)
            if want and str(g["ts"])[:10] not in want:
                continue
            gamma_rows.append(g)
            per_date[str(g["ts"])[:10]] += 1
            s = map_spot(row)
            key = (s["ticker"], s["ts"], s["seq"])
            if key not in seen_spot:
                seen_spot.add(key)
                spot_rows.append(s)

    report = {
        "mode": "execute" if execute else "dry-run (no writes)",
        "source": SOURCE,
        "files_scanned": len(files),
        "empty_files_skipped": empty_files,
        "dates": dict(sorted(per_date.items())),
        "rows_planned": {"gamma_snapshot": len(gamma_rows), "spot_tick": len(spot_rows)},
        "written": {},
    }

    if execute:
        settings = get_settings()
        if not settings.database_url:
            print("GAMMASUMMIT_DATABASE_URL is required", file=sys.stderr)
            return 2
        db = Database(settings.database_url)
        await db.connect()
        try:
            report["written"]["gamma_snapshot"] = await upsert_rows(
                db, "gamma_snapshot", gamma_rows, GAMMA_CONFLICT)
            report["written"]["spot_tick"] = await upsert_rows(
                db, "spot_tick", spot_rows, SPOT_CONFLICT)
        finally:
            await db.close()

    text = json.dumps(report, indent=1, default=str)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
