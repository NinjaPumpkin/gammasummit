"""Unit tests: T0 writers + batch-upsert (card E2.2).

Mapping evidence shapes (PHX payloads RE-probed 2026-10-02), idempotent
conflict-key upserts, and the safety laws (no synthesized values, unsafe
identifiers rejected).
"""
from __future__ import annotations

import datetime as dt
import unittest

from backend.core.db import QueryError, upsert_rows, upsert_sql
from backend.ingest import chain_writer, flow_writer, spot_writer
from backend.ingest.t0_writer import CONFLICT_KEYS, parse_ts, to_float, to_int, write_rows

TS = dt.datetime(2026, 10, 2, 16, 0, tzinfo=dt.timezone.utc)

CONTRACT_CALL = {
    "iv": 0.13, "expires": "2026-10-09", "delta": 0.33, "theta": -0.31,
    "gamma": 0.023, "open_interest": 5514, "volume": 8001, "last_price": "3.41",
    "option_symbol": "SPY261009C00770000", "strike": "770", "underlying_symbol": "SPY",
    "avg_price": "4.96", "option_type": "call", "bid_volume": 3341, "ask_volume": 3738,
    "mid_volume": 922, "prev_oi": 5319, "theo": 3.32, "vega": 0.43,
    "high_price": "6.05", "last_tape_time": "2026-09-30T21:35:58Z",
    "low_price": "3.15", "neutral_volume": 0, "charm": -0.26, "vanna": 0.06,
}
CONTRACT_PUT = dict(CONTRACT_CALL, option_type="put", option_symbol="SPY261009P00770000",
                    open_interest=2211, volume=3300, gamma=0.019)


class CoercionTest(unittest.TestCase):
    def test_parse_ts_iso_z(self):
        self.assertEqual(
            parse_ts("2026-10-02T19:59:59Z"), TS.replace(hour=19, minute=59, second=59)
        )

    def test_parse_ts_epoch_ms(self):
        self.assertEqual(
            parse_ts(1790799294591),
            dt.datetime.fromtimestamp(1790799294591 / 1000, tz=dt.timezone.utc),
        )

    def test_parse_ts_garbage_is_none(self):
        self.assertIsNone(parse_ts("not-a-date"))
        self.assertIsNone(parse_ts(None))

    def test_to_float_handles_phx_strings(self):
        self.assertEqual(to_float("763.99"), 763.99)
        self.assertIsNone(to_float(""))

    def test_to_int(self):
        self.assertEqual(to_int("5514"), 5514)
        self.assertIsNone(to_int(None))


class ChainWriterTest(unittest.TestCase):
    def test_call_put_merged_per_strike(self):
        rows = chain_writer.map_chain_rows("spy", [CONTRACT_CALL, CONTRACT_PUT], ts=TS, spot=769.64)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["ticker"], "SPY")
        self.assertEqual(row["expiry"], dt.date(2026, 10, 9))
        self.assertEqual(row["strike"], 770.0)
        self.assertEqual(row["ts"], TS)
        self.assertEqual(row["spot"], 769.64)
        self.assertEqual(row["call_oi"], 5514)
        self.assertEqual(row["put_oi"], 2211)
        self.assertEqual(row["call_gamma"], 0.023)
        self.assertEqual(row["put_gamma"], 0.019)
        self.assertEqual(row["source"], "phx_chains_expiry")
        # bid/ask prices are not served per contract — never synthesized.
        self.assertIsNone(row["call_bid"])
        self.assertIsNone(row["put_ask"])

    def test_two_strikes_two_rows_sorted(self):
        other = dict(CONTRACT_CALL, strike="771", option_symbol="SPY261009C00771000")
        rows = chain_writer.map_chain_rows("SPY", [other, CONTRACT_CALL], ts=TS, spot=None)
        self.assertEqual([r["strike"] for r in rows], [770.0, 771.0])

    def test_row_shape_is_homogeneous_for_upsert(self):
        rows = chain_writer.map_chain_rows("SPY", [CONTRACT_CALL, CONTRACT_PUT], ts=TS, spot=1.0)
        self.assertEqual(set(rows[0].keys()), set(CONFLICT_KEYS["gamma_snapshot"]) | {
            "spot", "call_oi", "put_oi", "call_volume", "put_volume",
            "call_bid", "call_ask", "put_bid", "put_ask",
            "call_iv", "put_iv", "call_delta", "put_delta", "call_gamma", "put_gamma",
            "call_vega", "put_vega", "call_theta", "put_theta", "source",
        })

    def test_latest_payload_ts_is_max_tape(self):
        late = dict(CONTRACT_CALL, last_tape_time="2026-10-01T10:00:00Z")
        self.assertEqual(
            chain_writer.latest_payload_ts([CONTRACT_CALL, late]),
            dt.datetime(2026, 10, 1, 10, 0, tzinfo=dt.timezone.utc),
        )


