"""THE single scheduler (tree: jobs/scheduler.py) — card E2.3, ADR 0007.

Single-scheduler law (hard rule, docs/build/README.md): pg_cron XOR backend
timers — NEVER both. GammaSummit runs **backend timers**: this daemon is the
only thing that schedules tier work. pg_cron is deliberately NOT installed
(pgTAP guard: db/tests/0004_single_scheduler.sql) because every job here is
Python (Parquet export, rclone, manifest verification) — a pg_cron SQL trigger
path would be a second scheduler in practice.

What it owns (the whole cadence, nothing else schedules anything):

  every 5 min   downsampler     T0 -> T15-min buckets (jobs/rollups.py)
  hourly        rollups         T1 -> T2 hourly expiry rollups (jobs/rollups.py)
  daily 22:30Z  rollups EOD     T1 -> T2 per-strike EOD chains
  daily 22:45Z  retention       T0 24-48h export-first drop (jobs/retention.py)
  daily 23:00Z  export_cold     T1/T2 -> T3 Parquet + rclone + drop
                                (jobs/export_cold.py)
  hourly        run_maintenance pg_partman partition creation (owner DSN —
                                partition DDL never runs as an app role)

One instance only: a Postgres advisory lock (session-scoped, held on a
dedicated connection) — a second scheduler exits without running anything.

Runs report into audit_log (actor `jobs:scheduler`) so freshness alarms and
humans share one truth (docs/ops/operations.md "Retention & export safety").

CLI:
  python -m backend.jobs.scheduler --dry-run        # full pass, zero writes
  python -m backend.jobs.scheduler --dry-run --once # same, exit after one tick
  python -m backend.jobs.scheduler --execute --once # apply (incl. verified drops)
  python -m backend.jobs.scheduler --execute --loop # daemon (systemd unit)
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time
from typing import Any, Awaitable, Callable, Optional, Sequence

from backend.core.config import get_settings
from backend.core.db import Database
from backend.core.errors import ConfigError
from backend.core.logging import configure_logging, get_logger

log = get_logger(__name__)

# Arbitrary but fixed key — one lock per database for the whole scheduler.
SCHEDULER_LOCK_KEY = 772_331_220_905
AUDIT_ACTOR = "jobs:scheduler"
TickFn = Callable[[bool], Awaitable[dict[str, Any]]]


class Scheduled:
    """One cadence entry. `every_s` = interval, `at_utc` = daily HH:MM (UTC)."""

    def __init__(
        self,
        name: str,
        fn: TickFn,
        *,
        every_s: Optional[int] = None,
        at_utc: Optional[str] = None,
    ) -> None:
        if (every_s is None) == (at_utc is None):
            raise ConfigError(f"schedule {name}: exactly one of every_s/at_utc")
        self.name = name
        self.fn = fn
        self.every_s = every_s
        self.at_utc = at_utc
        self.next_due: Optional[dt.datetime] = None  # run on the first tick

    def due(self, now: dt.datetime) -> bool:
        return self.next_due is None or now >= self.next_due

    def advance(self, now: dt.datetime) -> None:
        if self.every_s is not None:
            self.next_due = now + dt.timedelta(seconds=self.every_s)
            return
        assert self.at_utc is not None  # constructor guarantees exactly one mode
        hh, mm = (int(x) for x in self.at_utc.split(":"))
        candidate = now.astimezone(dt.timezone.utc).replace(
            hour=hh, minute=mm, second=0, microsecond=0
        )
        self.next_due = candidate if candidate > now else candidate + dt.timedelta(days=1)


class Scheduler:
    def __init__(
        self,
        db: Database,
        schedules: Sequence[Scheduled],
        *,
        owner_db: Optional[Database] = None,
        now: Optional[Callable[[], dt.datetime]] = None,
    ) -> None:
        self._db = db
        self._owner_db = owner_db
        self._schedules = list(schedules)
        self._now = now or (lambda: dt.datetime.now(tz=dt.timezone.utc))

    async def _audit(self, target: str, detail: dict[str, Any]) -> None:
        await self._db.execute(
            "INSERT INTO audit_log (actor, ts, action, target, detail) "
            "VALUES ($1, $2, $3, $4, $5)",
            AUDIT_ACTOR, self._now(), "job.run", target, json.dumps(detail, default=str),
        )

    async def _partman_maintenance(self, execute: bool) -> dict[str, Any]:
        """pg_partman partition creation — the ONLY partition DDL path (0003).
        Runs as the table owner via GAMMASUMMIT_DB_OWNER_URL; app roles never
        create/drop partitions (0004)."""
        if self._owner_db is None:
            return {"skipped": "no GAMMASUMMIT_DB_OWNER_URL for partition DDL"}
        if not execute:
            return {"planned": "run_maintenance() (dry-run: not called)"}
        schema = await self._owner_db.fetchval(
            "SELECT n.nspname FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'pg_partman'"
        )
        if not schema:
            raise ConfigError("pg_partman extension missing — 0003 requires it")
        await self._owner_db.execute(f"SELECT {schema}.run_maintenance()")
        return {"run_maintenance": "called", "schema": schema}

    def build(self) -> None:
        """Attach the fixed tier cadence (see module docstring)."""
        self._schedules = [
            Scheduled("downsampler", self._downsampler, every_s=300),
            Scheduled("rollups_hourly", self._rollups_hourly, every_s=3600),
            Scheduled("rollups_eod", self._rollups_eod, at_utc="22:30"),
            Scheduled("retention_t0", self._retention_t0, at_utc="22:45"),
            Scheduled("export_cold", self._export_cold, at_utc="23:00"),
            Scheduled("partman_maintenance", self._partman_maintenance, every_s=3600),
        ]

    # ------------------------------------------------------- tier job wiring
    async def _downsampler(self, execute: bool) -> dict[str, Any]:
        from backend.jobs.rollups import DownsamplerJob  # noqa: PLC0415 — wiring
        return await DownsamplerJob(self._db).run(dry_run=not execute)

    async def _rollups_hourly(self, execute: bool) -> dict[str, Any]:
        from backend.jobs.rollups import RollupsJob  # noqa: PLC0415
        return await RollupsJob(self._db).run(dry_run=not execute, hourly=True, eod=False)

    async def _rollups_eod(self, execute: bool) -> dict[str, Any]:
        from backend.jobs.rollups import RollupsJob  # noqa: PLC0415
        return await RollupsJob(self._db).run(dry_run=not execute, hourly=False, eod=True)

    async def _retention_t0(self, execute: bool) -> dict[str, Any]:
        from backend.jobs.retention import RetentionJob  # noqa: PLC0415
        settings = get_settings()
        # Deletes run as the table owner (E2.2 docstring, 0004): the owner DSN
        # is the job's connection when configured.
        db = self._owner_db or self._db
        job = RetentionJob(db, t3_root=settings.t3_root,
                           retention_hours=settings.retention_raw_hours)
        return await job.run(dry_run=not execute, delete=execute)

    async def _export_cold(self, execute: bool) -> dict[str, Any]:
        from backend.jobs.export_cold import ExportColdJob  # noqa: PLC0415
        settings = get_settings()
        db = self._owner_db or self._db
        job = ExportColdJob(
            db,
            t3_root=settings.t3_root,
            t2_retention_days=settings.retention_t2_days,
            rclone_remote=settings.t3_rclone_remote,
            rclone_bucket=settings.t3_rclone_bucket,
        )
        return await job.run(dry_run=not execute, delete=execute)

    # ------------------------------------------------------------------ tick
    async def tick(self, *, execute: bool = False, force: bool = False) -> dict[str, Any]:
        """Run due schedules sequentially. `force` runs everything (the --once
        proof pass). Returns a report; each run also lands in audit_log."""
        now = self._now()
        ran: list[dict[str, Any]] = []
        for sched in self._schedules:
            if not force and not sched.due(now):
                continue
            started = time.time()
            try:
                detail = await sched.fn(execute)
                status = "ok"
            except Exception as exc:  # noqa: BLE001 — one job failing never stops the day
                detail = {"error": repr(exc)}
                status = "error"
                log.error("scheduled job failed", extra={"job": sched.name, "error": repr(exc)})
            # audit ledger only on apply runs — dry-run touches no DB rows
            if execute:
                await self._audit(
                    sched.name, detail if isinstance(detail, dict) else {"result": detail}
                )
            ran.append({
                "job": sched.name,
                "status": status,
                "duration_s": round(time.time() - started, 2),
                "detail": detail,
            })
            sched.advance(self._now())
        return {
            "scheduler": "backend timers (ADR 0007 — pg_cron NOT installed)",
            "mode": "execute" if execute else "dry-run",
            "at": now.isoformat(),
            "jobs_run": ran,
        }

    async def run_locked(self, *, execute: bool = False, force: bool = False) -> dict[str, Any]:
        """Advisory-lock gate: a second scheduler instance exits without work."""
        async with self._db.session() as conn:
            locked = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)", SCHEDULER_LOCK_KEY
            )
            if not locked:
                return {"scheduler": "another instance holds the lock — exiting", "jobs_run": []}
            try:
                return await self.tick(execute=execute, force=force)
            finally:
                await conn.fetchval("SELECT pg_advisory_unlock($1)", SCHEDULER_LOCK_KEY)


# --------------------------------------------------------------------- CLI
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="THE tier scheduler (backend timers)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="plan only (default)")
    mode.add_argument("--execute", action="store_true", help="apply job writes/drops")
    run = ap.add_mutually_exclusive_group()
    run.add_argument("--once", action="store_true", help="one forced tick, then exit")
    run.add_argument("--loop", action="store_true", help="daemon: tick on cadence")
    ap.add_argument("--report", default="", help="write the report JSON here")
    return ap.parse_args(argv)


async def _async_main(args: argparse.Namespace) -> dict[str, Any]:
    settings = get_settings()
    if not settings.database_url:
        raise ConfigError("GAMMASUMMIT_DATABASE_URL is required")
    db = Database(settings.database_url)
    owner_db = Database(settings.db_owner_url) if settings.db_owner_url else None
    await db.connect()
    if owner_db is not None:
        await owner_db.connect()
    try:
        scheduler = Scheduler(db, [], owner_db=owner_db)
        scheduler.build()
        if args.loop:
            reports = []
            while True:  # daemon — operator stops via systemd/kill
                reports.append(await scheduler.run_locked(execute=args.execute))
                await asyncio.sleep(30)
        return await scheduler.run_locked(execute=args.execute, force=True)
    finally:
        if owner_db is not None:
            await owner_db.close()
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
