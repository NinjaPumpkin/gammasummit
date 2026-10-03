"""Tier rollup jobs (tree: jobs/rollups.py) — card E2.3.

Two idempotent T1/T2 jobs (docs/ops/data-tiering.md is law):

  DownsamplerJob  T0 -> T1: gamma_snapshot -> gamma_bucket_5m (5-min buckets)
  RollupsJob      T1 -> T2: gamma_bucket_5m -> expiry_rollup_hourly
                            + strike_eod (per-strike EOD chains)

GEX convention (the documented heatmap GEX mode of
docs/ops/signalforge-knowledge-transfer.md: `gamma x 100 x 0.01 x OI x S^2`,
contract multiplier 100 and the per-1% scaling 0.01 cancel to 1):

    strike gex = gamma x OI x spot^2      (per strike side; net = call - put)

This is the same within-expiry `net_gex = call_gex - put_gex` law as
core/exposure.py — the jobs compute per-strike aggregates, exposure.py owns
the value model on top. Rollup rows carry schema_version = 1:
bucket-average gamma basis, GEX only — call_vex/put_vex/net_vex stay NULL
(no vanna is served by UW PHX; nothing is synthesized).

Volume semantics (PHX `volume` is cumulative-since-session-open per contract):
a bucket's volume is the counter growth attributed to the bucket of the later
observation — `last_in_bucket - last_before_bucket`, with a counter RESET
(growth seen as a drop = new session) attributing the full counter to that
bucket. Summing a day's buckets telescopes to the day's cumulative total.

Both jobs are recomputable end-to-end from T0 (law: "rollups recomputable from
T0 within 48h or T3 after export") — every write is a conflict-key upsert, so
re-running any window overwrites identical rows instead of duplicating.

Dry-run is the DEFAULT (hard rule): it runs the aggregate SELECTs and reports
what WOULD be written with zero writes.

CLI:
  python -m backend.jobs.rollups --dry-run                      # plan (default)
  python -m backend.jobs.rollups --execute                      # write T1 + T2
  python -m backend.jobs.rollups --execute --since 2026-10-01T00:00Z \\
      --until 2026-10-02T00:00Z                                 # backfill window
  python -m backend.jobs.rollups --execute --downsample-only    # T0 -> T1 only
  python -m backend.jobs.rollups --execute --rollup-only        # T1 -> T2 only
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from typing import Any, Optional, Sequence

from backend.core.config import get_settings
from backend.core.db import Database, upsert_rows
from backend.core.errors import ConfigError
from backend.core.logging import configure_logging, get_logger

log = get_logger(__name__)

BUCKET_S = 300          # T1 grain: 5-min buckets (law)
HOUR_S = 3600           # T2 grain: hourly rollups (law)
ROLLUP_SCHEMA_VERSION = 1  # bucket-avg gamma basis, GEX only (see docstring)
RAW_HORIZON_HOURS = 48  # default downsample window = the raw retention horizon


def _aware(value: Any) -> Any:
    """asyncpg hands back naive UTC datetimes; keep every written ts aware."""
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


def _rows_to_dicts(
    rows: Sequence[Any], extra: Optional[dict[str, Any]] = None
) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        d = {k: _aware(v) for k, v in dict(r).items()}
        if extra:
            d.update(extra)
        out.append(d)
    return out


def gex(gamma: Optional[float], oi: Optional[float], spot: Optional[float]) -> Optional[float]:
    """Per-strike side GEX = gamma x OI x spot^2 (heatmap GEX mode, see above).

    NULL in, NULL out — nothing is synthesized from missing inputs.
    """
    if gamma is None or oi is None or spot is None:
        return None
    return gamma * float(oi) * spot * spot


def net(call: Optional[float], put: Optional[float]) -> Optional[float]:
    """Within-expiry net gex = call_gex - put_gex (established math, spec §2)."""
    if call is None or put is None:
        return None
    return call - put


# ---------------------------------------------------------------------------
# T0 -> T1: 5-min buckets.
#
# Window functions see each cell's FULL T0 history (the scoped CTE selects
# cells, not rows) so the volume-delta prev sample is correct even when the
# recomputed window starts mid-history.
# ---------------------------------------------------------------------------
DOWNSAMPLE_SQL = """
WITH scoped AS (
    SELECT DISTINCT ticker, expiry, strike
    FROM gamma_snapshot
    WHERE ts >= $1 AND ts < $2
),
w AS (
    SELECT g.ticker, g.expiry, g.strike,
           to_timestamp(floor(extract(epoch FROM g.ts) / 300.0) * 300) AS bucket,
           g.call_oi, g.put_oi, g.call_volume, g.put_volume,
           g.call_gamma, g.put_gamma, g.call_iv, g.put_iv, g.spot,
           lag(g.call_volume) OVER cell AS call_volume_prev,
           lag(g.put_volume)  OVER cell AS put_volume_prev,
           row_number() OVER bkt      AS rn_first,
           row_number() OVER bkt_desc AS rn_last
    FROM gamma_snapshot g
    JOIN scoped s
      ON s.ticker = g.ticker AND s.expiry = g.expiry AND s.strike = g.strike
    WINDOW cell AS (PARTITION BY g.ticker, g.expiry, g.strike ORDER BY g.ts),
           bkt AS (PARTITION BY g.ticker, g.expiry, g.strike,
                   to_timestamp(floor(extract(epoch FROM g.ts) / 300.0) * 300)
                   ORDER BY g.ts),
           bkt_desc AS (PARTITION BY g.ticker, g.expiry, g.strike,
                   to_timestamp(floor(extract(epoch FROM g.ts) / 300.0) * 300)
                   ORDER BY g.ts DESC)
)
SELECT ticker, expiry, strike, bucket,
       max(call_oi) FILTER (WHERE rn_first = 1) AS call_oi_first,
       max(call_oi) FILTER (WHERE rn_last = 1)  AS call_oi_last,
       max(put_oi)  FILTER (WHERE rn_first = 1) AS put_oi_first,
       max(put_oi)  FILTER (WHERE rn_last = 1)  AS put_oi_last,
       CASE
           WHEN max(call_volume) FILTER (WHERE rn_last = 1) IS NULL THEN NULL
           WHEN max(call_volume_prev) FILTER (WHERE rn_first = 1) IS NULL
                OR max(call_volume) FILTER (WHERE rn_last = 1)
                   < max(call_volume_prev) FILTER (WHERE rn_first = 1)
           THEN max(call_volume) FILTER (WHERE rn_last = 1)
           ELSE max(call_volume) FILTER (WHERE rn_last = 1)
                - max(call_volume_prev) FILTER (WHERE rn_first = 1)
       END AS call_volume,
       CASE
           WHEN max(put_volume) FILTER (WHERE rn_last = 1) IS NULL THEN NULL
           WHEN max(put_volume_prev) FILTER (WHERE rn_first = 1) IS NULL
                OR max(put_volume) FILTER (WHERE rn_last = 1)
                   < max(put_volume_prev) FILTER (WHERE rn_first = 1)
           THEN max(put_volume) FILTER (WHERE rn_last = 1)
           ELSE max(put_volume) FILTER (WHERE rn_last = 1)
                - max(put_volume_prev) FILTER (WHERE rn_first = 1)
       END AS put_volume,
       avg(call_gamma) AS call_gamma_avg,
       avg(put_gamma)  AS put_gamma_avg,
       avg(call_iv)    AS call_iv_avg,
       avg(put_iv)     AS put_iv_avg,
       max(spot) FILTER (WHERE rn_last = 1) AS spot_close,
       count(*) AS samples
