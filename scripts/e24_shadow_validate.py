#!/usr/bin/env python3
"""e24_shadow_validate.py — the shadow-validation harness (card E2.4).

Measured evidence that the shadow dataset sits at its TARGET tiers per
docs/ops/data-tiering.md with the hot set inside budget. One measurement run
covers every trading day of data present in the pipeline:

  per day   rows at T0 / T1 / T2 / T3 (verified exports) / daily tables
            + distinct `source` provenance values actually present
            + tier-placement verdict vs the retention law
            (T0 24-48h, T1 30d, T2 90d-1yr, T3 indefinite — a day that aged
            out of a window must have left that tier)
  global    hot-set bytes per tier via pg_total_relation_size (partitions +
            indexes included) vs the 10 GB budget
            + the freshness verdicts (backend/jobs/freshness.py — one truth)

It RUNS DAILY AND ACCUMULATES (the E0.2 refit-cadence pattern): --execute
appends one run record to data/e24_shadow/measurements.json and re-renders
docs/data/e24-shadow-validation.md from the latest run. The measurement table
grows one trading day per RTH session until (and beyond) the 5-day gate.

Nothing here writes tier data. Dry-run is the DEFAULT (measure + print, zero
writes). `--as-of` shifts threshold evaluation only (verification hook, same
pattern as export_cold/freshness — data untouched).

CLI:
  python3 scripts/e24_shadow_validate.py --dry-run
  python3 scripts/e24_shadow_validate.py --execute [--report data/e24_shadow/run.json]
  python3 scripts/e24_shadow_validate.py --execute --as-of 2026-10-05T14:30:00Z
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import sys
from typing import Any, Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from backend.core.config import get_settings  # noqa: E402
from backend.core.db import Database  # noqa: E402
from backend.jobs.freshness import FreshnessJob  # noqa: E402

DATA_DIR = os.path.join(REPO, "data", "e24_shadow")
MEASUREMENTS = os.path.join(DATA_DIR, "measurements.json")
DOCS_TABLE = os.path.join(REPO, "docs", "data", "e24-shadow-validation.md")
TARGET_TRADING_DAYS = 5  # the card's accrual gate (N/5)

# (table, tier, SQL day expression in UTC). Tables are code constants (never
# user input) — same law as core.db.upsert_sql.
DAY_TABLES: tuple[tuple[str, str, str], ...] = (
    ("gamma_snapshot", "T0", "(ts AT TIME ZONE 'UTC')::date"),
    ("spot_tick", "T0", "(ts AT TIME ZONE 'UTC')::date"),
    ("flow_print", "T0", "(ts AT TIME ZONE 'UTC')::date"),
    ("darkpool_print", "T0", "(ts AT TIME ZONE 'UTC')::date"),
    ("gamma_bucket_5m", "T1", "(bucket AT TIME ZONE 'UTC')::date"),
    ("expiry_rollup_hourly", "T2", "(hour AT TIME ZONE 'UTC')::date"),
    ("strike_eod", "T2", "day"),
    ("contract_daily_stats", "daily", "date"),
    ("underlying_daily_stats", "daily", "date"),
)
TIER_TABLES = {
    "T0": ["gamma_snapshot", "spot_tick", "flow_print", "darkpool_print"],
    "T1": ["gamma_bucket_5m"],
    "T2": ["expiry_rollup_hourly", "strike_eod"],
    "daily": ["contract_daily_stats", "underlying_daily_stats"],
}

HOT_TIERS = ("T0", "T1", "T2")  # the budget covers the tier tables; daily stats ride along in the report
T1_WINDOW_DAYS = 30  # law, not configurable (config.py comment)
MANIFEST_DATE_RE = re.compile(r"date=(\d{4}-\d{2}-\d{2})")
MANIFEST_TABLE_RE = re.compile(r"/(gamma|spot|flow|darkpool|gamma_bucket_5m|expiry_rollup_hourly|strike_eod)/")

HOT_SET_SQL = """
WITH fam AS (
    SELECT i.inhrelid AS rel FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhparent
    WHERE c.relname = ANY($1::text[])
    UNION
    SELECT c.oid FROM pg_class c
    WHERE c.relname = ANY($1::text[]) AND c.relkind IN ('r', 'p')
)
SELECT sum(pg_total_relation_size(rel))::bigint AS bytes FROM fam
"""


def _utc_day(value: dt.datetime) -> dt.date:
    return value.astimezone(dt.timezone.utc).date()


async def measure(db: Database, *, as_of: dt.datetime, t2_days: int,
                  raw_hours: int, budget_bytes: int,
                  t3_root: str = "") -> dict[str, Any]:
    # 1. per-day per-table row counts + provenance
    day_rows: dict[str, dict[str, dict[str, int]]] = {}
    day_sources: dict[str, set] = {}
    for table, tier, day_expr in DAY_TABLES:
        rows = await db.fetch(
            f"SELECT {day_expr} AS d, count(*) AS n FROM {table} GROUP BY 1"  # noqa: S608
        )
        for r in rows:
            if r["d"] is None:
                continue
            day_rows.setdefault(str(r["d"]), {}).setdefault(tier, {})[table] = int(r["n"])
        if tier == "T0" or tier == "daily":
            src_col = "source"
            try:
                srows = await db.fetch(
                    f"SELECT DISTINCT {day_expr} AS d, {src_col} AS s FROM {table}"  # noqa: S608
                )
            except Exception:  # noqa: BLE001 — a table without source must not break the run
                continue
            for r in srows:
                if r["d"] is not None and r["s"]:
                    day_sources.setdefault(str(r["d"]), set()).add(str(r["s"]))

    # 2. T3 archive rows per day (export_manifest: hive path carries date=)
    manifest_rows = await db.fetch(
        "SELECT file_path, tier, target, row_count, verified_at FROM export_manifest"
    )
    t3_rows: dict[str, dict[str, int]] = {}
    t3_verified: dict[str, dict[str, int]] = {}
    t3_unverified: dict[str, int] = {}
    for m in manifest_rows:
        mday = MANIFEST_DATE_RE.search(m["file_path"])
        if not mday:
            continue
        day = mday.group(1)
        target = m["target"]
        t3_rows.setdefault(day, {})[target] = t3_rows.setdefault(day, {}).get(target, 0) + int(m["row_count"] or 0)
        if m["verified_at"] is not None:
            t3_verified.setdefault(day, {})[target] = t3_verified.setdefault(day, {}).get(target, 0) + int(m["row_count"] or 0)
        else:
            t3_unverified[day] = t3_unverified.get(day, 0) + 1

    for day in t3_rows:
        day_rows.setdefault(day, {})

    # 2b. provenance from the ARCHIVED rows themselves: once retention drops
    # aged T0 rows, the only surviving per-row `source` values live in the
    # T3 Parquet (measured there — not remembered). export_manifest.file_path
    # is relative to the T3 root (retention.py cold layout).
    for m in manifest_rows:
        mday = MANIFEST_DATE_RE.search(m["file_path"])
        full = os.path.join(t3_root, m["file_path"]) if t3_root else m["file_path"]
        if not mday or not os.path.exists(full):
            continue
        try:
            import pyarrow.parquet as pq  # noqa: PLC0415 — evidence-path only

            # iter_batches, not read(): per-file row groups carry mixed
            # string/dictionary encodings and merge fails on full reads
            # (E2.3 ArrowTypeError finding). Column-only batches are fine.
            pf = pq.ParquetFile(full)
            values = set()
            for batch in pf.iter_batches(columns=["source"], batch_size=8192):
                values.update(str(v) for v in batch.column("source").to_pylist() if v)
        except Exception:  # noqa: BLE001 — a segment without source must not break the run
            continue
        if values:
            day_sources.setdefault(mday.group(1), set()).update(values)

    # 3. per-day placement verdict vs the tier law
    days: list[dict[str, Any]] = []
    for day_s in sorted(day_rows):
        day = dt.date.fromisoformat(day_s)
        day_end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(), tzinfo=dt.timezone.utc)
        age_h = (as_of - day_end).total_seconds() / 3600.0
        rows = day_rows[day_s]
        t0 = sum(rows.get("T0", {}).values())
        t1 = sum(rows.get("T1", {}).values())
        t2 = sum(rows.get("T2", {}).values())
        daily = sum(rows.get("daily", {}).values())
        t3 = sum(t3_rows.get(day_s, {}).values())
        details: list[str] = []
        if age_h >= raw_hours and t0:
            details.append(f"aged {age_h:.0f}h (>= {raw_hours}h) but {t0} T0 rows remain — retention/export pending or broken")
        if age_h >= T1_WINDOW_DAYS * 24 and t1:
            details.append(f"aged {age_h:.0f}h (>= {T1_WINDOW_DAYS}d) but {t1} T1 rows remain — export_cold window passed")
        if age_h >= t2_days * 24 and t2:
            details.append(f"aged {age_h:.0f}h (>= {t2_days}d) but {t2} T2 rows remain — export_cold window passed")
        if t3_unverified.get(day_s):
            details.append(f"{t3_unverified[day_s]} T3 manifests for this day are UNVERIFIED")
        session_day = day.weekday() < 5
        days.append({
            "day": day_s,
            "session_day": session_day,
            "age_h": round(age_h, 1),
            "rows": {"T0": t0, "T1": t1, "T2": t2, "T3": t3, "daily": daily},
            "rows_by_table": rows,
            "t3_rows_by_target": t3_rows.get(day_s, {}),
            "t3_verified_rows": sum(t3_verified.get(day_s, {}).values()),
            "sources": sorted(day_sources.get(day_s, set())),
            "placement": {"verdict": "ok" if not details else "violation", "details": details},
        })

    # 4. hot set per tier (partitions + indexes included) vs budget
    hot_set: dict[str, Any] = {"per_tier_bytes": {}, "per_tier_rows": {}}
    for tier in HOT_TIERS + ("daily",):
        val = await db.fetchval(HOT_SET_SQL, TIER_TABLES[tier])
        hot_set["per_tier_bytes"][tier] = int(val or 0)
        n = 0
        for table in TIER_TABLES[tier]:
            n += int(await db.fetchval(f"SELECT count(*) FROM {table}"))  # noqa: S608
        hot_set["per_tier_rows"][tier] = n
    hot_set["total_bytes"] = sum(hot_set["per_tier_bytes"][t] for t in HOT_TIERS)
    hot_set["budget_bytes"] = budget_bytes
    hot_set["within_budget"] = hot_set["total_bytes"] <= budget_bytes

    # 5. freshness snapshot (one truth with the alarms)
    freshness = await FreshnessJob(db).run(as_of=as_of)

    session_days = [d for d in days if d["session_day"]]
    return {
        "as_of": as_of.isoformat(),
        "days": days,
        "session_days": len(session_days),
        "target_trading_days": TARGET_TRADING_DAYS,
        "hot_set": hot_set,
        "freshness_overall": freshness["overall"],
        "freshness_checks": freshness["checks"],
    }


# ------------------------------------------------------------- docs renderer
def render_markdown(run: dict[str, Any], history: list[dict[str, Any]]) -> str:
    hs = run["hot_set"]
    lines = [
        "# E2.4 shadow validation — 5-trading-day measurement",
        "",
        "Generated by `scripts/e24_shadow_validate.py --execute` (the daily",
        "shadow-validation harness). Every number is MEASURED on real UW rows in",
        "the live tier pipeline — rows per tier, T3 verified exports, hot-set",
        "bytes (pg_total_relation_size, partitions + indexes), freshness verdicts.",
        "Rows accrue one trading day per RTH session (the E0.2 refit-cadence",
        "pattern); this table re-renders from the latest run.",
        "",
        f"**Last updated:** {run['as_of']} · **Trading days measured:** "
        f"{run['session_days']}/{run['target_trading_days']}",
        "",
        "## Per-trading-day placement (target tiers per data-tiering.md)",
        "",
        "| session day | T0 rows | T1 rows | T2 rows | T3 rows (verified) | daily rows | sources | placement |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for d in run["days"]:
        if not d["session_day"]:
            continue
        r = d["rows"]
        src = ", ".join(d["sources"]) if d["sources"] else "—"
        mark = "✓ " + d["placement"]["verdict"] if d["placement"]["verdict"] == "ok" else "✗ violation"
        lines.append(
            f"| {d['day']} | {r['T0']:,} | {r['T1']:,} | {r['T2']:,} "
            f"| {d['t3_verified_rows']:,} | {r['daily']:,} | {src} | {mark} |"
        )
    non_session = [d for d in run["days"] if not d["session_day"]]
    if non_session:
        lines += ["", "Non-session payload days (weekend-timestamped upstream rows, kept and measured):", ""]
        for d in non_session:
            r = d["rows"]
            lines.append(f"- {d['day']} (payload): T0 {r['T0']:,} · T3 {d['t3_verified_rows']:,} · sources "
                         + (", ".join(d["sources"]) or "—"))
    for d in run["days"]:
        for detail in d["placement"]["details"]:
            lines.append(f"- **{d['day']}**: {detail}")
    lines += [
        "",
        "## Hot set vs budget",
        "",
        "| tier | tables | rows | bytes |",
        "|---|---|---|---|",
    ]
    tier_tables = {"T0": "gamma_snapshot + spot + flow + darkpool", "T1": "gamma_bucket_5m",
                   "T2": "expiry_rollup_hourly + strike_eod", "daily": "contract/underlying_daily_stats"}
    for tier in ("T0", "T1", "T2", "daily"):
        lines.append(f"| {tier} | {tier_tables[tier]} | {hs['per_tier_rows'][tier]:,} | {hs['per_tier_bytes'][tier]:,} |")
    verdict = "YES" if hs["within_budget"] else "NO"
    lines += [
        f"| **hot set (T0+T1+T2)** | | | **{hs['total_bytes']:,}** |",
        "",
        f"Budget anchor: `docs/ops/risks-and-toolkit.md` (5–10 GB is snappy → cap "
        f"{hs['budget_bytes']:,} bytes). **≤ budget: {verdict}**.",
        "",
        "## Freshness snapshot (same metric the alarms use)",
        "",
        "| check | verdict | detail |",
        "|---|---|---|",
    ]
    for c in run["freshness_checks"]:
        lines.append(f"| {c['id']} | {c['verdict']} | {c['detail']} |")
    lines += [
        "",
        "## Run log (accumulates daily)",
        "",
        "| run as-of | session days | hot-set bytes | freshness |",
        "|---|---|---|---|",
    ]
    for h in history:
        lines.append(f"| {h['as_of']} | {h['session_days']}/{h['target_trading_days']} "
                     f"| {h['hot_set']['total_bytes']:,} | {h['freshness_overall']} |")
    lines += [
        "",
        "Tier law reference: `docs/ops/data-tiering.md`. Alarm wiring:",
        "`docs/ops/operations.md` (Uptime Kuma push monitors + freshness.py beacons).",
        "",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------------ CLI
def _parse_ts(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Shadow validation: tier placement + hot set + freshness")
    ap.add_argument("--dry-run", action="store_true", help="measure + print only (default)")
    ap.add_argument("--execute", action="store_true", help="append run to accumulator + re-render docs table")
    ap.add_argument("--as-of", default="", help="clock hook for threshold evaluation (data untouched)")
    ap.add_argument("--report", default="", help="write the run JSON here")
    args = ap.parse_args()
    execute = args.execute and not args.dry_run

    settings = get_settings()
    if not settings.database_url:
        print("GAMMASUMMIT_DATABASE_URL is required", file=sys.stderr)
        return 2
    as_of = _parse_ts(args.as_of) if args.as_of else dt.datetime.now(tz=dt.timezone.utc)

    db = Database(settings.database_url)
    await db.connect()
    try:
        run = await measure(
            db, as_of=as_of, t2_days=settings.retention_t2_days,
            raw_hours=settings.retention_raw_hours,
            budget_bytes=settings.hot_set_budget_bytes,
            t3_root=settings.t3_root,
        )
    finally:
        await db.close()

    history: list[dict[str, Any]] = []
    if os.path.exists(MEASUREMENTS):
        with open(MEASUREMENTS) as fh:
            history = json.load(fh).get("runs", [])

    if execute:
        history.append(run)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(MEASUREMENTS, "w", encoding="utf-8") as fh:
            json.dump({"runs": history}, fh, indent=1, default=str)
        with open(DOCS_TABLE, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(run, history))
        run["written"] = {"measurements": MEASUREMENTS, "docs_table": DOCS_TABLE}

    text = json.dumps(run, indent=1, default=str)
    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)

    violations = [d for d in run["days"] if d["placement"]["verdict"] != "ok"]
    ok = not violations and run["hot_set"]["within_budget"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
