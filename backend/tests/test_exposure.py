"""Unit tests for backend/core/exposure.py (card E0.3).

Vectors per spec §8.5: V = sum_e C + king = argmax|V| on a synthetic 2-expiry
grid; psi on a hand-computed feature row; EWMA recursion one step; edge cases
§6 (zero column, missing batch gap, sign fallback, stale rows, UW-only
expiries, strike matching by value, scale invariance).

Pure in-memory fixtures only — no transports, no file writes, no network.
"""
from __future__ import annotations

import math
import os
import sys
import unittest
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from backend.core import exposure as exp  # noqa: E402


# --------------------------------------------------------------- fixtures

def psi_rows():
    """Hand-computed feature-row fixture (2 rows, one expiry)."""
    return [
        {"strike": 100, "expiry_date": "2026-10-15", "call_gex": 10, "put_gex": 4,
         "call_oi": 50, "put_oi": 20, "call_ask_vol": 8, "call_bid_vol": 3,
         "put_ask_vol": 2, "put_bid_vol": 1, "call_prev_oi": 45, "put_prev_oi": 25},
        {"strike": 110, "expiry_date": "2026-10-15", "call_gex": 2, "put_gex": 7,
         "call_oi": 30, "put_oi": 10, "call_ask_vol": 1, "call_bid_vol": 4,
         "put_ask_vol": 3, "put_bid_vol": 2, "call_prev_oi": 30, "put_prev_oi": 12},
    ]


def grid_rows():
    """Synthetic 2-expiry grid: strikes 100/110 x expiries 2026-10-15/2026-11-20."""
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


# Hand-computed values for the psi fixture (arithmetic in the test vector
# script, independent of the module under test):
#   g(100)=6, g(110)=-5 -> G=11, net_col=1, ask=14, bid=10, doi=-2
#   COM = (6*100 + 5*110)/11 = 1150/11 -> com_dist = 1/231
#   tod = 29/48, dte = 15
X_LOG_DTE = 2.70805020110221          # log(15)
X_LOG_GMAG = 2.4849066497880004       # log(12)
X_NET_COL_SIGN_LOG = 0.6931471805599453   # log(2)
X_IMB = 0.16                          # (14-10)/(14+10+1)
X_DOI = -1.0986122886681098           # -log(3)
X_COM_DIST = 0.004329004329004317     # 1/231
X_TOD = 0.6041666666666666            # 29/48
# E0.5b magnitude temper (spec 12): psi = exp(MAG_GAMMA * theta.[1,x]) with
# MAG_GAMMA = 0.7. Raw (gamma = 1.0) legacy value kept for the identity test:
PSI_RAW_GAMMA1 = 1658622864.7173474   # exp(theta . [1, x]) on the row above
PSI_EXPECTED = 2843304.37699525       # PSI_RAW_GAMMA1 ** 0.7
EWMA_EXPECTED = 597095.4991690024     # 0.79 * 2.0 + 0.21 * PSI_EXPECTED