FROM w
WHERE bucket >= $1 AND bucket < $2
GROUP BY ticker, expiry, strike, bucket
ORDER BY ticker, expiry, strike, bucket
"""

T1_COLUMNS = (
    "ticker", "expiry", "strike", "bucket",
    "call_oi_first", "call_oi_last", "put_oi_first", "put_oi_last",
    "call_volume", "put_volume",
    "call_gamma_avg", "put_gamma_avg", "call_iv_avg", "put_iv_avg",
    "spot_close", "samples",
)


class DownsamplerJob:
    """T0 -> T15-min buckets (idempotent upserts, recomputable from T0)."""

    def __init__(
        self,
        db: Database,
        *,
        now: Optional[Any] = None,
    ) -> None:
        self._db = db
        self._now = now or (lambda: dt.datetime.now(tz=dt.timezone.utc))

    def default_window(self) -> tuple[dt.datetime, dt.datetime]:
        """[now - 48h, now) — the raw retention horizon: whatever survives in
        T0 can always be (re)downsampled before raw drops."""
        until = self._now()
        return until - dt.timedelta(hours=RAW_HORIZON_HOURS), until

    async def bucket_rows(
        self, since: dt.datetime, until: dt.datetime
    ) -> list[dict[str, Any]]:
        rows = await self._db.fetch(DOWNSAMPLE_SQL, since, until)
        return _rows_to_dicts(rows)

    async def run(
        self,
        *,
        dry_run: bool = True,
        since: Optional[dt.datetime] = None,
        until: Optional[dt.datetime] = None,
    ) -> dict[str, Any]:
        started = time.time()
        if since is None or until is None:
            def_since, def_until = self.default_window()
            since = since or def_since
            until = until or def_until
        rows = await self.bucket_rows(since, until)
        report: dict[str, Any] = {
            "job": "downsampler",
            "mode": "dry-run (no writes)" if dry_run else "execute",
            "since": since.isoformat(),
            "until": until.isoformat(),
            "t1_rows_planned": len(rows),
            "cells": len({(r["ticker"], r["expiry"], r["strike"]) for r in rows}),
        }
        if dry_run:
            report["duration_s"] = round(time.time() - started, 2)
            return report
        report["t1_rows_written"] = await upsert_rows(
            self._db, "gamma_bucket_5m", rows, ("ticker", "expiry", "strike", "bucket")
        )
        report["duration_s"] = round(time.time() - started, 2)
        log.info("downsampler run done", extra={k: report[k] for k in ("mode", "t1_rows_planned")})
        return report


# ---------------------------------------------------------------------------
# T1 -> T2: hourly expiry rollups + per-strike EOD chains.
# ---------------------------------------------------------------------------
HOURLY_SQL = """
WITH scoped AS (
    SELECT DISTINCT ticker, expiry
    FROM gamma_bucket_5m
    WHERE bucket >= $1 AND bucket < $2
),
w AS (
    SELECT b.ticker, b.expiry, b.strike,
           to_timestamp(floor(extract(epoch FROM b.bucket) / 3600.0) * 3600) AS hour,
           b.call_oi_last, b.put_oi_last,
           b.call_gamma_avg, b.put_gamma_avg, b.spot_close,
           row_number() OVER cell_hour      AS rn_cell_last,
           row_number() OVER hour_first     AS rn_hour_first,
           row_number() OVER hour_last      AS rn_hour_last
    FROM gamma_bucket_5m b
    JOIN scoped s ON s.ticker = b.ticker AND s.expiry = b.expiry
    WINDOW cell_hour AS (PARTITION BY b.ticker, b.expiry, b.strike,
                         to_timestamp(floor(extract(epoch FROM b.bucket) / 3600.0) * 3600)
                         ORDER BY b.bucket DESC),
           hour_first AS (PARTITION BY b.ticker, b.expiry,
                          to_timestamp(floor(extract(epoch FROM b.bucket) / 3600.0) * 3600)
                          ORDER BY b.bucket ASC),
           hour_last AS (PARTITION BY b.ticker, b.expiry,
                         to_timestamp(floor(extract(epoch FROM b.bucket) / 3600.0) * 3600)
                         ORDER BY b.bucket DESC)
)
SELECT ticker, expiry, hour,
       sum(call_gamma_avg * call_oi_last * spot_close * spot_close)
           FILTER (WHERE rn_cell_last = 1) AS call_gex,
       sum(put_gamma_avg * put_oi_last * spot_close * spot_close)
           FILTER (WHERE rn_cell_last = 1) AS put_gex,
       max(spot_close) FILTER (WHERE rn_hour_first = 1) AS spot_open,
       max(spot_close) FILTER (WHERE rn_hour_last = 1)  AS spot_close
