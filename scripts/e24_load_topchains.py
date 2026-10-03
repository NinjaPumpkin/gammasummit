#!/usr/bin/env python3
"""e24_load_topchains.py — real UW daily top-chains pulls -> contract_daily_stats.

data/e08/topchains_YYYY-MM-DD.json holds one real UW top-chains pull per trade
date (per-contract volume/OI/prev_oi/bid-ask-mid volume/avg price). Migration
0002's ContractStats row shape is the natural home; the mapping is 1:1 where
the source serves a value and honest NULL elsewhere (E0.2-era pulls carry no
premium/sweep/multi-leg/iv/trade_count — never invented):

  trade_date -> date, option_symbol -> occ, side -> "right", expiry -> expiration
  volume -> total_volume, avg_price -> vwap
  oi_change = open_interest - prev_oi (arithmetic on served fields, 0002 note)
  dte = (expiration - date).days
  total_premium, sweep_*, multi_leg_*, last_price, underlying_price, iv,
  trade_count -> NULL

source = 'uw_top_chains' on every row. INSERT-only (ON CONFLICT DO NOTHING):
an existing (date, occ) row is NEVER overwritten — same non-destructive law as
scripts/e08_contract_daily_persist.py.

Dry-run is DEFAULT; --execute writes.

CLI:
  python3 scripts/e24_load_topchains.py --dry-run
  python3 scripts/e24_load_topchains.py --execute [--dates 2026-09-25,2026-10-01]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import glob
import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from backend.core.config import get_settings  # noqa: E402
from backend.core.db import Database  # noqa: E402

DEFAULT_DIR = os.path.join(REPO, "data", "e08")
SOURCE = "uw_top_chains"

INSERT_SQL = (
    "INSERT INTO contract_daily_stats "
    "(date, occ, ticker, expiration, strike, \"right\", dte, total_volume, "
    " open_interest, prev_oi, oi_change, bid_volume, ask_volume, mid_volume, "
    " vwap, source) "
    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) "
    "ON CONFLICT (date, occ) DO NOTHING"
)


def map_row(row: dict, day: dt.date) -> tuple:
    exp = dt.date.fromisoformat(row["expiry"])
    oi = row.get("open_interest")
    prev = row.get("prev_oi")
    oi_change = (oi - prev) if (oi is not None and prev is not None) else None
    return (
        day,
        row["option_symbol"],
        row["ticker"],
        exp,
        float(row["strike"]),
        row["side"],
        (exp - day).days,
        row.get("volume"),
        oi,
        prev,
        oi_change,
        row.get("bid_volume"),
        row.get("ask_volume"),
        row.get("mid_volume"),
        row.get("avg_price"),
        SOURCE,
    )


async def main() -> int:
    ap = argparse.ArgumentParser(description="UW top-chains -> contract_daily_stats")
    ap.add_argument("--dry-run", action="store_true", help="counts only (default)")
    ap.add_argument("--execute", action="store_true", help="insert rows")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="directory holding topchains_*.json")
    ap.add_argument("--dates", default="", help="comma list of trade dates (default: all)")
    ap.add_argument("--report", default="")
    args = ap.parse_args()
    execute = args.execute and not args.dry_run
    want = {d.strip() for d in args.dates.split(",") if d.strip()}

    per_date: Counter = Counter()
    rows: list[tuple] = []
    files = sorted(glob.glob(os.path.join(args.dir, "topchains_*.json")))
    for path in files:
        day_s = os.path.basename(path)[len("topchains_"):-len(".json")]
        if want and day_s not in want:
            continue
        day = dt.date.fromisoformat(day_s)
        with open(path) as fh:
            data = json.load(fh)
        for row in data:
            if not isinstance(row, dict):
                continue
            rows.append(map_row(row, day))
            per_date[day_s] += 1

    report = {
        "mode": "execute" if execute else "dry-run (no writes)",
        "source": SOURCE,
        "files_scanned": len(files),
        "dates": dict(sorted(per_date.items())),
        "rows_planned": len(rows),
        "inserted": 0,
    }

    if execute:
        settings = get_settings()
        if not settings.database_url:
            print("GAMMASUMMIT_DATABASE_URL is required", file=sys.stderr)
            return 2
        db = Database(settings.database_url)
        await db.connect()
        try:
            result = await db.executemany(INSERT_SQL, list(rows))
            report["inserted"] = str(result)
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
