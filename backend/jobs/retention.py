"""T0 raw retention job (tree: jobs/retention.py) — export-first, manifest-
verified (card E2.2; docs/ops/data-tiering.md is law).

Raw T0 retention is owner-locked 24–48h: rows older than the cutoff leave
Postgres, but ONLY through the export-first sequence —

  plan → export (Parquet to the T3 cold root) → manifest (export_manifest row)
  → verify (re-read file: row count + sha256) → delete (verified segments only)

A delete step that finds any unverified segment refuses to run (hard rule:
retention never deletes un-exported data; NFR "Retention safety"). Nothing
here touches partition DDL — pg_partman retention stays NULL (0003) and the
P2 single scheduler owns run_maintenance (E2.3).

Dry-run is the DEFAULT (hard rule): it prints the full plan — segments, row
counts, intended file paths, and the export-first ordering — and performs ZERO
writes (no files, no DB rows). `--execute` exports + verifies + records
manifests; `--execute --delete` additionally removes the verified rows.

Deletes run as the table owner (the gammasummit_jobs role holds no DELETE on
T0 by design, 0004) — deploy wiring points this job at the owner DSN.

CLI:
  python -m backend.jobs.retention --dry-run                # plan only
  python -m backend.jobs.retention --execute                # export + verify
  python -m backend.jobs.retention --execute --delete       # + drop verified

Cold layout (docs/ops/migration-from-signalforge.md X10 layout):
  <t3_root>/<gamma|spot|flow|darkpool>/ticker=<T>/date=<YYYY-MM-DD>/part-*.parquet
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import sys
import time
from typing import Any, Callable, Optional, Sequence

from backend.core.config import get_settings
from backend.core.db import Database
from backend.core.errors import ConfigError
from backend.core.logging import configure_logging, get_logger

log = get_logger(__name__)

# (table, cold-store subdir). Table names are code constants (never user
# input) — same law as core.db.upsert_sql.
T0_SEGMENTS: tuple[tuple[str, str], ...] = (
    ("gamma_snapshot", "gamma"),
    ("spot_tick", "spot"),
    ("flow_print", "flow"),
    ("darkpool_print", "darkpool"),
)
TIER = "T0"
TARGET = "x10"  # external disk primary (B2/R2 copy is E2.3's export job)
MIN_RETENTION_HOURS = 24
MAX_RETENTION_HOURS = 48
EXPORT_FIRST_ORDER = ("plan", "export", "manifest", "verify", "delete")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _day_window(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day, dt.time(), tzinfo=dt.timezone.utc)
    return start, start + dt.timedelta(days=1)


class RetentionJob:
    def __init__(
        self,
        db: Database,
        *,
        t3_root: str,
        retention_hours: int = 48,
        now: Optional[Callable[[], dt.datetime]] = None,
    ) -> None:
        if not (MIN_RETENTION_HOURS <= retention_hours <= MAX_RETENTION_HOURS):
            raise ConfigError(
                f"raw retention must stay {MIN_RETENTION_HOURS}-{MAX_RETENTION_HOURS}h "
                "(owner-locked, docs/ops/data-tiering.md)"
            )
        if not t3_root:
            raise ConfigError("T3 root is empty")
        self._db = db
        self._t3_root = t3_root.rstrip("/")
        self._retention_hours = retention_hours
        self._now = now or (lambda: dt.datetime.now(tz=dt.timezone.utc))

    @property
    def cutoff(self) -> dt.datetime:
        return self._now() - dt.timedelta(hours=self._retention_hours)

    # ---------------------------------------------------------------- plan
    async def plan(self) -> list[dict[str, Any]]:
        """Segments (table × ticker × UTC day) with at least one row older
        than the cutoff — the unit of export, verification and deletion."""
        cutoff = self.cutoff
        segments: list[dict[str, Any]] = []
        for table, sub in T0_SEGMENTS:
            rows = await self._db.fetch(
                f"SELECT ticker, (ts AT TIME ZONE 'UTC')::date AS day, "
                f"count(*) AS rows, min(ts) AS min_ts, max(ts) AS max_ts "
                f"FROM {table} WHERE ts < $1 "
                f"GROUP BY ticker, (ts AT TIME ZONE 'UTC')::date ORDER BY ticker, day",
                cutoff,
            )
            for r in rows:
                segments.append(
                    {
                        "table": table,
                        "sub": sub,
                        "ticker": r["ticker"],
                        "day": r["day"],
                        "rows": int(r["rows"]),
                        "min_ts": r["min_ts"],
                        "max_ts": r["max_ts"],
                    }
                )
        return segments

    def intended_paths(self, segments: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Dry-run view: where each segment WOULD land, without writing."""
        stamp = self._now().strftime("%Y%m%dT%H%M%SZ")
        out = []
        for seg in segments:
            rel = (
                f"{seg['sub']}/ticker={seg['ticker']}/date={seg['day']}"
                f"/part-{stamp}.parquet"
            )
            out.append({**seg, "file_path": rel, "abs_path": f"{self._t3_root}/{rel}"})
        return out

    # --------------------------------------------------------------- export
    async def export(self, segments: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Write one Parquet per segment and hash it. Import is lazy so the
        dry-run path stays dependency-light."""
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        cutoff = self.cutoff
        manifests: list[dict[str, Any]] = []
        for seg in self.intended_paths(segments):
            start, end = _day_window(seg["day"])
            rows = await self._db.fetch(
                f"SELECT * FROM {seg['table']} WHERE ticker = $1 AND ts >= $2 AND ts < $3 "
                f"AND ts < $4 ORDER BY ts",
                seg["ticker"],
                start,
                end,
                cutoff,
            )
            records = [dict(r) for r in rows]
            os.makedirs(os.path.dirname(seg["abs_path"]), exist_ok=True)
            table = pa.Table.from_pylist(records)
            pq.write_table(table, seg["abs_path"], compression="zstd")
            manifests.append(
                {
                    "table": seg["table"],
                    "ticker": seg["ticker"],
                    "day": seg["day"],
                    "min_ts": seg["min_ts"],
                    "max_ts": seg["max_ts"],
                    "file_path": seg["file_path"],
                    "abs_path": seg["abs_path"],
                    "exported_at": self._now(),
                    "tier": TIER,
                    "target": TARGET,
                    "sha256": _sha256_file(seg["abs_path"]),
                    "byte_size": os.path.getsize(seg["abs_path"]),
                    "row_count": len(records),
                }
            )
        return manifests

    async def record_manifests(self, manifests: Sequence[dict[str, Any]]) -> int:
        """export_manifest rows (verified_at NULL — verify() attests them)."""
        for m in manifests:
            await self._db.execute(
                "INSERT INTO export_manifest "
                "(file_path, exported_at, tier, target, sha256, byte_size, row_count, verified_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, NULL)",
                m["file_path"],
                m["exported_at"],
                m["tier"],
                m["target"],
                m["sha256"],
                m["byte_size"],
                m["row_count"],
            )
        return len(manifests)

    # --------------------------------------------------------------- verify
    async def verify(self, manifests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Re-read every exported file: row count AND sha256 must match the
        manifest before the segment becomes deletable. A corrupt/unreadable
        file fails verification loudly (verified=False) — it never crashes the
        job and it never unlocks a delete."""
        import pyarrow.parquet as pq  # noqa: PLC0415

        for m in manifests:
            try:
                # ParquetFile reads the FILE: pq.read_table would treat the
                # hive-partitioned path (ticker=/date=) as a dataset and try to
                # merge the path columns into the schema.
                on_disk_rows = pq.ParquetFile(m["abs_path"]).metadata.num_rows
                sha = _sha256_file(m["abs_path"])
            except Exception as exc:  # noqa: BLE001 — verify must report, not crash
                m["verified"] = False
                m["verify_error"] = repr(exc)
                continue
            m["verified"] = bool(on_disk_rows == m["row_count"] and sha == m["sha256"])
            m["verified_rows_on_disk"] = on_disk_rows
            if m["verified"]:
                await self._db.execute(
                    "UPDATE export_manifest SET verified_at = now() "
                    "WHERE file_path = $1 AND exported_at = $2",
                    m["file_path"],
                    m["exported_at"],
                )
        return list(manifests)

    # ---------------------------------------------------------------- delete
    async def delete(self, manifests: Sequence[dict[str, Any]]) -> dict[str, int]:
        """Delete exported+verified rows only. Refuses outright if any manifest
        is unverified (never delete un-exported data)."""
        unverified = [m for m in manifests if not m.get("verified")]
        if unverified:
            raise ConfigError(
                f"refusing to delete: {len(unverified)} segment(s) lack a verified export"
            )
        cutoff = self.cutoff
        deleted: dict[str, int] = {}
        for m in manifests:
            start, end = _day_window(m["day"])
            status = await self._db.execute(
                f"DELETE FROM {m['table']} WHERE ticker = $1 AND ts >= $2 AND ts < $3 AND ts < $4",
                m["ticker"],
                start,
                end,
                cutoff,
            )
            deleted[m["table"]] = deleted.get(m["table"], 0) + int(status.split()[-1])
        return deleted

    # ------------------------------------------------------------------- run
    async def run(self, *, dry_run: bool = True, delete: bool = False) -> dict[str, Any]:
        started = time.time()
        cutoff = self.cutoff
        segments = await self.plan()
        report: dict[str, Any] = {
            "mode": "dry-run (no writes)" if dry_run else "execute",
            "cutoff": cutoff.isoformat(),
            "retention_hours": self._retention_hours,
            "export_first_order": list(EXPORT_FIRST_ORDER),
            "guard": "delete requires a verified export manifest per segment",
            "segments": len(segments),
            "rows_at_risk": sum(s["rows"] for s in segments),
            "per_table_rows": {},
            "planned_files": self.intended_paths(segments) if dry_run else [],
        }
        for s in segments:
            report["per_table_rows"][s["table"]] = (
                report["per_table_rows"].get(s["table"], 0) + s["rows"]
            )
        if dry_run:
            report["duration_s"] = round(time.time() - started, 2)
            return report

        manifests = await self.export(segments)
        report["exported_files"] = len(manifests)
        report["exported_bytes"] = sum(m["byte_size"] for m in manifests)
        report["manifests_recorded"] = await self.record_manifests(manifests)
        manifests = await self.verify(manifests)
        report["verified_files"] = sum(1 for m in manifests if m["verified"])
        report["verify_failures"] = [
            m["file_path"] for m in manifests if not m["verified"]
        ]
        if delete:
            report["deleted_rows"] = await self.delete(manifests)
        else:
            report["deleted_rows"] = "skipped (pass --delete to drop verified rows)"
        report["duration_s"] = round(time.time() - started, 2)
        log.info("retention run done", extra={k: report[k] for k in ("mode", "segments")})
        return report


# ----------------------------------------------------------------- CLI
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="T0 raw retention (export-first)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="plan only (default)")
    mode.add_argument("--execute", action="store_true", help="export + verify + manifest")
    ap.add_argument("--delete", action="store_true", help="also delete verified rows")
    ap.add_argument("--retention-hours", type=int, default=0, help="24-48 (default: settings)")
    ap.add_argument("--t3-root", default="", help="override the T3 cold root")
    ap.add_argument("--report", default="", help="write the report JSON here")
    return ap.parse_args(argv)


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        raise ConfigError("GAMMASUMMIT_DATABASE_URL is required")
    db = Database(settings.database_url)
    job = RetentionJob(
        db,
        t3_root=args.t3_root or settings.t3_root,
        retention_hours=args.retention_hours or settings.retention_raw_hours,
    )
    await db.connect()
    try:
        return await job.run(dry_run=not args.execute, delete=args.delete and args.execute)
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
