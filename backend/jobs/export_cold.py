"""T1/T2 cold export + manifest-verified retention (tree: jobs/export_cold.py)
— card E2.3; docs/ops/data-tiering.md is law, docs/architecture/topology-linkage.md
holds the rclone/R2 spec.

T1 (`gamma_bucket_5m`, fixed 30d) and T2 (`expiry_rollup_hourly`, `strike_eod`,
owner-locked 90d–365d) leave Postgres ONLY through the export-first sequence —
the same law as jobs/retention.py owns for raw T0:

  plan -> export (Parquet to the T3 cold root on X10) -> manifest
       -> verify (re-read file: row count + sha256)
       -> rclone copy (optional B2/R2 offsite leg, size-verified)
       -> delete (verified segments only)

A delete step that finds any unverified segment refuses to run (hard rule:
retention never deletes un-exported data). When the rclone leg is configured
(GAMMASUMMIT_T3_RCLONE_REMOTE), the offsite copy must verify too before the
segment becomes deletable (3-2-1, docs/ops/operations.md).

Deletes run as the table owner (gammasummit_jobs holds no DELETE on tier
tables by design, 0004) — deploy wiring and jobs/scheduler.py point this job
at the owner DSN.

Dry-run is the DEFAULT (hard rule): zero writes — no files, no DB rows.

CLI:
  python -m backend.jobs.export_cold --dry-run                 # plan only
  python -m backend.jobs.export_cold --execute                 # export + verify
  python -m backend.jobs.export_cold --execute --delete        # + drop verified

Cold layout (same hive shape as T0, docs/ops/migration-from-signalforge.md):
  <t3_root>/<table>/ticker=<T>/date=<YYYY-MM-DD>/part-*.parquet
  rclone -> <remote>:<bucket>/t3/<table>/ticker=<T>/date=<YYYY-MM-DD>/part-*.parquet
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from typing import Any, Callable, Optional, Sequence

from backend.core.config import get_settings
from backend.core.db import Database
from backend.core.errors import ConfigError
from backend.core.logging import configure_logging, get_logger

log = get_logger(__name__)

# T1 retention is fixed at 30d (law, not configurable). T2 window bounds come
# from the law range 90d–1yr.
RETENTION_T1_DAYS = 30
MIN_T2_RETENTION_DAYS = 90
MAX_T2_RETENTION_DAYS = 365
EXPORT_FIRST_ORDER = ("plan", "export", "manifest", "verify", "rclone_copy", "delete")

# (table, tier, time column, day expression). Table/column names are code
# constants (never user input) — same law as core.db.upsert_sql.
TIER_SEGMENTS: tuple[tuple[str, str, str, str], ...] = (
    ("gamma_bucket_5m", "T1", "bucket", "(bucket AT TIME ZONE 'UTC')::date"),
    ("expiry_rollup_hourly", "T2", "hour", "(hour AT TIME ZONE 'UTC')::date"),
    ("strike_eod", "T2", "day", "day"),
)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _day_window(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    if isinstance(day, dt.datetime):
        day = day.date()
    start = dt.datetime.combine(day, dt.time(), tzinfo=dt.timezone.utc)
    return start, start + dt.timedelta(days=1)


def _aware(value: Any) -> Any:
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


class ExportColdJob:
    """T1/T2 -> T3 Parquet cold export + manifest-verified retention."""

    def __init__(
        self,
        db: Database,
        *,
        t3_root: str,
        t2_retention_days: int = MAX_T2_RETENTION_DAYS,
        rclone_remote: str = "",
        rclone_bucket: str = "gammasummit-cold",
        runner: Optional[Callable[..., Any]] = None,
        now: Optional[Callable[[], dt.datetime]] = None,
    ) -> None:
        if not (MIN_T2_RETENTION_DAYS <= t2_retention_days <= MAX_T2_RETENTION_DAYS):
            raise ConfigError(
                f"T2 retention must stay {MIN_T2_RETENTION_DAYS}-"
                f"{MAX_T2_RETENTION_DAYS}d (owner-locked, docs/ops/data-tiering.md)"
            )
        if not t3_root:
            raise ConfigError("T3 root is empty")
        self._db = db
        self._t3_root = t3_root.rstrip("/")
        self._t2_days = t2_retention_days
        self._rclone_remote = rclone_remote.strip()
        self._rclone_bucket = rclone_bucket
        self._runner = runner or subprocess.run
        self._now = now or (lambda: dt.datetime.now(tz=dt.timezone.utc))
        self._r2_manifests: list[dict[str, Any]] = []

    # ------------------------------------------------------------- cutoffs
    def cutoffs(self) -> dict[str, dt.datetime]:
        now = self._now()
        return {
            "T1": now - dt.timedelta(days=RETENTION_T1_DAYS),
            "T2": now - dt.timedelta(days=self._t2_days),
        }

    # ---------------------------------------------------------------- plan
    async def plan(self) -> list[dict[str, Any]]:
        """Segments (table × ticker × UTC day) with at least one row past the
        tier's retention cutoff — the unit of export/verification/deletion."""
        cutoffs = self.cutoffs()
        segments: list[dict[str, Any]] = []
        for table, tier, tcol, day_expr in TIER_SEGMENTS:
            rows = await self._db.fetch(
                f"SELECT ticker, {day_expr} AS day, count(*) AS rows, "
                f"min({tcol}) AS min_ts, max({tcol}) AS max_ts "
                f"FROM {table} WHERE {tcol} < $1 "
                f"GROUP BY ticker, {day_expr} ORDER BY ticker, day",
                cutoffs[tier],
            )
            for r in rows:
                segments.append(
                    {
                        "table": table,
                        "tier": tier,
                        "tcol": tcol,
                        "ticker": r["ticker"],
                        "day": r["day"],
                        "rows": int(r["rows"]),
                        "min_ts": r["min_ts"],
                        "max_ts": r["max_ts"],
                    }
                )
        return segments

    def intended_paths(self, segments: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        stamp = self._now().strftime("%Y%m%dT%H%M%SZ")
        out = []
        for seg in segments:
            rel = (
                f"{seg['table']}/ticker={seg['ticker']}/date={seg['day']}"
                f"/part-{stamp}.parquet"
            )
            out.append({**seg, "file_path": rel, "abs_path": f"{self._t3_root}/{rel}"})
        return out

    # --------------------------------------------------------------- export
    async def export(self, segments: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """One Parquet per segment (all columns — full-fidelity cold copy)."""
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        cutoffs = self.cutoffs()
        manifests: list[dict[str, Any]] = []
        for seg in self.intended_paths(segments):
            start, end = _day_window(seg["day"])
            cutoff = cutoffs[seg["tier"]]
            rows = await self._db.fetch(
                f"SELECT * FROM {seg['table']} WHERE ticker = $1 "
                f"AND {seg['tcol']} >= $2 AND {seg['tcol']} < $3 "
                f"AND {seg['tcol']} < $4 ORDER BY {seg['tcol']}",
                seg["ticker"], start, end, cutoff,
            )
            records = [{k: _aware(v) for k, v in dict(r).items()} for r in rows]
            os.makedirs(os.path.dirname(seg["abs_path"]), exist_ok=True)
            pq.write_table(pa.Table.from_pylist(records), seg["abs_path"], compression="zstd")
            manifests.append(
                {
                    "table": seg["table"],
                    "tier": seg["tier"],
                    "ticker": seg["ticker"],
                    "day": seg["day"],
                    "min_ts": seg["min_ts"],
                    "max_ts": seg["max_ts"],
                    "file_path": seg["file_path"],
                    "abs_path": seg["abs_path"],
                    "exported_at": self._now(),
                    "target": "x10",
                    "sha256": _sha256_file(seg["abs_path"]),
                    "byte_size": os.path.getsize(seg["abs_path"]),
                    "row_count": len(records),
                }
            )
        return manifests

    async def record_manifests(
        self, manifests: Sequence[dict[str, Any]], target: str = "x10"
    ) -> int:
        for m in manifests:
            await self._db.execute(
                "INSERT INTO export_manifest "
                "(file_path, exported_at, tier, target, sha256, byte_size, row_count, verified_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, NULL)",
                m["file_path"], m["exported_at"], m["tier"], target,
                m["sha256"], m["byte_size"], m["row_count"],
            )
        return len(manifests)

    # --------------------------------------------------------------- verify
    async def verify(self, manifests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Re-read every exported file: row count AND sha256 must match the
        manifest. A corrupt/unreadable file fails verification loudly
        (verified=False) — it never crashes and never unlocks a delete."""
        import pyarrow.parquet as pq  # noqa: PLC0415

        for m in manifests:
            try:
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
                    "WHERE file_path = $1 AND exported_at = $2 AND target = 'x10'",
                    m["file_path"], m["exported_at"],
                )
        return list(manifests)

    # --------------------------------------------------------- rclone copy
    def rclone_enabled(self) -> bool:
        return bool(self._rclone_remote)

    def _remote_path(self, file_path: str) -> str:
        return f"{self._rclone_remote}:{self._rclone_bucket}/t3/{file_path}"

    def rclone_copy(self, manifests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Offsite leg (topology-linkage.md step 5): rclone copyto the verified
        local Parquet, then confirm the remote object's SIZE matches. The
        remote manifest row records the local sha256; verification is the size
        round-trip (R2/B2 serve no sha256 via lsjson). Dry-run callers never
        reach this — run() gates it behind execute."""
        for m in manifests:
            remote = self._remote_path(m["file_path"])
            if not self.rclone_enabled():
                m["r2"] = "skipped (no rclone remote configured)"
                continue
            try:
                self._runner(
                    ["rclone", "copyto", m["abs_path"], remote, "--transfers", "4"],
                    capture_output=True, text=True, check=True,
                )
                out = self._runner(
                    ["rclone", "lsjson", remote],
                    capture_output=True, text=True, check=True,
                )
                listed = json.loads(out.stdout or "[]")
                remote_size = int(listed[0]["Size"]) if listed else -1
                m["r2_verified"] = remote_size == m["byte_size"]
                m["r2_remote"] = remote
                if not m["r2_verified"]:
                    m["r2_error"] = f"remote size {remote_size} != local {m['byte_size']}"
            except Exception as exc:  # noqa: BLE001 — report, never crash the run
                m["r2_verified"] = False
                m["r2_error"] = repr(exc)
            if m.get("r2_verified"):
                # The offsite copy is its own export event: it needs its own
                # exported_at (export_manifest PK = (file_path, exported_at)),
                # and a copy can never predate the local export it came from.
                r2_ts = max(
                    self._now(), m["exported_at"] + dt.timedelta(microseconds=1)
                )
                self._r2_manifests.append({**m, "exported_at": r2_ts, "target": "r2"})
        return list(manifests)

    async def record_r2_manifests(self) -> int:
        return await self.record_manifests(self._r2_manifests, target="r2")

    # ---------------------------------------------------------------- delete
    def deletable(self, manifests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        """Segments proven safe to drop: local export verified, and the offsite
        copy verified too when the rclone leg is configured."""
        ok = []
        for m in manifests:
            if not m.get("verified"):
                continue
            if self.rclone_enabled() and not m.get("r2_verified"):
                continue
            ok.append(m)
        return ok

    async def delete(self, manifests: Sequence[dict[str, Any]]) -> dict[str, int]:
        deletable_ids = {id(m) for m in self.deletable(manifests)}
        unverified = [m for m in manifests if id(m) not in deletable_ids]
        if unverified:
            raise ConfigError(
                f"refusing to delete: {len(unverified)} segment(s) lack a verified export"
            )
        cutoffs = self.cutoffs()
        deleted: dict[str, int] = {}
        for m in manifests:
            start, end = _day_window(m["day"])
            cutoff = cutoffs[m["tier"]]
            tcol = next(t for tbl, _tier, t, _d in TIER_SEGMENTS if tbl == m["table"])
            status = await self._db.execute(
                f"DELETE FROM {m['table']} WHERE ticker = $1 "
                f"AND {tcol} >= $2 AND {tcol} < $3 AND {tcol} < $4",
                m["ticker"], start, end, cutoff,
            )
            deleted[m["table"]] = deleted.get(m["table"], 0) + int(status.split()[-1])
        return deleted

    # ------------------------------------------------------------------- run
    async def run(self, *, dry_run: bool = True, delete: bool = False) -> dict[str, Any]:
        started = time.time()
        self._r2_manifests = []
        cutoffs = self.cutoffs()
        segments = await self.plan()
        report: dict[str, Any] = {
            "job": "export_cold",
            "mode": "dry-run (no writes)" if dry_run else "execute",
            "cutoffs": {k: v.isoformat() for k, v in cutoffs.items()},
            "retention_days": {"T1": RETENTION_T1_DAYS, "T2": self._t2_days},
            "export_first_order": list(EXPORT_FIRST_ORDER),
            "guard": "delete requires a verified export manifest per segment"
                     " (+ verified rclone copy when configured)",
            "rclone": "enabled: " + self._rclone_remote if self.rclone_enabled()
                      else "skipped (no rclone remote configured)",
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
        report["verify_failures"] = [m["file_path"] for m in manifests if not m["verified"]]
        self.rclone_copy(manifests)
        report["r2_verified_files"] = sum(1 for m in manifests if m.get("r2_verified"))
        report["r2_failures"] = [
            {"file": m["file_path"], "error": m.get("r2_error", m.get("r2"))}
            for m in manifests
            if self.rclone_enabled() and not m.get("r2_verified")
        ]
        report["r2_manifests_recorded"] = await self.record_r2_manifests()
        if delete:
            report["deleted_rows"] = await self.delete(manifests)
        else:
            report["deleted_rows"] = "skipped (pass --delete to drop verified rows)"
        report["duration_s"] = round(time.time() - started, 2)
        log.info("export_cold run done", extra={"mode": report["mode"], "segments": len(segments)})
        return report


# ----------------------------------------------------------------- CLI
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="T1/T2 cold export (export-first)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="plan only (default)")
    mode.add_argument("--execute", action="store_true", help="export + verify + manifest")
    ap.add_argument("--delete", action="store_true", help="also delete verified rows")
    ap.add_argument("--t2-days", type=int, default=0, help="90-365 (default: settings)")
    ap.add_argument("--t3-root", default="", help="override the T3 cold root")
    ap.add_argument(
        "--as-of", default="",
        help="verification/backfill hook: evaluate retention windows at this "
             "instant instead of wall clock (ISO)",
    )
    ap.add_argument("--report", default="", help="write the report JSON here")
    return ap.parse_args(argv)


def _constant_clock(as_of: dt.datetime) -> Callable[[], dt.datetime]:
    """--as-of hook: a fixed retention clock (verification/backfill runs)."""
    def now() -> dt.datetime:
        return as_of
    return now


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        raise ConfigError("GAMMASUMMIT_DATABASE_URL is required")
    now_fn: Optional[Callable[[], dt.datetime]] = None
    if args.as_of:
        now_fn = _constant_clock(
            dt.datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        )

    db = Database(settings.database_url)
    job = ExportColdJob(
        db,
        t3_root=args.t3_root or settings.t3_root,
        t2_retention_days=args.t2_days or settings.retention_t2_days,
        rclone_remote=settings.t3_rclone_remote,
        rclone_bucket=settings.t3_rclone_bucket,
        now=now_fn,
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
