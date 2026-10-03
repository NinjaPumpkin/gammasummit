#!/usr/bin/env python3
"""e23_reload_t0.py — reload real T0 rows from a T3 Parquet export tree.

The E2.2 retention export (scratch `t3_shadow/`, hive layout
`<sub>/ticker=<T>/date=<D>/part-*.parquet`) holds the real UW PHX shadow
captures. This loader feeds them back into T0 — the documented recovery path
("rollups recomputable from T0 within 48h or T3 after export") — so the E2.3
tier chain can run end-to-end on real shadow data.

Dry-run is the DEFAULT (counts only, zero writes); --execute upserts.
Nothing here synthesizes a single value: every row round-trips through Parquet
as captured.

CLI:
  python3 scripts/e23_reload_t0.py --dry-run
  python3 scripts/e23_reload_t0.py --execute [--t3-root <tree>]
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from backend.core.config import get_settings  # noqa: E402
from backend.core.db import Database, upsert_rows  # noqa: E402

DEFAULT_ROOT = os.path.join(
    "/Users/admin/hermes/profiles/gammasummit-backend/cache/scratch", "t3_shadow"
)

# cold subdir -> (table, PK conflict keys)  [inverse of jobs/retention.py T0_SEGMENTS]
SEGMENTS = {
    "gamma": ("gamma_snapshot", ("ticker", "expiry", "strike", "ts")),
    "spot": ("spot_tick", ("ticker", "ts", "seq")),
    "flow": ("flow_print", ("occ", "ts", "seq")),
    "darkpool": ("darkpool_print", ("ticker", "ts", "seq")),
}


def read_segment(path: str) -> list[dict]:
    """Read ONE parquet FILE (never the hive dataset — the ticker=/date= path
    columns collide with real columns; E2.2 finding)."""
    import pyarrow.parquet as pq  # noqa: PLC0415

    return pq.ParquetFile(path).read().to_pylist()


async def main() -> int:
    ap = argparse.ArgumentParser(description="T3 parquet -> T0 reload (real rows)")
    ap.add_argument("--dry-run", action="store_true", help="counts only (default)")
    ap.add_argument("--execute", action="store_true", help="upsert rows into T0")
    ap.add_argument("--t3-root", default=DEFAULT_ROOT)
    ap.add_argument("--report", default="")
    args = ap.parse_args()
    execute = args.execute and not args.dry_run

    settings = get_settings()
    if not settings.database_url:
        print("GAMMASUMMIT_DATABASE_URL is required", file=sys.stderr)
        return 2

    plan = {}
    for sub, (table, keys) in SEGMENTS.items():
        files = sorted(glob.glob(os.path.join(args.t3_root, sub, "**", "*.parquet"),
                                 recursive=True))
        rows = []
        for f in files:
            if os.path.basename(f).startswith("._"):
                continue  # macOS AppleDouble sidecar on exFAT (E2.3 finding — not data)
            rows.extend(read_segment(f))
        plan[table] = {"keys": keys, "files": len(files), "rows": rows}

    report = {
        "mode": "execute" if execute else "dry-run (no writes)",
        "t3_root": args.t3_root,
        "tables": {t: {"files": p["files"], "rows": len(p["rows"])} for t, p in plan.items()},
        "written": {},
    }

    if execute:
        db = Database(settings.database_url)
        await db.connect()
        try:
            for table, p in plan.items():
                report["written"][table] = await upsert_rows(db, table, p["rows"], p["keys"])
        finally:
            await db.close()

    import json  # noqa: PLC0415

    text = json.dumps(report, indent=1, default=str)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