class SpotWriterTest(unittest.TestCase):
    PAYLOAD = {
        "prev": {"close": "763.99"},  # unstable shape (dict here) — never written
        "regular": {"close": "769.64", "market_time": "regular",
                    "tape_time": "2026-10-02T19:59:59Z"},
        "pre": {"close": "770.63", "market_time": "premarket",
                "tape_time": "2026-10-02T13:29:57Z"},
        "post": {"close": "769.34", "market_time": "postmarket",
                 "tape_time": "2026-10-02T21:24:36Z"},
        "market_time": "postmarket",
    }

    def test_sessions_written_with_tape_ts(self):
        rows = spot_writer.map_spot_rows("SPY", self.PAYLOAD)
        self.assertEqual(len(rows), 3)
        by_src = {r["source"]: r for r in rows}
        self.assertIn("phx_price_v2:regular", by_src)
        self.assertEqual(by_src["phx_price_v2:regular"]["price"], 769.64)
        self.assertEqual(by_src["phx_price_v2:regular"]["seq"], 0)
        self.assertIsNone(by_src["phx_price_v2:regular"]["size"])
        self.assertEqual(
            by_src["phx_price_v2:post"]["ts"],
            dt.datetime(2026, 10, 2, 21, 24, 36, tzinfo=dt.timezone.utc),
        )

    def test_prev_never_written(self):
        rows = spot_writer.map_spot_rows("SPY", self.PAYLOAD)
        self.assertFalse(any("prev" in r["source"] for r in rows))

    def test_missing_tape_time_skipped(self):
        payload = {"regular": {"close": "10.0"}}
        self.assertEqual(spot_writer.map_spot_rows("SPY", payload), [])


class FlowWriterTest(unittest.TestCase):
    ALERT = {
        "strike": "765", "start_time": 1790799294591, "option_chain": "SPY261001C00765000",
        "vega": 0.15, "iv": 0.14, "delta": 0.39, "ask": "1.56", "bid": "1.53",
        "open_interest": 3520, "total_premium": "24017", "expiry": "2026-10-01",
        "underlying_price": "763.39", "volume": 36245, "ticker": "SPY",
        "price": "1.55", "has_multileg": False, "theta": -1.1, "id": "0b02",
        "total_size": 155, "has_sweep": False, "type": "call",
        "created_at": "2026-09-30T20:15:27.198752Z",
    }

    def test_alert_maps_to_flow_print(self):
        rows, dropped = flow_writer.map_flow_rows([self.ALERT])
        self.assertEqual(dropped, 0)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["occ"], "SPY261001C00765000")
        self.assertEqual(row["opt_right"], "C")
        self.assertEqual(row["premium"], 24017.0)
        self.assertEqual(row["size"], 155)
        self.assertFalse(row["is_sweep"])
        self.assertEqual(row["source"], "phx_flow_alerts")

    def test_missing_occ_dropped_not_synthesized(self):
        bad = dict(self.ALERT, option_chain="")
        rows, dropped = flow_writer.map_flow_rows([bad, self.ALERT])
        self.assertEqual(len(rows), 1)
        self.assertEqual(dropped, 1)

    def test_darkpool_canceled_dropped(self):
        trades = [
            {"size": 674, "ticker": "SPCX", "created_at": "2026-09-30T15:00:00Z",
             "price": "149.855", "premium": "101002.270", "market_center": "L",
             "tracking_id": 9599305906444, "executed_at": "2026-09-30T14:59:59Z",
             "canceled": False},
            {"size": 1, "ticker": "SPCX", "price": "1.0", "canceled": True},
        ]
        rows, dropped = flow_writer.map_darkpool_rows(trades)
        self.assertEqual(len(rows), 1)
        self.assertEqual(dropped, 1)
        self.assertEqual(rows[0]["seq"], 9599305906444)
        self.assertEqual(rows[0]["venue"], "L")
        self.assertEqual(rows[0]["source"], "phx_flow_dark_pool")