class TestPsiFeatureRow(unittest.TestCase):
    def test_feature_row_hand_computed(self):
        x = exp.expiry_features(psi_batch(), "2026-10-15")
        expected = [X_LOG_DTE, X_LOG_GMAG, X_NET_COL_SIGN_LOG, X_IMB,
                    X_DOI, X_COM_DIST, X_TOD]
        for got, want, name in zip(x, expected, exp.FEATURE_ORDER):
            self.assertTrue(math.isclose(got, want, rel_tol=1e-12, abs_tol=1e-12),
                            f"{name}: got {got!r} want {want!r}")

    def test_psi_value_and_sign(self):
        psi = exp.psi_weights(psi_batch())
        self.assertIn("2026-10-15", psi)
        self.assertTrue(math.isclose(psi["2026-10-15"], PSI_EXPECTED,
                                     rel_tol=1e-9), psi)
        self.assertGreater(psi["2026-10-15"], 0)  # net_col > 0 -> sgn +1

    def test_sign_fallback_matches_net_col(self):
        # spec §6.4: sgn(a_e) = sgn(sum_s g) — flip to net_col < 0
        rows = [{"strike": 100, "expiry_date": "2026-10-15", "call_gex": 2, "put_gex": 10},
                {"strike": 110, "expiry_date": "2026-10-15", "call_gex": 1, "put_gex": 7}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        psi = exp.psi_weights(batch)
        self.assertLess(psi["2026-10-15"], 0)

    def test_uw_only_expiry_extrapolates(self):
        # spec §6.1: expiry with no fit counterpart still gets a psi weight
        rows = [{"strike": 100, "expiry_date": "2031-12-19", "call_gex": 10, "put_gex": 4}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        psi = exp.psi_weights(batch)
        self.assertTrue(math.isfinite(psi["2031-12-19"]))
        self.assertNotEqual(psi["2031-12-19"], 0.0)


class TestEwmaRecursion(unittest.TestCase):
    def test_one_step(self):
        state = {"2026-10-15": 2.0}
        w = exp.cross_expiry_weights(psi_batch(prev_ts="2026-09-30T14:25:00+00:00"), state)
        self.assertTrue(math.isclose(w["2026-10-15"], EWMA_EXPECTED, rel_tol=1e-9), w)

    def test_cold_start_equals_psi(self):
        w = exp.cross_expiry_weights(psi_batch(prev_ts="2026-09-30T14:25:00+00:00"), {})
        self.assertTrue(math.isclose(w["2026-10-15"], PSI_EXPECTED, rel_tol=1e-9), w)

    def test_gap_beyond_interval_resets_to_psi(self):
        # spec §6.3: gap > one batch interval (~480 s) -> stale state, reset
        state = {"2026-10-15": 2.0}
        w = exp.cross_expiry_weights(psi_batch(prev_ts="2026-09-30T14:21:40+00:00"), state)
        self.assertTrue(math.isclose(w["2026-10-15"], PSI_EXPECTED, rel_tol=1e-9), w)

    def test_gap_within_interval_uses_state(self):
        state = {"2026-10-15": 2.0}
        w = exp.cross_expiry_weights(psi_batch(prev_ts="2026-09-30T14:25:00+00:00"), state)
        self.assertFalse(math.isclose(w["2026-10-15"], PSI_EXPECTED, rel_tol=1e-9))

    def test_missing_prev_ts_treats_state_fresh(self):
        state = {"2026-10-15": 2.0}
        w = exp.cross_expiry_weights(psi_batch(), state)
        self.assertTrue(math.isclose(w["2026-10-15"], EWMA_EXPECTED, rel_tol=1e-9), w)

    def test_zero_column_zero_weight(self):
        # spec §6.2: G_e == 0 -> a_e = 0 exactly, regardless of psi AND state
        rows = [{"strike": 100, "expiry_date": "2026-10-15", "call_gex": 0, "put_gex": 0,
                 "call_oi": 50, "put_oi": 20}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        w = exp.cross_expiry_weights(batch, {})
        self.assertEqual(w["2026-10-15"], 0.0)
        w2 = exp.cross_expiry_weights(batch, {"2026-10-15": 2.0})
        self.assertEqual(w2["2026-10-15"], 0.0)

    def test_state_not_mutated(self):
        state = {"2026-10-15": 2.0}
        exp.cross_expiry_weights(psi_batch(), state)
        self.assertEqual(state, {"2026-10-15": 2.0})


class TestNodeMath(unittest.TestCase):
    def setUp(self):
        self.batch = exp.normalize_batch(
            grid_rows(), ts="2026-09-30T14:30:00+00:00", spot=105.0)
        self.weights = {"2026-10-15": 1.5, "2026-11-20": -2.0}

    def test_node_values_sum_over_expiries(self):
        # p = 1.0 = established g basis (E0.6 backward-compat switch, spec §5b)
        v = exp.node_values(self.batch, self.weights, p=1.0)
        # V(100) = 1.5*6 + (-2.0)*2 = 5.0 ; V(110) = 1.5*(-5) + (-2.0)*(-3) = -1.5
        self.assertEqual(v[100], 5.0)
        self.assertEqual(v[110], -1.5)

    def test_cells_and_v_consistency(self):
        cells = exp.cell_values(self.batch, self.weights, p=1.0)
        self.assertEqual(cells[(100.0, "2026-10-15")], 9.0)
        self.assertEqual(cells[(110.0, "2026-10-15")], -7.5)
        self.assertEqual(cells[(100.0, "2026-11-20")], -4.0)
        self.assertEqual(cells[(110.0, "2026-11-20")], 6.0)
        v = exp.node_values(self.batch, self.weights, p=1.0)
        for s in (100.0, 110.0):
            self.assertEqual(v[s], sum(c for (st, _e), c in cells.items() if st == s))

    def test_king_argmax_abs(self):
        v = exp.node_values(self.batch, self.weights)
        sel = exp.select_nodes(v)
        self.assertEqual(sel["king"], 100)
        self.assertEqual(sel["top6"], [100, 110])

    def test_star_argmax_cells(self):
        cells = exp.cell_values(self.batch, self.weights)
        v = exp.node_values(self.batch, self.weights)
        sel = exp.select_nodes(v, cells)
        self.assertEqual(sel["stars"]["2026-10-15"], 100)   # |9| > |-7.5|
        self.assertEqual(sel["stars"]["2026-11-20"], 110)   # |6| > |-4|
        self.assertEqual(sel["global_star"]["strike"], 100)
        self.assertEqual(sel["global_star"]["expiry"], "2026-10-15")

    def test_strike_matching_by_value(self):
        # spec §6.7: strikes match by value, never positionally
        rows = list(reversed(grid_rows()))
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        v = exp.node_values(batch, self.weights, p=1.0)
        self.assertEqual(v[100], 5.0)
        self.assertEqual(v[110], -1.5)

    def test_positive_rescale_keeps_selection(self):
        k = 37.5
        v = exp.node_values(self.batch, self.weights)
        cells = exp.cell_values(self.batch, self.weights)
        sel0 = exp.select_nodes(v, cells)
        sel1 = exp.select_nodes({s: k * x for s, x in v.items()},
                                {c: k * x for c, x in cells.items()})
        for key in ("king", "top6", "stars"):
            self.assertEqual(sel0[key], sel1[key])
        self.assertEqual(sel0["global_star"]["strike"], sel1["global_star"]["strike"])
        self.assertEqual(sel0["global_star"]["expiry"], sel1["global_star"]["expiry"])

    def test_display_weights_normalized(self):
        w = exp.display_weights(self.weights)  # {E1: 1.5, E2: -2.0}
        e = len(w)
        self.assertTrue(math.isclose(sum(abs(x) for x in w.values()) / e, 1.0))
        self.assertTrue(math.isclose(w["2026-11-20"] / w["2026-10-15"], -2.0 / 1.5))


class TestShapeTransform(unittest.TestCase):
    """E0.6 within-cell power basis (spec §5b, MAG_SHAPE_P = 1.25).

    Hand-computed vectors on grid_rows (independent arithmetic):
        e1 col: g = {100: 6, 110: -5}, m = 6
            h = {100: 6*(6/6)^1.25 = 6.0, 110: -6*(5/6)^1.25 = -4.777213961021834}
        e2 col: g = {100: 2, 110: -3}, m = 3
            h = {100: 3*(2/3)^1.25 = 1.8072040072196895, 110: -3*(3/3)^1.25 = -3.0}
        C = a_e * h with a = {e1: 1.5, e2: -2.0}; V = sum_e C.
    """

    def setUp(self):
        self.batch = exp.normalize_batch(
            grid_rows(), ts="2026-09-30T14:30:00+00:00", spot=105.0)
        self.weights = {"2026-10-15": 1.5, "2026-11-20": -2.0}

    def test_constant(self):
        self.assertEqual(exp.MAG_SHAPE_P, 1.25)

    def test_p1_reduces_exactly_to_g_basis(self):
        # acceptance: p = 1 is the current g basis, bit-for-bit
        g_cells = {(100.0, "2026-10-15"): 6.0, (110.0, "2026-10-15"): -5.0,
                   (100.0, "2026-11-20"): 2.0, (110.0, "2026-11-20"): -3.0}
        self.assertEqual(exp.cell_basis(self.batch, p=1.0), g_cells)
        self.assertEqual(
            exp.cell_values(self.batch, self.weights, p=1.0),
            {k: self.weights[k[1]] * g for k, g in g_cells.items()})
        self.assertEqual(
            exp.node_values(self.batch, self.weights, p=1.0),
            {100.0: 1.5 * 6.0 + (-2.0) * 2.0,
             110.0: 1.5 * (-5.0) + (-2.0) * (-3.0)})
        # the transform itself: exact early return for any input
        for g, m in ((6.0, 6.0), (-5.0, 6.0), (0.0, 0.0), (3.25, 7.5)):
            self.assertEqual(exp.shape_transform(g, m, p=1.0), g)

    def test_hand_computed_p125(self):
        h = exp.cell_basis(self.batch)  # default MAG_SHAPE_P = 1.25
        self.assertTrue(math.isclose(h[(100.0, "2026-10-15")], 6.0, rel_tol=1e-12), h)
        self.assertTrue(math.isclose(h[(110.0, "2026-10-15")], -4.777213961021834,
                                     rel_tol=1e-12), h)
        self.assertTrue(math.isclose(h[(100.0, "2026-11-20")], 1.8072040072196895,
                                     rel_tol=1e-12), h)
        self.assertTrue(math.isclose(h[(110.0, "2026-11-20")], -3.0, rel_tol=1e-12), h)
        c = exp.cell_values(self.batch, self.weights)  # C = a_e * h
        self.assertTrue(math.isclose(c[(100.0, "2026-10-15")], 9.0, rel_tol=1e-12), c)
        self.assertTrue(math.isclose(c[(110.0, "2026-10-15")], -7.165820941532751,
                                     rel_tol=1e-12), c)
        self.assertTrue(math.isclose(c[(100.0, "2026-11-20")], -3.614408014439379,
                                     rel_tol=1e-12), c)
        self.assertTrue(math.isclose(c[(110.0, "2026-11-20")], 6.0, rel_tol=1e-12), c)
        v = exp.node_values(self.batch, self.weights)  # V = sum_e C
        self.assertTrue(math.isclose(v[100.0], 5.385591985560621, rel_tol=1e-12), v)
        self.assertTrue(math.isclose(v[110.0], -1.1658209415327514, rel_tol=1e-12), v)
        for s in (100.0, 110.0):
            self.assertTrue(math.isclose(
                v[s], sum(val for (st, _e), val in c.items() if st == s),
                rel_tol=1e-12), (s, v))

    def test_zero_safe(self):
        # spec §5b edge case: m_e = 0 (all g zero in the column) -> h = 0
        rows = [{"strike": 100, "expiry_date": "2026-10-15", "call_gex": 0, "put_gex": 0},
                {"strike": 110, "expiry_date": "2026-10-15", "call_gex": 3, "put_gex": 3}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        h = exp.cell_basis(batch)
        self.assertEqual(h[(100.0, "2026-10-15")], 0.0)
        self.assertEqual(h[(110.0, "2026-10-15")], 0.0)
        self.assertEqual(exp.shape_transform(0.0, 0.0), 0.0)
        self.assertEqual(exp.shape_transform(5.0, 0.0), 0.0)  # m = 0 -> h = 0
        self.assertEqual(exp.shape_column({100.0: 0.0}), {100.0: 0.0})
        v = exp.node_values(batch, {"2026-10-15": 2.0})
        self.assertEqual(v, {100.0: 0.0, 110.0: 0.0})

    def test_sign_and_column_magnitude(self):
        # spec §6.4 sign preserved exactly; max|h| == m_e (g-scale magnitudes)
        cols = {"e1": {100.0: 6.0, 110.0: -5.0}, "e2": {100.0: 2.0, 110.0: -3.0}}
        for name, col in cols.items():
            hh = exp.shape_column(col)
            sgn = lambda x: (1.0 if x > 0 else (-1.0 if x < 0 else 0.0))  # noqa: E731
            self.assertEqual({s: sgn(x) for s, x in hh.items()},
                             {s: sgn(x) for s, x in col.items()}, name)
            self.assertEqual(max(abs(x) for x in hh.values()),
                             max(abs(x) for x in col.values()), name)
        # single-cell column: |g| == m_e -> h == g exactly
        self.assertEqual(exp.shape_column({100.0: -3.5}), {100.0: -3.5})

    def test_selection_unchanged_on_fixture(self):
        # king/star selection on the p = 1.25 basis (same as g on this fixture)
        v = exp.node_values(self.batch, self.weights)
        c = exp.cell_values(self.batch, self.weights)
        sel = exp.select_nodes(v, c)
        self.assertEqual(sel["king"], 100)
        self.assertEqual(sel["stars"], {"2026-10-15": 100, "2026-11-20": 110})
        self.assertEqual(sel["global_star"], {"strike": 100, "expiry": "2026-10-15",
                                              "value": 9.0})


class TestBatchHygiene(unittest.TestCase):
    def test_stale_row_dropped(self):
        # spec §6.5: fetched_at deviating > one batch interval -> dropped
        rows = psi_rows() + [
            {"strike": 120, "expiry_date": "2026-10-15", "call_gex": 1, "put_gex": 0,
             "fetched_at": "2026-09-30T14:13:20+00:00"}]  # 1000 s before ts
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        self.assertEqual(batch["n_rows"], 2)
        self.assertEqual(batch["dropped_stale_rows"], 1)
        v = exp.node_values(batch, {"2026-10-15": 1.0})
        self.assertNotIn(120, v)

    def test_fresh_fetched_at_kept(self):
        rows = [{"strike": 100, "expiry_date": "2026-10-15", "call_gex": 1, "put_gex": 0,
                 "fetched_at": "2026-09-30T14:29:00+00:00"}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        self.assertEqual(batch["n_rows"], 1)
        self.assertEqual(batch["dropped_stale_rows"], 0)

    def test_spot_median_from_rows(self):
        rows = [{"strike": s, "expiry_date": "2026-10-15", "call_gex": 1,
                 "put_gex": 0, "spot_price": sp}
                for s, sp in ((100, 100.0), (110, 105.0), (120, 110.0))]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00")
        self.assertEqual(batch["spot"], 105.0)

    def test_missing_strike_or_expiry_dropped(self):
        rows = [{"expiry_date": "2026-10-15", "call_gex": 1},
                {"strike": 100, "call_gex": 1},
                {"strike": 100, "expiry_date": "2026-10-15", "call_gex": 1}]
        batch = exp.normalize_batch(rows, ts="2026-09-30T14:30:00+00:00", spot=105.0)
        self.assertEqual(batch["n_rows"], 1)
        self.assertEqual(batch["dropped_stale_rows"], 2)


class TestTsParsing(unittest.TestCase):
    def test_formats(self):
        want = datetime(2026, 9, 30, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(exp.parse_ts("2026-09-30T14:30:00Z"), want)
        self.assertEqual(exp.parse_ts("2026-09-30T14:30:00+00:00"), want)
        self.assertEqual(exp.parse_ts("2026-09-30T14:30:00"), want)  # naive -> UTC
        self.assertEqual(exp.parse_ts(want), want)
        self.assertEqual(exp.parse_ts(want.timestamp()), want)


if __name__ == "__main__":
    unittest.main()
