"""Unit tests for the E0.5b psi magnitude temper (card E0.5b, spec 12).

MAG_GAMMA = 0.7 compresses the psi log-magnitude: |psi| = exp(gamma * dot),
i.e. |psi| -> |psi|^gamma; gamma = 1.0 reproduces the pre-E0.5b model exactly
(the legacy E0.3 vector PSI_RAW_GAMMA1 is asserted below). The sign convention
(spec 6.4) is unchanged, and the value path for explicit weights is untouched
(V = sum_e a_e * g with the caller's weights as given).

Hand-computed vectors: psi on the E0.3 fixture row (reused numbers, tempered),
EWMA one step on tempered psi, gamma identity, sign preservation, spread
compression ratio^gamma, zero-column edge case (spec 6.2).

Pure in-memory fixtures only — no transports, no file writes, no network.
"""
from __future__ import annotations

import math
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from backend.core import exposure as exp  # noqa: E402


def psi_rows():
    """Same hand-computed fixture as test_exposure.psi_rows (2 rows, 1 expiry)."""
    return [
        {"strike": 100, "expiry_date": "2026-10-15", "call_gex": 10, "put_gex": 4,
         "call_oi": 50, "put_oi": 20, "call_ask_vol": 8, "call_bid_vol": 3,
         "put_ask_vol": 2, "put_bid_vol": 1, "call_prev_oi": 45, "put_prev_oi": 25},
        {"strike": 110, "expiry_date": "2026-10-15", "call_gex": 2, "put_gex": 7,
         "call_oi": 30, "put_oi": 10, "call_ask_vol": 1, "call_bid_vol": 4,
         "put_ask_vol": 3, "put_bid_vol": 2, "call_prev_oi": 30, "put_prev_oi": 12},
    ]


def grid_rows():
    """Same synthetic 2-expiry grid as test_exposure.grid_rows."""
    return [
        {"strike": 100, "expiry_date": "2026-10-15", "call_gex": 10, "put_gex": 4},
        {"strike": 110, "expiry_date": "2026-10-15", "call_gex": 2, "put_gex": 7},
        {"strike": 100, "expiry_date": "2026-11-20", "call_gex": 3, "put_gex": 1},
        {"strike": 110, "expiry_date": "2026-11-20", "call_gex": 1, "put_gex": 4},
    ]


def psi_batch(**kw):
    kw.setdefault("ts", "2026-09-30T14:30:00+00:00")
    kw.setdefault("spot", 105.0)
    return exp.normalize_batch(psi_rows(), **kw)


# Hand-computed (arithmetic in the test vector script, independent of the
# module under test):
PSI_RAW_GAMMA1 = 1658622864.7173474    # exp(theta . [1, x]) (E0.3 vector)
PSI_EXPECTED_07 = 2843304.37699525     # PSI_RAW_GAMMA1 ** 0.7
EWMA_EXPECTED_07 = 597095.4991690024   # 0.79 * 2.0 + 0.21 * PSI_EXPECTED_07


class TestMagGamma(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(exp.MAG_GAMMA, 0.7)

    def test_gamma1_identity_matches_legacy_vector(self):
        psi = exp.psi_weights(psi_batch(), gamma=1.0)
        self.assertTrue(math.isclose(psi["2026-10-15"], PSI_RAW_GAMMA1, rel_tol=1e-9), psi)

    def test_default_gamma_tempered(self):
        psi = exp.psi_weights(psi_batch())
        self.assertTrue(math.isclose(psi["2026-10-15"], PSI_EXPECTED_07, rel_tol=1e-9), psi)

    def test_temper_is_raw_power(self):
        # |psi_gamma| == |psi_1| ** gamma for any gamma (magnitude model)
        for g in (0.3, 0.5, 0.7, 1.0):
            p1 = exp.psi_weights(psi_batch(), gamma=1.0)["2026-10-15"]
            pg = exp.psi_weights(psi_batch(), gamma=g)["2026-10-15"]
            self.assertTrue(math.isclose(pg, p1 ** g, rel_tol=1e-9), (g, pg, p1 ** g))

    def test_sign_preserved_under_temper(self):
        # net_col < 0 fixture: sign stays negative for every gamma
        rows = [{"strike": 100, "expiry_date": "2026-10-15", "call_gex": 2, "put_gex": 10},
                {"strike": 110, "expiry_date": "2026-10-15", "call_gex": 1, "put_gex": 7}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        for g in (0.7, 1.0):
            self.assertLess(exp.psi_weights(batch, gamma=g)["2026-10-15"], 0)

    def test_spread_compression(self):
        # relative magnitude ratio between expiries compresses as ratio**gamma
        rows = [
            {"strike": 100, "expiry_date": "2026-10-15", "call_gex": 10, "put_gex": 4,
             "call_oi": 50, "put_oi": 20, "call_ask_vol": 8, "call_bid_vol": 3,
             "put_ask_vol": 2, "put_bid_vol": 1, "call_prev_oi": 45, "put_prev_oi": 25},
            {"strike": 100, "expiry_date": "2026-11-20", "call_gex": 3, "put_gex": 1,
             "call_oi": 5, "put_oi": 2, "call_ask_vol": 1, "call_bid_vol": 1,
             "put_ask_vol": 1, "put_bid_vol": 1, "call_prev_oi": 5, "put_prev_oi": 2},
        ]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        p1 = exp.psi_weights(batch, gamma=1.0)
        pg = exp.psi_weights(batch, gamma=0.7)
        r1 = abs(p1["2026-10-15"] / p1["2026-11-20"])
        rg = abs(pg["2026-10-15"] / pg["2026-11-20"])
        self.assertTrue(math.isclose(rg, r1 ** 0.7, rel_tol=1e-9), (r1, rg))
        # spread = max/min ratio across the two expiries actually compresses
        spread1, spread_g = max(r1, 1 / r1), max(rg, 1 / rg)
        self.assertLess(spread_g, spread1)

    def test_zero_column_still_zero(self):
        # spec 6.2 edge case survives the temper
        rows = [{"strike": 100, "expiry_date": "2026-10-15", "call_gex": 0, "put_gex": 0,
                 "call_oi": 50, "put_oi": 20}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        self.assertEqual(exp.psi_weights(batch)["2026-10-15"], 0.0)
        w = exp.cross_expiry_weights(batch, {"2026-10-15": 2.0})
        self.assertEqual(w["2026-10-15"], 0.0)

    def test_ewma_one_step_on_tempered_psi(self):
        state = {"2026-10-15": 2.0}
        w = exp.cross_expiry_weights(psi_batch(prev_ts="2026-09-30T14:25:00+00:00"), state)
        self.assertTrue(math.isclose(w["2026-10-15"], EWMA_EXPECTED_07, rel_tol=1e-9), w)

    def test_value_path_untouched_for_explicit_weights(self):
        # the temper lives in the psi layer only: V = sum_e a_e * g with the
        # caller's weights as given (E0.3 hand vector preserved; p = 1.0 pins
        # the g basis -- the E0.6 shape transform is tested in test_exposure)
        batch = exp.normalize_batch(grid_rows(), ts="2026-09-30T14:30:00+00:00", spot=105.0)
        v = exp.node_values(batch, {"2026-10-15": 1.5, "2026-11-20": -2.0}, p=1.0)
        self.assertEqual(v[100], 5.0)
        self.assertEqual(v[110], -1.5)


if __name__ == "__main__":
    unittest.main()