class FakeDb:
    def __init__(self):
        self.batches = []

    async def executemany(self, query, args_seq):
        self.batches.append((query, list(args_seq)))


class FakePool:
    """asyncpg pool boundary fake — proves Database.executemany passes the row
    sequence as ONE argument (regression: a splat broke the first shadow run)."""

    def __init__(self):
        self.seen = []

    async def executemany(self, query, args_seq):
        self.seen.append((query, args_seq))
        return "OK"


def _async_factory(pool):
    async def factory(*args, **kwargs):
        return pool

    return factory


class DatabaseExecutemanyTest(unittest.TestCase):
    def test_row_sequence_passed_as_one_argument(self):
        import asyncio

        from backend.core.db import Database

        pool = FakePool()
        db = Database("postgresql://user:***@host/db", pool_factory=_async_factory(pool))
        rows = [("SPY", 1), ("QQQ", 2)]

        async def run():
            await db.connect()
            return await db.executemany("INSERT INTO t VALUES ($1, $2)", rows)

        asyncio.run(run())
        self.assertEqual(pool.seen, [("INSERT INTO t VALUES ($1, $2)", rows)])


class UpsertTest(unittest.TestCase):
    def test_upsert_sql_conflict_keys(self):
        sql = upsert_sql("gamma_snapshot", ["ticker", "expiry", "strike", "ts", "spot"],
                         ["ticker", "expiry", "strike", "ts"])
        self.assertIn("INSERT INTO gamma_snapshot", sql)
        self.assertIn(
            "ON CONFLICT (ticker, expiry, strike, ts) DO UPDATE SET spot = EXCLUDED.spot",
            sql,
        )

    def test_unsafe_identifiers_rejected(self):
        with self.assertRaises(QueryError):
            upsert_sql("gamma_snapshot; DROP TABLE x", ["ticker"], ["ticker"])
        with self.assertRaises(QueryError):
            upsert_sql("gamma_snapshot", ["ticker", "ts; --"], ["ticker"])

    def test_chunked_batches(self):
        import asyncio

        db = FakeDb()
        rows = [{"ticker": "SPY", "ts": TS, "seq": 0, "price": 1.0, "size": None,
                 "source": "t"} for _ in range(1200)]
        written = asyncio.run(upsert_rows(db, "spot_tick", rows, ("ticker", "ts", "seq")))
        self.assertEqual(written, 1200)
        self.assertEqual([len(b[1]) for b in db.batches], [500, 500, 200])

    def test_write_rows_is_idempotent_on_retry(self):
        import asyncio

        db = FakeDb()
        rows = spot_writer.map_spot_rows("SPY", SpotWriterTest.PAYLOAD)
        asyncio.run(write_rows(db, "spot_tick", rows))
        asyncio.run(write_rows(db, "spot_tick", rows))  # retry of the same batch
        self.assertEqual(len(db.batches), 2)
        # identical SQL and args both times — the ON CONFLICT upsert makes the
        # rerun a no-op at the row level.
        self.assertEqual(db.batches[0][0], db.batches[1][0])
        self.assertEqual(db.batches[0][1], db.batches[1][1])
        self.assertIn("ON CONFLICT (ticker, ts, seq)", db.batches[0][0])

    def test_mixed_shapes_rejected(self):
        import asyncio

        db = FakeDb()
        rows = [{"ticker": "SPY"}, {"ticker": "SPY", "extra": 1}]
        with self.assertRaises(QueryError):
            asyncio.run(write_rows(db, "spot_tick", rows))

    def test_conflict_keys_match_migration_pks(self):
        self.assertEqual(CONFLICT_KEYS["gamma_snapshot"], ("ticker", "expiry", "strike", "ts"))
        self.assertEqual(CONFLICT_KEYS["spot_tick"], ("ticker", "ts", "seq"))
        self.assertEqual(CONFLICT_KEYS["flow_print"], ("occ", "ts", "seq"))
        self.assertEqual(CONFLICT_KEYS["darkpool_print"], ("ticker", "ts", "seq"))


if __name__ == "__main__":
    unittest.main()