FROM w
GROUP BY ticker, expiry, hour
ORDER BY ticker, expiry, hour
"""

EOD_SQL = """
WITH scoped AS (
    SELECT DISTINCT ticker, expiry, strike
    FROM gamma_bucket_5m
    WHERE bucket >= $1 AND bucket < $2
),
w AS (
    SELECT b.ticker, b.expiry, b.strike,
           (b.bucket AT TIME ZONE 'UTC')::date AS day,
           b.call_oi_last, b.put_oi_last, b.call_volume, b.put_volume,
           b.call_gamma_avg, b.put_gamma_avg, b.spot_close,
           row_number() OVER day_last AS rn_last
    FROM gamma_bucket_5m b
    JOIN scoped s
      ON s.ticker = b.ticker AND s.expiry = b.expiry AND s.strike = b.strike
    WINDOW day_last AS (PARTITION BY b.ticker, b.expiry, b.strike,
                        (b.bucket AT TIME ZONE 'UTC')::date
                        ORDER BY b.bucket DESC)
)
SELECT ticker, expiry, strike, day,
       max(call_oi_last) FILTER (WHERE rn_last = 1) AS call_oi,
       max(put_oi_last)  FILTER (WHERE rn_last = 1) AS put_oi,
       sum(call_volume) AS call_volume,
       sum(put_volume)  AS put_volume,
       sum(call_gamma_avg * call_oi_last * spot_close * spot_close)
           FILTER (WHERE rn_last = 1) AS call_gex,
       sum(put_gamma_avg * put_oi_last * spot_close * spot_close)
           FILTER (WHERE rn_last = 1) AS put_gex,
       max(spot_close) FILTER (WHERE rn_last = 1) AS spot_close
