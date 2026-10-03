"""Unit tests: E2.3 tier jobs — downsampler/rollups math, export_cold
export-first retention, single-scheduler semantics.

Math is tested pure (GEX convention, net law, window laws). export_cold is
tested end-to-end on a real tmp dir with real Parquet: dry-run performs ZERO
writes, delete refuses unverified manifests, the rclone leg is skipped without
a remote and gates delete when configured. Scheduler tests pin the ONE
scheduler: cadence semantics, advisory-lock contention, audit trail, and
one-job-failure isolation.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import shutil
import tempfile
import unittest

from backend.core.errors import ConfigError
from backend.jobs.export_cold import (
    MAX_T2_RETENTION_DAYS,
    MIN_T2_RETENTION_DAYS,
    ExportColdJob,
)
from backend.jobs.rollups import (
    RAW_HORIZON_HOURS,
    ROLLUP_SCHEMA_VERSION,
    DownsamplerJob,
    RollupsJob,
    gex,
    net,
)
from backend.jobs.scheduler import SCHEDULER_LOCK_KEY, Scheduled, Scheduler

TS = dt.datetime(2026, 10, 2, 16, 0, tzinfo=dt.timezone.utc)
OLD_DAY = dt.date(2026, 8, 1)

SEGMENT_ROW = {
    "ticker": "SPY", "day": OLD_DAY, "rows": 2,
    "min_ts": TS - dt.timedelta(days=60), "max_ts": TS - dt.timedelta(days=60),
}
EXPORT_ROW_A = {
    "ticker": "SPY", "expiry": dt.date(2026, 8, 21), "strike": 700.0,
    "day": OLD_DAY, "call_oi": 10, "put_oi": 12,
    "call_volume": 5, "put_volume": 7, "call_gex": 1.5, "put_gex": 0.5,
    "net_gex": 1.0, "spot_close": 769.64, "schema_version": 1,
}
EXPORT_ROW_B = dict(EXPORT_ROW_A, strike=710.0, call_oi=1)


class FakeDb:
    """Captures SQL at the Database boundary. plan/export rows are routed per
    table name (GROUP BY = plan, SELECT * = export)."""

    def __init__(self, plan_rows=None, export_rows=None, lock_ok=True):
        self.plan_rows = dict(plan_rows or {})
        self.export_rows = dict(export_rows or {})
        self.lock_ok = lock_ok
        self.calls = []

    def _route(self, query, table_map):
        for table, rows in table_map.items():
            if f"FROM {table} " in query:
                return rows
        return []

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "GROUP BY" in query:
            return self._route(query, self.plan_rows)
        if query.startswith("SELECT * FROM"):
            return self._route(query, self.export_rows)
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "pg_try_advisory_lock" in query:
            return self.lock_ok
        if "pg_advisory_unlock" in query:
            return True
        return True

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "DELETE 3"

    async def executemany(self, query, args_seq):
        self.calls.append(("executemany", query, args_seq))
        return "INSERT 0"

    def session(self):
        """Dedicated-connection stand-in (core.db.Database.session contract)."""
        fake = self

        class _Conn:
            async def fetchval(self, query, *args):
                return await fake.fetchval(query, *args)

        class _CM:
            async def __aenter__(self):
                return _Conn()

            async def __aexit__(self, *exc):
                return False

        return _CM()

    def sql_of(self, needle):
        return [c for c in self.calls if needle in c[1]]


class RollupMathTest(unittest.TestCase):
    def test_gex_convention(self):
        """Heatmap GEX mode: gamma x 100 x 0.01 x OI x S^2 == gamma x OI x S^2."""
        self.assertEqual(gex(2.0, 100, 50.0), 2.0 * 100 * 50.0 * 50.0)
        self.assertIsNone(gex(None, 1, 1.0))
        self.assertIsNone(gex(1.0, None, 1.0))
        self.assertIsNone(gex(1.0, 1, None))

    def test_net_law(self):
        self.assertEqual(net(10.0, 4.0), 6.0)
        self.assertIsNone(net(10.0, None))

    def test_downsampler_window_is_raw_horizon(self):
        job = DownsamplerJob(FakeDb(), now=lambda: TS)
        since, until = job.default_window()
        self.assertEqual(until - since, dt.timedelta(hours=RAW_HORIZON_HOURS))
        self.assertEqual(until, TS)

    def test_rollup_windows_obey_tier_law(self):
        job = RollupsJob(FakeDb(), now=lambda: TS)
        h_since, h_until = job.hourly_window()
        self.assertEqual(h_until - h_since, dt.timedelta(hours=24))
        self.assertEqual(h_until.minute, 0)
        e_since, e_until = job.eod_window()
        self.assertEqual(e_since.date(), dt.date(2026, 10, 1))
        self.assertEqual(e_until - e_since, dt.timedelta(days=1))

    def test_downsampler_dry_run_writes_nothing(self):
        db = FakeDb()
        report = asyncio.run(DownsamplerJob(db, now=lambda: TS).run(dry_run=True))
        self.assertEqual(report["mode"], "dry-run (no writes)")
        self.assertEqual(db.sql_of("executemany"), [])

    def test_downsampler_execute_upserts_idempotent_keys(self):
        row = {
            "ticker": "SPY", "expiry": dt.date(2026, 10, 9), "strike": 700.0,
            "bucket": TS, "call_oi_first": 1, "call_oi_last": 2,
            "put_oi_first": 3, "put_oi_last": 4, "call_volume": 5, "put_volume": 6,
            "call_gamma_avg": 0.1, "put_gamma_avg": 0.2, "call_iv_avg": 0.3,
            "put_iv_avg": 0.4, "spot_close": 769.6, "samples": 2,
        }
        db = FakeDb(plan_rows={"gamma_snapshot": [row]})
        report = asyncio.run(DownsamplerJob(db, now=lambda: TS).run(dry_run=False))
        self.assertEqual(report["t1_rows_written"], 1)
        writes = db.sql_of("ON CONFLICT")
        self.assertEqual(len(writes), 1)
        self.assertIn("ON CONFLICT (ticker, expiry, strike, bucket)", writes[0][1])


class ExportColdTest(unittest.TestCase):
    def make_job(self, db, tmp, days=MAX_T2_RETENTION_DAYS, remote="", runner=None):
        return ExportColdJob(
            db,
            t3_root=tmp,
            t2_retention_days=days,
            rclone_remote=remote,
            rclone_bucket="gammasummit-cold",
            runner=runner,
            now=lambda: TS,
        )

    def test_t2_window_is_owner_locked(self):
        for bad in (MIN_T2_RETENTION_DAYS - 1, MAX_T2_RETENTION_DAYS + 1, 0, 999):
            with self.assertRaises(ConfigError):
                self.make_job(FakeDb(), "/tmp/x", days=bad)
        self.make_job(FakeDb(), "/tmp/x", days=MIN_T2_RETENTION_DAYS)  # in range
        self.make_job(FakeDb(), "/tmp/x", days=MAX_T2_RETENTION_DAYS)  # in range

    def test_dry_run_writes_nothing(self):
        tmp = tempfile.mkdtemp(prefix="gs-cold-")
        try:
            db = FakeDb(plan_rows={"strike_eod": [SEGMENT_ROW]})
            report = asyncio.run(self.make_job(db, tmp).run(dry_run=True))
            self.assertEqual(report["mode"], "dry-run (no writes)")
            self.assertEqual(report["segments"], 1)
            self.assertEqual(report["rows_at_risk"], 2)
            self.assertEqual(report["retention_days"], {"T1": 30, "T2": 365})
            planned = report["planned_files"][0]
            self.assertEqual(
                planned["file_path"],
                f"strike_eod/ticker=SPY/date={OLD_DAY}/part-20261002T160000Z.parquet",
            )
            self.assertFalse(os.path.exists(os.path.join(tmp, "strike_eod")))
            self.assertEqual(db.sql_of("INSERT INTO export_manifest"), [])
            self.assertEqual(db.sql_of("DELETE FROM"), [])
        finally:
            shutil.rmtree(tmp)

    def test_execute_export_first_then_delete_verified(self):
        tmp = tempfile.mkdtemp(prefix="gs-cold-")
        try:
            db = FakeDb(
                plan_rows={"strike_eod": [SEGMENT_ROW]},
                export_rows={"strike_eod": [EXPORT_ROW_A, EXPORT_ROW_B]},
            )
            job = self.make_job(db, tmp)
            report = asyncio.run(job.run(dry_run=False, delete=True))
            self.assertEqual(report["exported_files"], 1)
            self.assertEqual(report["verified_files"], 1)
            self.assertEqual(report["verify_failures"], [])
            self.assertEqual(report["deleted_rows"], {"strike_eod": 3})
            parquet = os.path.join(
                tmp, "strike_eod", "ticker=SPY", f"date={OLD_DAY}",
                "part-20261002T160000Z.parquet",
            )
            self.assertTrue(os.path.exists(parquet))
            # ordering proof: manifest INSERT -> verify UPDATE -> DELETE
            seq = [c[1].split()[0] + " " + c[1].split()[1] for c in db.calls
                   if c[1].startswith(("INSERT", "UPDATE", "DELETE"))]
            self.assertEqual(
                seq, ["INSERT INTO", "UPDATE export_manifest", "DELETE FROM"],
            )
        finally:
            shutil.rmtree(tmp)

    def test_delete_refuses_unverified_manifest(self):
        job = self.make_job(FakeDb(), "/tmp/x")
        manifest = {
            "table": "strike_eod", "tier": "T2", "ticker": "SPY", "day": OLD_DAY,
            "file_path": "x.parquet", "exported_at": TS, "verified": False,
        }
        with self.assertRaises(ConfigError):
            asyncio.run(job.delete([manifest]))

    def test_corrupt_export_blocks_delete(self):
        tmp = tempfile.mkdtemp(prefix="gs-cold-")
        try:
            db = FakeDb(
                plan_rows={"strike_eod": [SEGMENT_ROW]},
                export_rows={"strike_eod": [EXPORT_ROW_A, EXPORT_ROW_B]},
            )
            job = self.make_job(db, tmp)
            # tamper with the Parquet after export() wrote it
            orig_export = job.export

            async def export_then_corrupt(segments):
                manifests = await orig_export(segments)
                with open(manifests[0]["abs_path"], "wb") as fh:
                    fh.write(b"corrupt")
                return manifests

            job.export = export_then_corrupt
            with self.assertRaises(ConfigError):
                asyncio.run(job.run(dry_run=False, delete=True))
            self.assertEqual(db.sql_of("DELETE FROM"), [])
        finally:
            shutil.rmtree(tmp)

    def test_rclone_skipped_without_remote(self):
        tmp = tempfile.mkdtemp(prefix="gs-cold-")
        try:
            called = []

            def runner(cmd, **kwargs):
                called.append(cmd)
                raise AssertionError("rclone must not run without a remote")

            db = FakeDb(
                plan_rows={"strike_eod": [SEGMENT_ROW]},
                export_rows={"strike_eod": [EXPORT_ROW_A]},
            )
            report = asyncio.run(self.make_job(db, tmp, runner=runner).run(dry_run=False))
            self.assertIn("skipped (no rclone remote configured)", report["rclone"])
            self.assertEqual(called, [])
        finally:
            shutil.rmtree(tmp)

    def test_rclone_copy_gates_delete(self):
        tmp = tempfile.mkdtemp(prefix="gs-cold-")
        try:
            # mismatch runner: remote size 0 != local -> r2_verified False
            def runner_mismatch(cmd, **kwargs):
                class Result:
                    stdout = ""
                if cmd[1] == "lsjson":
                    Result.stdout = json.dumps([{"Size": 0}])
                return Result()

            db = FakeDb(
                plan_rows={"strike_eod": [SEGMENT_ROW]},
                export_rows={"strike_eod": [EXPORT_ROW_A]},
            )
            job = self.make_job(db, tmp, remote="r2", runner=runner_mismatch)
            with self.assertRaises(ConfigError):
                asyncio.run(job.run(dry_run=False, delete=True))
            self.assertEqual(db.sql_of("DELETE FROM"), [])

            # match runner: lsjson echoes the local byte_size -> verified
            state = {"size": 0}

            def runner_match(cmd, **kwargs):
                class Result:
                    stdout = ""
                if cmd[1] == "lsjson":
                    Result.stdout = json.dumps([{"Size": state["size"]}])
                return Result()

            db2 = FakeDb(
                plan_rows={"strike_eod": [SEGMENT_ROW]},
                export_rows={"strike_eod": [EXPORT_ROW_A]},
            )
            job2 = self.make_job(db2, tmp, remote="r2", runner=runner_match)
            orig_export = job2.export

            async def export_capture(segments):
                manifests = await orig_export(segments)
                state["size"] = manifests[0]["byte_size"]
                return manifests

            job2.export = export_capture
            report = asyncio.run(job2.run(dry_run=False, delete=True))
            self.assertEqual(report["r2_verified_files"], 1)
            self.assertEqual(report["deleted_rows"], {"strike_eod": 3})
        finally:
            shutil.rmtree(tmp)


class SchedulerTest(unittest.TestCase):
    def test_schedule_needs_exactly_one_mode(self):
        with self.assertRaises(ConfigError):
            Scheduled("x", None, every_s=60, at_utc="22:30")
        with self.assertRaises(ConfigError):
            Scheduled("x", None)
        Scheduled("x", None, every_s=60)  # ok
        Scheduled("x", None, at_utc="22:30")  # ok

    def test_daily_schedule_rolls_to_next_day(self):
        s = Scheduled("x", None, at_utc="22:30")
        s.advance(TS.replace(hour=23, minute=0))  # past today's 22:30
        self.assertEqual(s.next_due, dt.datetime(2026, 10, 3, 22, 30, tzinfo=dt.timezone.utc))

    def test_interval_schedule_advances_by_seconds(self):
        s = Scheduled("x", None, every_s=300)
        s.advance(TS)
        self.assertEqual(s.next_due, TS + dt.timedelta(seconds=300))

    def run_sched(self, scheduler, execute=False):
        return asyncio.run(scheduler.tick(execute=execute, force=True))

    def test_tick_runs_jobs_and_writes_audit(self):
        db = FakeDb()
        ran = []

        async def job_fn(execute):
            ran.append(execute)
            return {"n": 1}

        sched = Scheduler(db, [Scheduled("j", job_fn, every_s=60)], now=lambda: TS)
        report = self.run_sched(sched, execute=True)
        self.assertEqual(ran, [True])
        audits = db.sql_of("INSERT INTO audit_log")
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0][2][3], "j")
        self.assertEqual(report["jobs_run"][0]["status"], "ok")
        self.assertIn("backend timers", report["scheduler"])

    def test_dry_run_writes_no_audit_rows(self):
        """Dry-run = zero DB rows (hard rule) — the audit ledger is written on
        apply runs only."""
        db = FakeDb()

        async def job_fn(execute):
            return {}

        sched = Scheduler(db, [Scheduled("j", job_fn, every_s=60)], now=lambda: TS)
        self.run_sched(sched, execute=False)
        self.assertEqual(db.sql_of("INSERT INTO audit_log"), [])

    def test_execute_flag_reaches_jobs(self):
        db = FakeDb()
        ran = []

        async def job_fn(execute):
            ran.append(execute)
            return {}

        sched = Scheduler(db, [Scheduled("j", job_fn, every_s=60)], now=lambda: TS)
        self.run_sched(sched, execute=True)
        self.assertEqual(ran, [True])

    def test_one_job_failure_does_not_stop_the_day(self):
        db = FakeDb()
        second = []

        async def boom(execute):
            raise RuntimeError("nope")

        async def fine(execute):
            second.append(True)
            return {}

        sched = Scheduler(
            db, [Scheduled("a", boom, every_s=60), Scheduled("b", fine, every_s=60)],
            now=lambda: TS,
        )
        report = self.run_sched(sched)
        self.assertEqual(second, [True])
        self.assertEqual(report["jobs_run"][0]["status"], "error")
        self.assertEqual(report["jobs_run"][1]["status"], "ok")

    def test_lock_contention_runs_nothing(self):
        db = FakeDb(lock_ok=False)
        ran = []

        async def job_fn(execute):
            ran.append(True)
            return {}

        sched = Scheduler(db, [Scheduled("j", job_fn, every_s=60)], now=lambda: TS)
        report = asyncio.run(sched.run_locked())
        self.assertEqual(ran, [])
        self.assertEqual(report["jobs_run"], [])
        # the lock key is the documented constant
        lock_call = db.sql_of("pg_try_advisory_lock")[0]
        self.assertEqual(lock_call[2][0], SCHEDULER_LOCK_KEY)

    def test_rollover_schema_version_is_pinned(self):
        self.assertEqual(ROLLUP_SCHEMA_VERSION, 1)


if __name__ == "__main__":
    unittest.main()
