#!/usr/bin/env python3
"""E0.6 non-linear / shape-class RE iteration (goal-judge directive).

Previous iteration: every LINEAR within-cell class loses to the g basis
(docs/build/skylit-cell-model.md §2b). This probe tests concrete NON-LAR
/ structural classes:

1. strike-lag alignment: is their cell column aligned with our g at a shifted
   strike? (grid-index shifts -3..+3) -- if best lag != 0 the basis itself is
   misaligned.
2. within-column power class: h = sign(g)*|g|^p, p in {0.25..2} -- nonlinear
   monotone reshaping of g inside the column.
3. per-DTE-bucket ALS theta (chain+shape features): separate theta per expiry
   distance bucket {0-1, 2-7, 8-45, 46+} -- piecewise-linear in DTE.
4. piecewise spot-side ALS theta: separate theta for s >= spot vs s < spot.

Metrics: median within-column cos^2 (per-column LS scale profiled, mask g!=0,
n>=5) + LODO for the ALS classes. Baseline g = 0.0941 (full set).

Usage:
  python3 scripts/e06_nonlinear_probe.py run [--execute]

Clean-room; leandata/RE captures read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import e06_cell_model as e06  # noqa: E402

OUT_DIR = os.path.join(REPO, "data", "e06", "accum")


def col_cos2_med(target, pred, colkeys):
    c2, _ = e06._col_stats(target, pred, colkeys)
    return (float(np.median(c2)) if c2 else None), len(c2)


def als_fit(Xs, c, colkeys, ridge=1e-8, iters=12):
    F = Xs.shape[1]
    theta = np.zeros(F)
    theta[0] = 1.0
    order = np.argsort(colkeys, kind="stable")
    ks = colkeys[order]
    Xm = np.ascontiguousarray(Xs[order])
    cm = np.ascontiguousarray(c[order])
    boundaries = np.flatnonzero(np.diff(ks)) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [len(ks)]))
    sizes = ends - starts
    for _ in range(iters):
        h_all = Xm @ theta
        t_h = np.add.reduceat(cm * h_all, starts)
        t_t = np.add.reduceat(cm * cm, starts)
        h_h = np.add.reduceat(h_all * h_all, starts)
        ok = (h_h > 0) & (t_t > 0) & (sizes >= 5)
        if not ok.any():
            break
        lam_seg = np.zeros(len(starts))
        lam_seg[ok] = t_h[ok] / h_h[ok]
        lam_cell = np.repeat(lam_seg, ends - starts)
        w_cell = lam_cell * lam_cell
        xtx = Xm.T @ (Xm * w_cell[:, None])
        xty = Xm.T @ (cm * lam_cell)
        theta = e06._solve_ridge(xtx, xty, ridge)
        nrm = float(np.linalg.norm(theta))
        if nrm > 0:
            theta = theta / nrm
    return theta


def run(execute):
    M = e06.materialize()
    g = M.feats[:, e06.FEAT_INDEX["g"]].astype(np.float64)
    mask = g != 0
    cells = M.cells[mask]
    colkeys = e06._build_colkeys(M, mask)
    gm = g[mask]
    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "script": "scripts/e06_nonlinear_probe.py run",
           "baseline_g_full_set": 0.0941}

    med, n = col_cos2_med(cells, gm, colkeys)
    out["g_same_walk"] = {"median_cos2": med, "n_cols": n}

    # --- 1. strike-lag alignment -----------------------------------------
    # grid index per cell (rec_ij i-index), masked
    gi = np.zeros(M.cells.size, dtype=np.int32)
    for rid, (start, end, _rec) in enumerate(M.rec_slices):
        i_idx, _j = M.rec_ij[rid]
        gi[start:end] = i_idx
    gik = gi[mask]
    lags = {}
    for k in (-3, -2, -1, 1, 2, 3):
        pred = np.zeros_like(gm)
        # shift g by k grid steps within each (record, expiry) column
        order = np.argsort(colkeys, kind="stable")
        ks = colkeys[order]
        boundaries = np.flatnonzero(np.diff(ks)) + 1
        starts = np.concatenate(([0], boundaries))
        ends = np.concatenate((boundaries, [len(ks)]))
        g_ord = gm[order]
        i_ord = gik[order]
        pred_ord = np.zeros_like(g_ord)
        for a, b in zip(starts, ends):
            idx = i_ord[a:b]
            val = g_ord[a:b]
            m = {}
            for x, v in zip(idx, val):
                m[int(x)] = v
            for r, x in enumerate(idx):
                pred_ord[a + r] = m.get(int(x) + k, 0.0)
        pred[order] = pred_ord
        med_k, n_k = col_cos2_med(cells, pred, colkeys)
        lags[str(k)] = {"median_cos2": med_k, "n_cols": n_k}
    med0, _ = col_cos2_med(cells, gm, colkeys)
    lags["0"] = {"median_cos2": med0}
    out["strike_lag"] = lags
    print("strike-lag cos2:", {k: (v["median_cos2"]) for k, v in lags.items()})

    # --- 2. within-column power class ------------------------------------
    powers = {}
    for p in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        pred = np.sign(gm) * np.abs(gm) ** p
        med_p, n_p = col_cos2_med(cells, pred, colkeys)
        powers[str(p)] = {"median_cos2": med_p, "n_cols": n_p}
    out["power_class"] = powers
    print("power class cos2:", {k: v["median_cos2"] for k, v in powers.items()})

    # --- 3/4. per-DTE-bucket + piecewise spot-side ALS --------------------
    sel = e06.GROUPS["chain"] + e06.GROUPS["shape"]
    cols = [e06.FEAT_INDEX[f] for f in sel]
    X = M.feats[mask][:, cols].astype(np.float64)
    means = X.mean(axis=0)
    norms = np.sqrt(np.maximum(X.var(axis=0), 1e-30))
    Xs = (X - means) / norms

    # per-cell: DTE bucket + spot side, from rec_slices
    dte_b = np.zeros(M.cells.size, dtype=np.int8)
    side = np.zeros(M.cells.size, dtype=np.int8)
    for rid, (start, end, rec) in enumerate(M.rec_slices):
        _i, j = M.rec_ij[rid]
        exps = rec["expiries"]
        day = rec["day"]
        spot = rec.get("spot") or 0.0
        strikes = [float(s) for s in rec["strikes"]]
        for r in range(end - start):
            e = exps[j[r]]
            try:
                d = (datetime.fromisoformat(e)
                     - datetime.fromisoformat(day)).days
            except Exception:
                d = 0
            b = 0 if d <= 1 else (1 if d <= 7 else (2 if d <= 45 else 3))
            dte_b[start + r] = b
            s = strikes[_i[r]]
            side[start + r] = 1 if s >= spot else 0
    dte_k = dte_b[mask]
    side_k = side[mask]

    def als_eval(sel_mask, tag):
        if int(sel_mask.sum()) < 500:
            return None
        Xsub = Xs[sel_mask]
        csub = cells[sel_mask]
        ksub = colkeys[sel_mask]
        # LODO by day for honesty
        days_k = M.day[mask][sel_mask]
        th_full = als_fit(Xsub, csub, ksub)
        med_full, n_full = col_cos2_med(csub, Xsub @ th_full, ksub)
        lodo = {}
        for di in range(len(M.days)):
            tr = days_k != di
            te = days_k == di
            if tr.sum() < 500 or te.sum() < 200:
                continue
            th_d = als_fit(Xsub[tr], csub[tr], ksub[tr])
            med_d, _ = col_cos2_med(csub[te], Xsub[te] @ th_d, ksub[te])
            lodo[M.days[di]] = med_d
        g_med, _ = col_cos2_med(csub, g[mask][sel_mask], ksub)
        # per-day g baseline on the SAME held-out-day columns as LODO, so the
        # honest out-of-sample comparison (theta LODO vs g) is computable from
        # this artifact alone (added 2026-10-01, re-measure lane t_c21da222).
        g_lodo = {}
        for di in range(len(M.days)):
            te = days_k == di
            if te.sum() < 200:
                continue
            g_day_med, _ = col_cos2_med(csub[te], g[mask][sel_mask][te],
                                        ksub[te])
            g_lodo[M.days[di]] = g_day_med
        print(f"  {tag}: g_med={g_med} theta_med={med_full} "
              f"lodo={lodo} g_lodo={g_lodo} (n_cols={n_full})")
        return {"g_median_cos2": g_med, "theta_median_cos2": med_full,
                "lodo_median_cos2": lodo, "g_lodo_median_cos2": g_lodo,
                "n_cols": n_full}

    out["dte_bucket_als"] = {}
    for b, name in ((0, "dte_0_1"), (1, "dte_2_7"), (2, "dte_8_45"),
                    (3, "dte_46p")):
        out["dte_bucket_als"][name] = als_eval(dte_k == b, name)
    out["piecewise_side_als"] = {
        "above_spot": als_eval(side_k == 1, "above_spot"),
        "below_spot": als_eval(side_k == 0, "below_spot"),
    }

    if execute:
        path = os.path.join(OUT_DIR, "nonlinear_probe.json")
        os.makedirs(OUT_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(out, f, indent=1, default=str)
        os.replace(tmp, path)
        print("written:", path)
    else:
        print("(dry-run; pass --execute to write)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["run"])
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    return run(args.execute)


if __name__ == "__main__":
    sys.exit(main())
