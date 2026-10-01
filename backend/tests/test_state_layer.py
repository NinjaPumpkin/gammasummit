"""Unit tests for the §10 cell-level dynamic state layer (card E0.5a).

Vectors per spec §10.5 / acceptance: one literal state step (hand-computed),
recursion invariants, and edge cases from §6 mapped onto the state layer.
Pure in-memory fixtures — no transports, no file writes, no network.
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

E1 = "2026-10-15"
TS1 = "2026-09-30T14:30:00+00:00"
TS2 = "2026-09-30T14:34:01+00:00"     # exactly +241 s = one MEDIAN_CADENCE_S
TS3 = "2026-09-30T15:30:00+00:00"


def rows1():
    """Batch 1: g(100)=6, g(110)=-5; f(100)=0, f(110)=-2."""
    return [
        {"strike": 100, "expiry_date": E1, "call_gex": 10, "put_gex": 4,
         "call_oi": 50, "put_oi": 20, "call_prev_oi": 45, "put_prev_oi": 25},
        {"strike": 110, "expiry_date": E1, "call_gex": 2, "put_gex": 7,
         "call_oi": 30, "put_oi": 10, "call_prev_oi": 30, "put_prev_oi": 12},
    ]


def rows2():
    """Batch 2: g(100)=-6, g(110)=-5; f(100)=5, f(110)=-2."""
    return [
        {"strike": 100, "expiry_date": E1, "call_gex": 4, "put_gex": 10,
         "call_oi": 55, "put_oi": 15, "call_prev_oi": 45, "put_prev_oi": 20},
        {"strike": 110, "expiry_date": E1, "call_gex": 2, "put_gex": 7,
         "call_oi": 30, "put_oi": 10, "call_prev_oi": 30, "put_prev_oi": 12},
    ]


def batch(rows, ts, spot=105.0, **kw):
    return exp.normalize_batch(rows, ts=ts, spot=spot, **kw)


# Hand-computed state step (spec §10.2.1), dt = 241 s -> lam_k = lam = 0.79:
#   first batch initializes q = obs:  q_g(100)=6, q_f(100)=0, q_g(110)=-5, q_f(110)=-2
#   second batch: q_g(100) = 0.79*6   + 0.21*(-6) = 3.48
#                 q_f(100) = 0.79*0   + 0.21*5   = 1.05
#                 q_g(110) = 0.79*(-5)+ 0.21*(-5)= -5.0   (constant obs fixed point)
Q_G100 = 3.48
Q_F100 = 1.05
Q_G110 = -5.0


class TestLiteralStateStep(unittest.TestCase):
    def test_first_observation_initializes(self):
        st = exp.update_cell_state(batch(rows1(), TS1), exp.new_cell_state(), lam=0.79)
        self.assertEqual(st["q_g"][(100.0, E1)], 6.0)
        self.assertEqual(st["q_f"][(100.0, E1)], 0.0)
        self.assertEqual(st["q_g"][(110.0, E1)], -5.0)
        self.assertEqual(st["q_f"][(110.0, E1)], -2.0)

    def test_one_step_hand_computed(self):
        st = exp.update_cell_state(batch(rows1(), TS1), exp.new_cell_state(), lam=0.79)
        st = exp.update_cell_state(batch(rows2(), TS2), st, lam=0.79)
        self.assertTrue(math.isclose(st["q_g"][(100.0, E1)], Q_G100, rel_tol=1e-12),
                        st["q_g"])
        self.assertTrue(math.isclose(st["q_f"][(100.0, E1)], Q_F100, rel_tol=1e-12),
                        st["q_f"])
        self.assertTrue(math.isclose(st["q_g"][(110.0, E1)], Q_G110, rel_tol=1e-12),
                        st["q_g"])

    def test_stateful_value_hand_computed(self):
        # beta = (1, 2, 0, ...): V(s) = sum_e a_e*(g + 2*q_g), a = 1.5
        st = exp.update_cell_state(batch(rows1(), TS1), exp.new_cell_state(), lam=0.79)
        st = exp.update_cell_state(batch(rows2(), TS2), st, lam=0.79)
        b = batch(rows2(), TS2)
        v = exp.stateful_node_values(b, {E1: 1.5}, st, beta=(1.0, 2.0, 0.0, 0.0,
                                                            0.0, 0.0, 0.0, 0.0))
        self.assertTrue(math.isclose(v[100.0], 1.5 * (-6.0 + 2 * Q_G100), rel_tol=1e-12), v)
        self.assertTrue(math.isclose(v[110.0], 1.5 * (-5.0 + 2 * Q_G110), rel_tol=1e-12), v)

    def test_node_scores_hand_computed(self):
        # spot path 104 -> 109 over grid {100, 110}: band(100)=band(110)=5
        #   100: in_prev(4<=5) and out_cur and no cross -> reject;  110: touch
        rows = [{"strike": 100, "expiry_date": E1, "call_gex": 1, "put_gex": 0},
                {"strike": 110, "expiry_date": E1, "call_gex": 1, "put_gex": 0}]
        st = exp.update_cell_state(batch(rows, TS1, spot=104.0), exp.new_cell_state())
        st = exp.update_cell_state(batch(rows, TS2, spot=109.0), st)
        d100, r100, t100 = exp.node_state_scores(st, 100.0)
        d110, r110, t110 = exp.node_state_scores(st, 110.0)
        self.assertEqual((d100, r100, t100), (0.0, 1.0, 0.0))   # N_del=0, N_rej=1, N_tch=0
        self.assertTrue(math.isclose(t110, math.log(2.0), rel_tol=1e-12))
        self.assertEqual((d110, r110), (0.0, 0.0))

    def test_deliver_count_hand_computed(self):
        # spot 98 -> 103 crosses 100 (band 5): deliver + touch at 100
        rows = [{"strike": 100, "expiry_date": E1, "call_gex": 1, "put_gex": 0},
                {"strike": 110, "expiry_date": E1, "call_gex": 1, "put_gex": 0}]
        st = exp.update_cell_state(batch(rows, TS1, spot=98.0), exp.new_cell_state())
        st = exp.update_cell_state(batch(rows, TS2, spot=103.0), st)
        d, r, t = exp.node_state_scores(st, 100.0)
        self.assertTrue(math.isclose(d, 0.5, rel_tol=1e-12))    # 1 deliver / (1 touch + 1)
        self.assertEqual(r, 0.0)


class TestRecursionInvariants(unittest.TestCase):
    def test_convex_combination_bound(self):
        # q_k is a convex combination of past observations -> stays in [min, max]
        obs = [6.0, -6.0, 12.0, -20.0, 3.0]
        st = exp.new_cell_state()
        for i, g in enumerate(obs):
            rows = [{"strike": 100, "expiry_date": E1, "call_gex": g, "put_gex": 0.0}]
            ts = f"2026-09-30T14:{30 + i:02d}:00+00:00"
            st = exp.update_cell_state(batch(rows, ts), st)
        q = st["q_g"][(100.0, E1)]
        self.assertGreaterEqual(q, min(obs) - 1e-12)
        self.assertLessEqual(q, max(obs) + 1e-12)

    def test_constant_observation_fixed_point(self):
        st = exp.new_cell_state()
        for i in range(5):
            rows = [{"strike": 100, "expiry_date": E1, "call_gex": 7.0, "put_gex": 1.0}]
            ts = f"2026-09-30T14:{30 + i:02d}:00+00:00"
            st = exp.update_cell_state(batch(rows, ts), st)
        self.assertEqual(st["q_g"][(100.0, E1)], 6.0)

    def test_baseline_reduction_exact(self):
        # beta = (1, 0, ...) -> stateful model == E0.3 g-basis model exactly
        # (property of the model form; the default STATE_BETA is the fitted one.
        # The §10 model stays on the g basis -- E0.6 MAG_SHAPE_P does not apply,
        # so the comparison uses cell_values/node_values with p = 1.0.)
        b0 = (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        st = exp.update_cell_state(batch(rows2(), TS2), exp.new_cell_state())
        b = batch(rows2(), TS2)
        w = {E1: 2.5}
        v0 = exp.node_values(b, w, p=1.0)
        v1 = exp.stateful_node_values(b, w, st, beta=b0)
        for s, x in v0.items():
            self.assertTrue(math.isclose(v1[s], x, rel_tol=1e-12), (s, x, v1[s]))
        c0 = exp.cell_values(b, w, p=1.0)
        c1 = exp.stateful_cell_values(b, w, st, beta=b0)
        for k, x in c0.items():
            self.assertTrue(math.isclose(c1[k], x, rel_tol=1e-12), (k, x, c1[k]))

    def test_cells_sum_to_nodes(self):
        st = exp.update_cell_state(batch(rows1(), TS1), exp.new_cell_state())
        st = exp.update_cell_state(batch(rows2(), TS2), st)
        b = batch(rows2(), TS2)
        w = {E1: 1.5}
        beta = (1.0, 2.0, -0.5, 0.25, 0.75, 0.3, -0.2, 0.1)
        cells = exp.stateful_cell_values(b, w, st, beta=beta)
        v = exp.stateful_node_values(b, w, st, beta=beta)
        for s in v:
            total = sum(c for (sk, _e), c in cells.items() if sk == s)
            self.assertTrue(math.isclose(total, v[s], rel_tol=1e-12), (s, total, v[s]))

    def test_input_state_not_mutated(self):
        st = exp.new_cell_state()
        exp.update_cell_state(batch(rows1(), TS1), st)
        self.assertEqual(st["q_g"], {})


class TestEdgeCases(unittest.TestCase):
    def test_zero_column_node_terms_still_enter(self):
        # spec §10.6.1: a_e = 0 kills the weighted part; node-state terms survive
        rows = [{"strike": 100, "expiry_date": E1, "call_gex": 0, "put_gex": 0,
                 "call_oi": 50, "put_oi": 20}]
        st = exp.new_cell_state()
        st = exp.update_cell_state(batch(rows, TS1, spot=101.0), st)
        st = exp.update_cell_state(batch(rows, TS2, spot=101.0), st)  # touch at 100
        b = batch(rows, TS2, spot=101.0)
        w = exp.cross_expiry_weights(b, {})
        self.assertEqual(w[E1], 0.0)                                   # §6.2
        beta = (1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.5)
        v = exp.stateful_node_values(b, w, st, beta=beta)
        self.assertTrue(math.isclose(v[100.0], 0.5 * math.log(2.0), rel_tol=1e-12), v)

    def test_gap_decays_but_never_resets(self):
        # spec §10.4.2: gap of 3600 s -> q = lam^(3600/241)*q_prev + (1-..)*g,
        # NOT reset to g (contrast §6.3 which resets a_e)
        st = exp.update_cell_state(batch(rows1(), TS1), exp.new_cell_state())
        st = exp.update_cell_state(batch(rows2(), TS3), st)   # 3600 s gap
        lam_k = exp.LAMBDA_CELL ** (3600.0 / exp.MEDIAN_CADENCE_S)
        want = lam_k * 6.0 + (1.0 - lam_k) * (-6.0)
        self.assertTrue(math.isclose(st["q_g"][(100.0, E1)], want, rel_tol=1e-12),
                        st["q_g"])
        self.assertNotEqual(st["q_g"][(100.0, E1)], -6.0)

    def test_stale_rows_never_reach_state(self):
        # spec §10.6.5 / §6.5: stale row dropped before the update
        rows = rows1() + [
            {"strike": 120, "expiry_date": E1, "call_gex": 1, "put_gex": 0,
             "fetched_at": "2026-09-30T14:13:20+00:00"}]
        b = batch(rows, TS1)
        self.assertEqual(b["n_rows"], 2)
        st = exp.update_cell_state(b, exp.new_cell_state())
        self.assertNotIn((120.0, E1), st["q_g"])

    def test_observed_zero_decays_unobserved_holds(self):
        # spec §10.4.3: row present with g=0 is an observation; absent cell holds
        st = exp.update_cell_state(batch(rows1(), TS1), exp.new_cell_state())
        rows_zero = [{"strike": 100, "expiry_date": E1, "call_gex": 0, "put_gex": 0}]
        st = exp.update_cell_state(batch(rows_zero, TS2), st)
        self.assertNotEqual(st["q_g"][(100.0, E1)], 0.0)   # decays toward 0, not snapped
        self.assertLess(abs(st["q_g"][(100.0, E1)]), 6.0)
        self.assertEqual(st["q_g"][(110.0, E1)], -5.0)     # unobserved -> held

    def test_strike_outside_uw_grid_absent(self):
        # spec §10.6.3: no rows -> no state -> V key absent (scored as 0)
        b = batch(rows2(), TS2)
        st = exp.new_cell_state()
        v = exp.stateful_node_values(b, {E1: 1.0}, st)
        self.assertNotIn(200.0, v)

    def test_row_order_invariant(self):
        b1 = batch(rows2(), TS2)
        b2 = batch(list(reversed(rows2())), TS2)
        st = exp.new_cell_state()
        v1 = exp.stateful_node_values(b1, {E1: 1.0}, st)
        v2 = exp.stateful_node_values(b2, {E1: 1.0}, st)
        for s in v1:
            self.assertTrue(math.isclose(v1[s], v2[s], rel_tol=1e-12))

    def test_positive_rescale_keeps_selection(self):
        st = exp.update_cell_state(batch(rows2(), TS2), exp.new_cell_state())
        b = batch(rows2(), TS2)
        w = {E1: 1.5}
        v = exp.stateful_node_values(b, w, st)
        c = exp.stateful_cell_values(b, w, st)
        k = 42.0
        s0 = exp.select_nodes(v, c)
        s1 = exp.select_nodes({s: k * x for s, x in v.items()},
                              {ck: k * x for ck, x in c.items()})
        for key in ("king", "top6", "stars"):
            self.assertEqual(s0[key], s1[key])

    def test_unsigned_node_scores(self):
        # spec §10.6.6: d/r/tau cannot flip signs
        st = exp.new_cell_state()
        st = exp.update_cell_state(batch(rows1(), TS1, spot=104.0), st)
        st = exp.update_cell_state(batch(rows2(), TS2, spot=103.0), st)
        for s in (100.0, 110.0):
            d, r, t = exp.node_state_scores(st, s)
            self.assertGreaterEqual(d, 0.0)
            self.assertGreaterEqual(r, 0.0)
            self.assertGreaterEqual(t, 0.0)

    def test_day_boundary_resets_ceil_floor(self):
        st = exp.update_cell_state(batch(rows1(), TS1), exp.new_cell_state())
        self.assertEqual(st["ceil"], {E1: 11.0})            # |6| + |-5|
        st2 = exp.update_cell_state(
            batch(rows1(), "2026-10-01T14:30:00+00:00"), st)
        self.assertEqual(st2["ceil"], {E1: 11.0})           # fresh day: reset then set
        self.assertTrue(math.isclose(st2["q_g"][(100.0, E1)], 6.0, rel_tol=1e-12))
        self.assertEqual(st2["floor"], {E1: 11.0})

    def test_empty_batch(self):
        b = exp.normalize_batch([], ts=TS1, spot=105.0)
        self.assertEqual(exp.stateful_node_values(b, {}, exp.new_cell_state()), {})
        st = exp.update_cell_state(b, exp.new_cell_state())
        self.assertEqual(st["q_g"], {})


if __name__ == "__main__":
    unittest.main()
