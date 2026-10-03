"""Unit tests: pgmq backfill worker + T0 retention job (card E2.2).

Queue semantics are tested against a fake db boundary (read/ack/requeue/
dead-letter, poison isolation, rate-pause never burns an attempt). Retention
is tested end-to-end on a real tmp dir with real Parquet: dry-run performs ZERO
writes, delete refuses unverified manifests, and the export-first sequence
(plan → export → manifest → verify → delete) is the only deletion path.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import shutil
import tempfile
import unittest

from backend.core.errors import ConfigError, RateLimitError
from backend.jobs.backfill import BackfillWorker, build_message, enqueue, valid_payload
from backend.jobs.retention import RetentionJob

TS = dt.datetime(2026, 10, 2, 16, 0, tzinfo=dt.timezone.utc)
OLD_DAY = dt.date(2026, 9, 29)


class FakeDb:
    """Captures SQL at the Database boundary. `reads` feeds pgmq.read rows;
    plan/export rows are routed per T0 table name."""

    def __init__(self, reads=None, plan_rows=None, export_rows=None):
        self.reads = [list(r) for r in (reads or [])]
        self.plan_rows = dict(plan_rows or {})
        self.export_rows = dict(export_rows or {})
        self.calls = []
        self.send_id = 100

    def _route(self, query, table_map):
        for table, rows in table_map.items():
            if f"FROM {table} " in query:
                return rows
        return []

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        if "pgmq.read" in query:
            return self.reads.pop(0) if self.reads else []
        if "GROUP BY" in query:
            return self._route(query, self.plan_rows)
        if query.startswith("SELECT * FROM"):
            return self._route(query, self.export_rows)
        return []

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "pgmq.send" in query:
            self.send_id += 1
            return self.send_id
        return True

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "DELETE 3"

    def sql_of(self, needle):
        return [c for c in self.calls if needle in c[1]]


def msg_row(msg_id, payload, read_ct=1):
    return {"msg_id": msg_id, "read_ct": read_ct, "message": json.dumps(payload)}


class BackfillQueueTest(unittest.TestCase):
    def run_worker(self, worker, **kwargs):
        return asyncio.run(worker.run(**kwargs))

    def test_message_contract(self):
        payload = build_message("spy", "gamma_chain", reason="cycle_gap", requested_by="fleet")
        self.assertEqual(payload["ticker"], "SPY")
        self.assertTrue(valid_payload(payload))
        self.assertFalse(valid_payload({"ticker": "SPY", "dataset": "nope"}))
        self.assertFalse(valid_payload("not-a-dict"))

    def test_enqueue_uses_pgmq_send(self):
        db = FakeDb()
        msg_id = asyncio.run(enqueue(db, build_message("SPY", "spot")))
        self.assertEqual(msg_id, 101)
        sends = db.sql_of("pgmq.send")
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0][2][0], "backfill")

    def test_happy_path_acks_message(self):
        payload = build_message("SPY", "spot")
        db = FakeDb(reads=[[msg_row(1, payload)], []])
        seen = []

        async def handler(p):
            seen.append(p)
            return {"rows": 2}

        report = self.run_worker(BackfillWorker(db, handler), max_messages=5)
        self.assertEqual(report["processed"], 1)
        self.assertEqual(seen[0]["ticker"], "SPY")
        self.assertTrue(db.sql_of("pgmq.delete"))

    def test_invalid_payload_dead_letters_immediately(self):
        db = FakeDb(reads=[[msg_row(1, {"dataset": "bogus"})], []])

        async def handler(p):
            raise AssertionError("handler must not run for poison")

        report = self.run_worker(BackfillWorker(db, handler), max_messages=5)
        self.assertEqual(report["dead_lettered"], 1)
        self.assertTrue(db.sql_of("pgmq.archive"))

    def test_handler_failure_requeues_with_backoff(self):
        payload = build_message("SPY", "flow")
        db = FakeDb(reads=[[msg_row(1, payload)], []])

        async def handler(p):
            raise RuntimeError("upstream exploded")

        report = self.run_worker(BackfillWorker(db, handler, max_attempts=5), max_messages=5)
        self.assertEqual(report["requeued"], 1)
        step = report["steps"][0]
        self.assertEqual(step["attempts"], 1)
        self.assertEqual(step["delay_s"], 30)
        self.assertTrue(db.sql_of("pgmq.delete"))  # old copy removed

    def test_attempts_exhaust_to_dead_letter_with_context(self):
        payload = dict(build_message("SPY", "flow"), attempts=4)
        db = FakeDb(reads=[[msg_row(1, payload)], []])

        async def handler(p):
            raise RuntimeError("still broken")

        report = self.run_worker(BackfillWorker(db, handler, max_attempts=5), max_messages=5)
        self.assertEqual(report["dead_lettered"], 1)
        archived_send = db.sql_of("pgmq.send")[0]
        body = json.loads(archived_send[2][1])
        self.assertEqual(body["attempts"], 5)
        self.assertIn("still broken", body["last_error"])

    def test_rate_pause_never_burns_an_attempt(self):
        payload = dict(build_message("SPY", "gamma_chain"), attempts=2)
        db = FakeDb(reads=[[msg_row(1, payload)], []])

        async def handler(p):
            raise RateLimitError("paused", retry_after_s=90.0, source="phx")

        report = self.run_worker(BackfillWorker(db, handler, max_attempts=5), max_messages=5)
        self.assertEqual(report["requeued"], 1)
        step = report["steps"][0]
        self.assertEqual(step["attempts"], 2)  # unchanged
        self.assertGreaterEqual(step["delay_s"], 90)

    def test_empty_queue_is_idle(self):
        db = FakeDb(reads=[[]])

        async def handler(p):
            return {}

        report = self.run_worker(BackfillWorker(db, handler), max_messages=5)
        self.assertEqual(report["consumed"], 0)


SEGMENT_ROW = {"ticker": "SPY", "day": OLD_DAY, "rows": 2,
               "min_ts": TS - dt.timedelta(days=3), "max_ts": TS - dt.timedelta(days=3)}
EXPORT_ROW_A = {"ticker": "SPY", "ts": TS - dt.timedelta(days=3), "seq": 0,
                "price": 769.64, "size": None, "source": "phx_price_v2:regular"}
EXPORT_ROW_B = {"ticker": "SPY", "ts": TS - dt.timedelta(days=3, minutes=5), "seq": 0,
                "price": 769.60, "size": None, "source": "phx_price_v2:regular"}


class RetentionTest(unittest.TestCase):
    def make_job(self, db, tmp, hours=48):
        return RetentionJob(
            db,
            t3_root=tmp,
            retention_hours=hours,
            now=lambda: TS,
        )

    def test_retention_window_is_owner_locked(self):
        for bad in (12, 23, 49, 72):
            with self.assertRaises(ConfigError):
                self.make_job(FakeDb(), "/tmp/x", hours=bad)
        self.make_job(FakeDb(), "/tmp/x", hours=24)  # in range

    def test_dry_run_writes_nothing(self):
        tmp = tempfile.mkdtemp(prefix="gs-ret-")
        try:
            db = FakeDb(plan_rows={"spot_tick": [SEGMENT_ROW]})
            report = asyncio.run(self.make_job(db, tmp).run(dry_run=True))
            self.assertEqual(report["mode"], "dry-run (no writes)")
            self.assertEqual(report["segments"], 1)
            self.assertEqual(report["rows_at_risk"], 2)
            self.assertEqual(
                report["export_first_order"],
                ["plan", "export", "manifest", "verify", "delete"],
            )
            planned = report["planned_files"][0]
            self.assertEqual(
                planned["file_path"],
                f"spot/ticker=SPY/date={OLD_DAY}/part-20261002T160000Z.parquet",
            )
            # zero side effects: no files, no INSERT/UPDATE/DELETE
            self.assertFalse(os.path.exists(os.path.join(tmp, "spot")))
            self.assertEqual(db.sql_of("INSERT INTO export_manifest"), [])
            self.assertEqual(db.sql_of("UPDATE export_manifest"), [])
            self.assertEqual(db.sql_of("DELETE FROM"), [])
        finally:
            shutil.rmtree(tmp)

    def test_delete_refuses_unverified_manifest(self):
        tmp = tempfile.mkdtemp(prefix="gs-ret-")
        try:
            db = FakeDb()
            job = self.make_job(db, tmp)
            manifest = {"table": "spot_tick", "ticker": "SPY", "day": OLD_DAY,
                        "file_path": "x.parquet", "exported_at": TS,
                        "verified": False}
            with self.assertRaises(ConfigError):
                asyncio.run(job.delete([manifest]))
        finally:
            shutil.rmtree(tmp)

    def test_execute_export_first_then_delete_verified(self):
        tmp = tempfile.mkdtemp(prefix="gs-ret-")
        try:
            db = FakeDb(plan_rows={"spot_tick": [SEGMENT_ROW]},
                        export_rows={"spot_tick": [EXPORT_ROW_A, EXPORT_ROW_B]})
            job = self.make_job(db, tmp)
            report = asyncio.run(job.run(dry_run=False, delete=True))
            self.assertEqual(report["mode"], "execute")
            self.assertEqual(report["exported_files"], 1)
            self.assertEqual(report["verified_files"], 1)
            self.assertEqual(report["verify_failures"], [])
            self.assertEqual(report["deleted_rows"], {"spot_tick": 3})

            parquet = os.path.join(
                tmp, "spot", "ticker=SPY", f"date={OLD_DAY}",
                "part-20261002T160000Z.parquet",
            )
            self.assertTrue(os.path.exists(parquet))
            self.assertGreater(report["exported_bytes"], 0)

            # ordering proof: manifest INSERT precedes the verify UPDATE, and
            # the DELETE lands after both.
            seq = [c[1].split()[0] + " " + c[1].split()[1] for c in db.calls
                   if c[1].startswith(("INSERT", "UPDATE", "DELETE"))]
            self.assertEqual(
                seq,
                ["INSERT INTO", "UPDATE export_manifest", "DELETE FROM"],
            )
        finally:
            shutil.rmtree(tmp)

    def test_unverified_export_blocks_delete_in_run(self):
        """verify() failing (file tampered) must stop the delete phase."""
        tmp = tempfile.mkdtemp(prefix="gs-ret-")
        try:
            db = FakeDb(plan_rows={"spot_tick": [SEGMENT_ROW]},
                        export_rows={"spot_tick": [EXPORT_ROW_A, EXPORT_ROW_B]})
            job = self.make_job(db, tmp)
            report = asyncio.run(job.run(dry_run=False, delete=False))
            self.assertEqual(report["verified_files"], 1)
            # corrupt the exported file outright
            for root, _dirs, files in os.walk(tmp):
                for f in files:
                    with open(os.path.join(root, f), "wb") as fh:
                        fh.write(b"corrupt")
            manifests = [{"table": "spot_tick", "ticker": "SPY", "day": OLD_DAY,
                          "file_path": "spot/ticker=SPY/x.parquet",
                          "abs_path": os.path.join(tmp, "spot", "ticker=SPY",
                                                  f"date={OLD_DAY}",
                                                  "part-20261002T160000Z.parquet"),
                          "exported_at": TS, "row_count": 2,
                          "sha256": "00", "min_ts": TS, "max_ts": TS}]
            manifests = asyncio.run(job.verify(manifests))
            self.assertFalse(manifests[0]["verified"])
            with self.assertRaises(ConfigError):
                asyncio.run(job.delete(manifests))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
