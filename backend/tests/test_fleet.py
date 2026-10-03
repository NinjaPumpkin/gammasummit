"""Unit tests: ingest fleet daemon logic (card E2.2).

Cycle behavior over fakes: per-ticker failure isolation, rate-pause aborts the
cycle (a paused source is never hammered), gap work lands in the backfill
queue, and the lazy-backfill handler writes T0.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import unittest

from backend.core.errors import IngestError, RateLimitError, UpstreamError
from backend.ingest.fleet import Fleet

TS = dt.datetime(2026, 10, 2, 16, 0, tzinfo=dt.timezone.utc)

PRICE_PAYLOAD = {
    "prev": "763.99",
    "regular": {"close": "769.64", "market_time": "regular", "tape_time": "2026-10-02T19:59:59Z"},
    "pre": None,
    "post": None,
    "market_time": "regular",
}
CHAIN_LIST = [{"expires": "2026-10-09", "oi": 1, "number_of_strikes": 2},
              {"expires": "2026-11-06", "oi": 2, "number_of_strikes": 2}]
CONTRACT = {
    "iv": 0.13, "expires": "2026-10-09", "delta": 0.33, "theta": -0.31,
    "gamma": 0.023, "open_interest": 10, "volume": 20, "last_price": "3.41",
    "option_symbol": "SPY261009C00770000", "strike": "770", "underlying_symbol": "SPY",
    "avg_price": "4.96", "option_type": "call", "bid_volume": 1, "ask_volume": 2,
    "mid_volume": 3, "prev_oi": 9, "theo": 3.3, "vega": 0.4,
    "high_price": "6.0", "last_tape_time": "2026-09-30T21:35:58Z",
    "low_price": "3.1", "neutral_volume": 0, "charm": -0.2, "vanna": 0.06,
}
FLOW_ALERT = {
    "option_chain": "SPY261001C00765000", "created_at": "2026-09-30T20:15:27Z",
    "price": "1.55", "type": "call", "expiry": "2026-10-01", "strike": "765",
    "ticker": "SPY", "total_size": 155, "total_premium": "24017",
    "underlying_price": "763.39", "has_sweep": False, "has_multileg": False,
}
DARK_TRADE = {"size": 674, "ticker": "SPY", "created_at": "2026-09-30T15:00:00Z",
              "price": "149.855", "premium": "101.0", "market_center": "L",
              "tracking_id": 555, "executed_at": "2026-09-30T14:59:59Z",
              "canceled": False}


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fail = {}  # (ticker, stage) -> exception instance

    def _maybe(self, key):
        self.calls.append(key)
        exc = self.fail.get(key)
        if exc:
            raise exc

    def price(self, ticker):
        self._maybe((ticker, "price"))
        return PRICE_PAYLOAD

    def chain_expiries(self, ticker):
        self._maybe((ticker, "chain_expiries"))
        return CHAIN_LIST

    def chain_expiry(self, ticker, expiry):
        self._maybe((ticker, "chain_expiry", expiry))
        return {"rows": [CONTRACT], "price_data": {"type": "regular", "price": "769.64"}}

    def flow_alerts(self, ticker):
        self._maybe((ticker, "flow"))
        return [dict(FLOW_ALERT, ticker=ticker)]

    def dark_pool(self, limit=50):
        self._maybe(("*", "dark_pool"))
        return [DARK_TRADE]

    def stats(self):
        return {"source": "phx", "calls": len(self.calls)}


class FakeDb:
    def __init__(self):
        self.batches = []

    async def executemany(self, query, args_seq):
        self.batches.append((query, list(args_seq)))

    def tables_written(self):
        out = {}
        for query, args in self.batches:
            table = query.split("INSERT INTO ")[1].split(" ")[0]
            out[table] = out.get(table, 0) + len(args)
        return out


class FleetCycleTest(unittest.TestCase):
    def run_cycle(self, fleet, tickers):
        return asyncio.run(fleet.run_cycle(tickers))

    def test_full_cycle_writes_all_t0_tables(self):
        client, db = FakeClient(), FakeDb()
        fleet = Fleet(client, db, max_expiries=1)
        report = self.run_cycle(fleet, ["SPY"])
        self.assertEqual(report["failures"], [])
        self.assertIsNone(report["aborted"])
        written = db.tables_written()
        self.assertEqual(written.get("spot_tick"), 1)
        self.assertEqual(written.get("gamma_snapshot"), 1)  # 1 strike cell
        self.assertEqual(written.get("flow_print"), 1)
        self.assertEqual(written.get("darkpool_print"), 1)
        # max_expiries=1 → exactly one chain_expiry fetch
        self.assertIn(("SPY", "chain_expiry", "2026-10-09"), client.calls)

    def test_one_bad_ticker_never_kills_the_cycle(self):
        client, db = FakeClient(), FakeDb()
        client.fail[("BAD", "price")] = UpstreamError("boom", source="phx")
        enqueued = []

        async def enqueue(payload):
            enqueued.append(payload)
            return len(enqueued)

        fleet = Fleet(client, db, max_expiries=1, enqueue_backfill=enqueue)
        report = self.run_cycle(fleet, ["BAD", "SPY"])
        self.assertEqual(len(report["failures"]), 1)
        self.assertEqual(report["failures"][0]["ticker"], "BAD")
        self.assertEqual(report["tickers_completed"], ["SPY"])
        self.assertTrue(db.tables_written())
        # failed ticker's gap work is queued for lazy backfill
        self.assertEqual(
            sorted(p["dataset"] for p in enqueued), ["flow", "gamma_chain", "spot"]
        )
        self.assertTrue(all(p["ticker"] == "BAD" for p in enqueued))

    def test_rate_pause_aborts_cycle_without_hammering(self):
        client, db = FakeClient(), FakeDb()
        client.fail[("A", "price")] = RateLimitError(
            "pause", retry_after_s=60.0, source="phx"
        )
        fleet = Fleet(client, db, max_expiries=1)
        report = self.run_cycle(fleet, ["A", "B"])
        self.assertIsNotNone(report["aborted"])
        # B never dialed after the pause.
        self.assertFalse(any(c[0] == "B" for c in client.calls))
        self.assertIn({"ticker": "B", "dataset": "*", "error": "cycle_aborted"},
                      report["failures"])


class GapHandlerTest(unittest.TestCase):
    def test_run_gap_gamma_chain(self):
        client, db = FakeClient(), FakeDb()
        fleet = Fleet(client, db, max_expiries=1)
        out = asyncio.run(fleet.run_gap({
            "ticker": "spy", "dataset": "gamma_chain",
            "date_from": "2026-10-01", "date_to": "2026-10-02",
        }))
        self.assertEqual(out["ticker"], "SPY")
        self.assertEqual(out["rows"], 1)
        self.assertEqual(db.tables_written().get("gamma_snapshot"), 1)

    def test_run_gap_spot(self):
        client, db = FakeClient(), FakeDb()
        fleet = Fleet(client, db)
        out = asyncio.run(fleet.run_gap({"ticker": "SPY", "dataset": "spot"}))
        self.assertEqual(out["rows"], 1)

    def test_run_gap_dark_pool_filters_ticker(self):
        client, db = FakeClient(), FakeDb()
        fleet = Fleet(client, db)
        out = asyncio.run(fleet.run_gap({"ticker": "SPY", "dataset": "dark_pool"}))
        self.assertEqual(out["rows"], 1)
        out_none = asyncio.run(fleet.run_gap({"ticker": "ZZZZ", "dataset": "dark_pool"}))
        self.assertEqual(out_none["rows"], 0)

    def test_run_gap_unknown_dataset(self):
        fleet = Fleet(FakeClient(), FakeDb())
        with self.assertRaises(IngestError):
            asyncio.run(fleet.run_gap({"ticker": "SPY", "dataset": "nope"}))


if __name__ == "__main__":
    unittest.main()
