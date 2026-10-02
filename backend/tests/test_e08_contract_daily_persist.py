"""Unit tests for scripts/e08_contract_daily_persist.py row mapping/aggregation.

Covers the ContractStats/UnderlyingStats shape mapping (db/migrations/0002), the
OCC normalization, right=C/P mapping, oi_change derivation, and the call/put
underlying rollup. No network.
"""
from __future__ import annotations

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from scripts.e08_contract_daily_persist import (  # noqa: E402
    aggregate_underlying, map_contract_row,
)

ROW = {
    "option_symbol": "SPY 261016C00580000",
    "underlying_symbol": "SPY",
    "option_type": "call",
    "strike": "580",
    "expires": "2026-10-16",
    "volume": 1234,
    "avg_price": "2.5",
    "open_interest": 900,
    "prev_oi": 400,
    "bid_volume": 100,
    "ask_volume": 200,
    "mid_volume": 50,
    "last_price": "2.6",
    "iv": 0.31,
    "last_tape_time": "2026-10-01T19:59:00Z",
}


class MapContractRowTest(unittest.TestCase):
    def test_shape(self):
        r = map_contract_row(ROW, "2026-10-01")
        self.assertEqual(r["occ"], "SPY261016C00580000")  # space stripped
        self.assertEqual(r["right"], "C")
        self.assertEqual(r["date"], "2026-10-01")
        self.assertEqual(r["expiration"], "2026-10-16")
        self.assertEqual(r["dte"], 15)
        self.assertEqual(r["total_volume"], 1234)
        self.assertEqual(r["total_premium"], 2.5 * 1234 * 100.0)
        self.assertEqual(r["oi_change"], 500)
        self.assertEqual(r["open_interest"], 900)
        self.assertEqual(r["prev_oi"], 400)
        self.assertEqual(r["bid_volume"], 100)
        self.assertEqual(r["ask_volume"], 200)
        self.assertEqual(r["mid_volume"], 50)
        self.assertEqual(r["vwap"], 2.5)
        self.assertEqual(r["source"], "phx_chains_expiry")
        # honest NULLs for fields PHX does not serve
        for k in ("sweep_volume", "sweep_premium", "multi_leg_volume",
                  "multi_leg_premium", "trade_count"):
            self.assertIsNone(r[k])

    def test_put_and_double_underscore_occ(self):
        row = dict(ROW, option_symbol="SPY__261016P00580000", option_type="put")
        r = map_contract_row(row, "2026-10-01")
        self.assertEqual(r["occ"], "SPY261016P00580000")
        self.assertEqual(r["right"], "P")

    def test_zero_avg_price_is_none(self):
        row = dict(ROW, avg_price="0")
        r = map_contract_row(row, "2026-10-01")
        self.assertIsNone(r["vwap"])
        self.assertEqual(r["total_premium"], 0.0)


class AggregateUnderlyingTest(unittest.TestCase):
    def test_rollup(self):
        call = map_contract_row(ROW, "2026-10-01")
        put = map_contract_row(dict(ROW, option_type="put",
                                    option_symbol="SPY261016P00580000",
                                    volume=600, avg_price="1.0"), "2026-10-01")
        u = aggregate_underlying("SPY", "2026-10-01", [call, put], spot=581.5)
        self.assertEqual(u["ticker"], "SPY")
        self.assertEqual(u["call_volume"], 1234)
        self.assertEqual(u["put_volume"], 600)
        self.assertEqual(u["total_volume"], 1834)
        self.assertAlmostEqual(u["call_premium"], 2.5 * 1234 * 100.0)
        self.assertAlmostEqual(u["put_premium"], 1.0 * 600 * 100.0)
        self.assertAlmostEqual(u["net_premium"], u["call_premium"] - u["put_premium"])
        self.assertEqual(u["unique_strikes"], 1)
        self.assertEqual(u["unique_expirations"], 1)
        self.assertEqual(u["last_price"], 581.5)


if __name__ == "__main__":
    unittest.main()
