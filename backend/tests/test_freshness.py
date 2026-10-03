"""Unit tests: E2.4 freshness metric — threshold math, market-hours gating,
as-of clock hook, audit-window job check, Uptime Kuma push beacon.

Pure logic where possible; the push beacon is exercised against a real local
HTTP server (real socket, real query string — no mocking of urllib).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from backend.jobs.freshness import (
    ALERT,
    OK,
    FreshnessJob,
    market_open,
    push_all,
    push_beacon,
)

# Friday 2026-10-02: 15:00Z = 11:00 ET (market open), 21:30Z = 17:30 ET (closed).
NOW_OPEN = dt.datetime(2026, 10, 2, 15, 0, tzinfo=dt.timezone.utc)
NOW_CLOSED = dt.datetime(2026, 10, 2, 21, 30, tzinfo=dt.timezone.utc)
NOW_SATURDAY = dt.datetime(2026, 10, 3, 15, 0, tzinfo=dt.timezone.utc)


def run(coro):
    return asyncio.run(coro)


class FakeDb:
    """Routes the three freshness queries: per-table metrics (fetchrow with
    'AS newest'), T0/T1 maxima (fetchval 'SELECT max('), audit rows (fetch)."""

    def __init__(self, metrics=None, t0_max=None, t1_max=None, audit_rows=None):
        self.metrics = dict(metrics or {})
        self.t0_max = dict(t0_max or {})
        self.t1_max = t1_max
        self.audit_rows = list(audit_rows or [])

    async def fetchrow(self, query, *args):
        if "AS newest" in query:
            for table, val in self.metrics.items():
                if f"FROM {table}" in query:
                    return val
            return {"newest": None, "rows": 0}
        return None

    async def fetchval(self, query, *args):
        if "FROM gamma_bucket_5m" in query:
            return self.t1_max
        for table, val in self.t0_max.items():
            if f"FROM {table}" in query:
                return val
        return None

    async def fetch(self, query, *args):
        if "FROM audit_log" in query:
            return self.audit_rows
        return []

    async def execute(self, query, *args):
        return "OK"


def ts(minutes_ago: float, now: dt.datetime) -> dt.datetime:
    return now - dt.timedelta(minutes=minutes_ago)


class TestMarketOpen(unittest.TestCase):
    def test_open_hours(self):
        self.assertTrue(market_open(NOW_OPEN))
        self.assertFalse(market_open(NOW_CLOSED))
        self.assertFalse(market_open(NOW_SATURDAY))


class TestT0Freshness(unittest.TestCase):
    def _report(self, db, now):
        return run(FreshnessJob(db, now=lambda: now).run())

    def _verdict(self, report, check_id):
        return next(c["verdict"] for c in report["checks"] if c["id"] == check_id)

    def test_fresh_during_market_ok(self):
        db = FakeDb(
            metrics={"gamma_snapshot": {"newest": ts(1, NOW_OPEN), "rows": 5}},
            t0_max={"gamma_snapshot": ts(1, NOW_OPEN)},
        )
        self.assertEqual(self._verdict(self._report(db, NOW_OPEN), "t0_freshness"), OK)

    def test_stale_during_market_alerts(self):
        db = FakeDb(
            metrics={"gamma_snapshot": {"newest": ts(20, NOW_OPEN), "rows": 5}},
            t0_max={"gamma_snapshot": ts(20, NOW_OPEN)},
        )
        self.assertEqual(self._verdict(self._report(db, NOW_OPEN), "t0_freshness"), ALERT)

    def test_stale_after_close_is_gated(self):
        db = FakeDb(
            metrics={"gamma_snapshot": {"newest": ts(120, NOW_CLOSED), "rows": 5}},
            t0_max={"gamma_snapshot": ts(120, NOW_CLOSED)},
        )
        self.assertEqual(self._verdict(self._report(db, NOW_CLOSED), "t0_freshness"), OK)

    def test_empty_t0_during_market_alerts(self):
        db = FakeDb(metrics={}, t0_max={})
        self.assertEqual(self._verdict(self._report(db, NOW_OPEN), "t0_freshness"), ALERT)
        self.assertEqual(self._verdict(self._report(db, NOW_CLOSED), "t0_freshness"), OK)


class TestDownsamplerLag(unittest.TestCase):
    def _verdict(self, db, now):
        report = run(FreshnessJob(db, now=lambda: now).run())
        return next(c["verdict"] for c in report["checks"] if c["id"] == "downsampler_lag")

    def test_small_lag_ok(self):
        db = FakeDb(t0_max={"gamma_snapshot": NOW_OPEN}, t1_max=ts(10, NOW_OPEN))
        self.assertEqual(self._verdict(db, NOW_OPEN), OK)

    def test_large_lag_alerts(self):
        db = FakeDb(t0_max={"gamma_snapshot": NOW_OPEN}, t1_max=ts(45, NOW_OPEN))
        self.assertEqual(self._verdict(db, NOW_OPEN), ALERT)


class TestRetentionJobs(unittest.TestCase):
    def _verdict(self, audit_rows, now=NOW_OPEN):
        db = FakeDb(audit_rows=audit_rows)
        report = run(FreshnessJob(db, now=lambda: now).run())
        return next(c["verdict"] for c in report["checks"] if c["id"] == "retention_jobs")

    def test_both_jobs_ok(self):
        rows = [
            {"action": "retention_t0", "ts": NOW_OPEN, "detail": {"segments": 3}},
            {"action": "export_cold", "ts": NOW_OPEN, "detail": {"segments": 2}},
        ]
        self.assertEqual(self._verdict(rows), OK)

    def test_missing_job_alerts(self):
        rows = [{"action": "retention_t0", "ts": NOW_OPEN, "detail": "{}"}]
        self.assertEqual(self._verdict(rows), ALERT)

    def test_error_detail_counts_as_missed(self):
        rows = [
            {"action": "retention_t0", "ts": NOW_OPEN, "detail": {"error": "boom"}},
            {"action": "export_cold", "ts": NOW_OPEN, "detail": {"error": "boom"}},
        ]
        self.assertEqual(self._verdict(rows), ALERT)

    def test_string_detail_parsed(self):
        rows = [
            {"action": "retention_t0", "ts": NOW_OPEN, "detail": '{"ok": 1}'},
            {"action": "export_cold", "ts": NOW_OPEN, "detail": '{"ok": 1}'},
        ]
        self.assertEqual(self._verdict(rows), OK)


class TestAsOfHook(unittest.TestCase):
    def test_as_of_shifts_evaluation_only(self):
        # 20-min-old payload relative to --as-of 2026-10-05 (market open) -> alert.
        as_of = dt.datetime(2026, 10, 5, 15, 0, tzinfo=dt.timezone.utc)
        newest = as_of - dt.timedelta(minutes=20)
        db = FakeDb(metrics={"gamma_snapshot": {"newest": newest, "rows": 1}},
                    t0_max={"gamma_snapshot": newest})
        report = run(FreshnessJob(db).run(as_of=as_of))
        self.assertEqual(report["as_of"], as_of.isoformat())
        verdict = next(c["verdict"] for c in report["checks"] if c["id"] == "t0_freshness")
        self.assertEqual(verdict, ALERT)


class _Capture(BaseHTTPRequestHandler):
    hits: list = []

    def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler API
        _Capture.hits.append(parse_qs(urlparse(self.path).query))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *args, **kwargs):  # quiet
        return


class TestKumaPush(unittest.TestCase):
    def setUp(self):
        _Capture.hits = []
        self.server = HTTPServer(("127.0.0.1", 0), _Capture)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_beacon_sends_status_down(self):
        url = f"http://127.0.0.1:{self.port}/api/push/tokentest"
        result = push_beacon(url, up=False, msg="t0_freshness: alert — stale")
        self.assertTrue(result["ok"])
        self.assertEqual(_Capture.hits[0]["status"], ["down"])
        self.assertIn("t0_freshness: alert", _Capture.hits[0]["msg"][0])

    def test_beacon_never_raises_on_dead_url(self):
        result = push_beacon("http://127.0.0.1:1/api/push/x", up=True, msg="ok", timeout_s=1)
        self.assertFalse(result["ok"])

    def test_push_all_maps_verdicts(self):
        class S:
            kuma_push_overall = f"http://127.0.0.1:{self.port}/api/push/overall"
            kuma_push_t0_freshness = f"http://127.0.0.1:{self.port}/api/push/t0"
            kuma_push_downsampler_lag = None
            kuma_push_retention_jobs = None

        report = {
            "overall": ALERT,
            "checks": [
                {"id": "t0_freshness", "verdict": ALERT, "detail": "stale"},
                {"id": "downsampler_lag", "verdict": OK, "detail": "fine"},
                {"id": "retention_jobs", "verdict": OK, "detail": "ran"},
            ],
        }
        results = push_all(report, S())
        self.assertEqual(set(results), {"overall", "t0_freshness"})
        statuses = sorted(h["status"][0] for h in _Capture.hits)
        self.assertEqual(statuses, ["down", "down"])


if __name__ == "__main__":
    unittest.main()