FROM w
GROUP BY ticker, expiry, strike, day
ORDER BY ticker, expiry, strike, day
"""


class RollupsJob:
    """T1 -> T2 (hourly rollups + EOD chains), schema_version 1."""

    def __init__(
        self,
        db: Database,
        *,
        now: Optional[Any] = None,
        schema_version: int = ROLLUP_SCHEMA_VERSION,
    ) -> None:
        self._db = db
        self._now = now or (lambda: dt.datetime.now(tz=dt.timezone.utc))
        self._schema_version = schema_version

    def hourly_window(self) -> tuple[dt.datetime, dt.datetime]:
        """Completed hours of the last day: [floor_hour(now)-24h, floor_hour(now))."""
        until = self._now().replace(minute=0, second=0, microsecond=0)
        return until - dt.timedelta(hours=24), until

    def eod_window(self) -> tuple[dt.datetime, dt.datetime]:
        """Yesterday (UTC) — the day's buckets are all in the past."""
        today = self._now().astimezone(dt.timezone.utc).date()
        start = dt.datetime.combine(today - dt.timedelta(days=1), dt.time(), tzinfo=dt.timezone.utc)
        return start, start + dt.timedelta(days=1)

    async def hourly_rows(
        self, since: dt.datetime, until: dt.datetime
    ) -> list[dict[str, Any]]:
        raw = await self._db.fetch(HOURLY_SQL, since, until)
        rows = []
        for r in raw:
            d = {k: _aware(v) for k, v in dict(r).items()}
            d["net_gex"] = net(d.get("call_gex"), d.get("put_gex"))
            d["schema_version"] = self._schema_version
            rows.append(d)
        return rows

    async def eod_rows(
        self, since: dt.datetime, until: dt.datetime
    ) -> list[dict[str, Any]]:
        raw = await self._db.fetch(EOD_SQL, since, until)
        rows = []
        for r in raw:
            d = {k: _aware(v) for k, v in dict(r).items()}
            d["net_gex"] = net(d.get("call_gex"), d.get("put_gex"))
            d["schema_version"] = self._schema_version
            rows.append(d)
        return rows

    async def run(
        self,
        *,
        dry_run: bool = True,
        hourly: bool = True,
        eod: bool = True,
        hourly_window: Optional[tuple[dt.datetime, dt.datetime]] = None,
        eod_window: Optional[tuple[dt.datetime, dt.datetime]] = None,
    ) -> dict[str, Any]:
        started = time.time()
        report: dict[str, Any] = {
            "job": "rollups",
            "mode": "dry-run (no writes)" if dry_run else "execute",
            "schema_version": self._schema_version,
        }
        if hourly:
            since, until = hourly_window or self.hourly_window()
            rows = await self.hourly_rows(since, until)
            report["hourly"] = {
                "since": since.isoformat(),
                "until": until.isoformat(),
                "rows_planned": len(rows),
            }
            if not dry_run:
                report["hourly"]["rows_written"] = await upsert_rows(
                    self._db,
                    "expiry_rollup_hourly",
                    rows,
                    ("ticker", "expiry", "hour"),
                )
        if eod:
            since, until = eod_window or self.eod_window()
            rows = await self.eod_rows(since, until)
            report["eod"] = {
                "since": since.isoformat(),
                "until": until.isoformat(),
                "rows_planned": len(rows),
            }
            if not dry_run:
                report["eod"]["rows_written"] = await upsert_rows(
                    self._db,
                    "strike_eod",
                    rows,
                    ("ticker", "expiry", "strike", "day"),
                )
        report["duration_s"] = round(time.time() - started, 2)
        log.info("rollups run done", extra={"mode": report["mode"]})
        return report


# --------------------------------------------------------------------------- CLI
def _parse_ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="T0->T1 downsampler + T1->T2 rollups")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="plan only (default)")
    mode.add_argument("--execute", action="store_true", help="write T1/T2 rows")
    ap.add_argument("--since", default="", help="window start (ISO)")
    ap.add_argument("--until", default="", help="window end (ISO)")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--downsample-only", action="store_true")
    scope.add_argument("--rollup-only", action="store_true")
    ap.add_argument("--report", default="", help="write the report JSON here")
    return ap.parse_args(argv)


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        raise ConfigError("GAMMASUMMIT_DATABASE_URL is required")
    db = Database(settings.database_url)
    await db.connect()
    try:
        report: dict[str, Any] = {}
        since = _parse_ts(args.since) if args.since else None
        until = _parse_ts(args.until) if args.until else None
        dry_run = not args.execute
        if not args.rollup_only:
            report["downsampler"] = await DownsamplerJob(db).run(
                dry_run=dry_run, since=since, until=until
            )
        if not args.downsample_only:
            job = RollupsJob(db)
            hw = (since, until) if (since and until) else None
            report["rollups"] = await job.run(
                dry_run=dry_run,
                hourly_window=hw,
                eod_window=hw,
            )
        return report
    finally:
        await db.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)
    report = asyncio.run(_async_main(args))
    text = json.dumps(report, indent=1, default=str)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
