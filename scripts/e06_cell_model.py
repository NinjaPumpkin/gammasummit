#!/usr/bin/env python3
"""E0.6 per-cell value model: RE Skylit's per-cell gamma-heatmap calcs from UW.

Goal (card t_3a0b0ae0): model the Skylit per-cell values `rec["cells"]` (matrix
captures, strike x expiry) from the UW gamma_data_v2 extraction until our
per-cell values are "very close" to theirs. The gap this card attacks is CELL
SHAPE (docs/build/e05b-king-parity.md §5: oracle-bound 68.6% king exact for the
`a_e` weight class on the `g = call_gex - put_gex` basis; median within-column
R^2 0.089).

Metric definitions (pinned to the established ones):

- within-column R^2 = cos^2(c_col, h_col) per (record, expiry) column, LS
  scale profiled per column (scripts/e02_cross_expiry_fit.py fit_instant:
  `col_r2 = 1 - resid/capp` == cos^2 with `a = <c,g>/<g,g>`). Mask: cells with
  a UW row, g != 0, n >= 5 per column. Baseline (h = g): 0.089.
- node APE = per-record median |c_scale*V_ours - V_sk| / |V_sk| on material
  nodes (|V_sk| >= 5% max), c_scale = per-record LS scalar
  (scripts/e03_batch_harness.py score_record). Baseline p50 ~ 1.00.
- king exact = argmax |V| over grid strikes, tie-break smallest strike, vs
  Skylit `king` nodeType. Baseline 35.42% exact / 83.32% +/-tol (gamma-tempered
  psi weights, data/e05b/after).
- ORACLE_free / ORACLE_joint = scripts/e05b_king_fix.py oracle_weights numerics
  (bound-only, per-record LS weights vs their cells / node values). Baselines
  on the g basis: 40.86% / 68.60% exact.

Model class: per-cell shape h(s,e) = theta . phi(s,e) — strike-relative UW
features + accumulation proxies from OUR history (uw_cache batches walked in
ts order per symbol; leandata multi-year history is a future feature source per
operator note 2026-10-01, read-only). Fit is incremental + deterministic:
re-running `fit` over the growing Tier-A set (daily refit cron adds days)
refits theta from scratch.

Commands (dry-run default; --execute writes data/e06/):

  python3 scripts/e06_cell_model.py features [--execute]
  python3 scripts/e06_cell_model.py fit      [--execute]
  python3 scripts/e06_cell_model.py eval     [--execute] [--group all]
  python3 scripts/e06_cell_model.py verify

Clean-room: all derivations from math + RE evidence; no reference-system code
read or copied. RE captures (X10) are read-only.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from backend.core import exposure as exp  # noqa: E402

FITSET_DIR = os.path.join(REPO, "data", "e02", "fit_dataset")
UWCACHE_DIR = os.path.join(REPO, "data", "e02", "uw_cache")
OUT_DIR = os.path.join(REPO, "data", "e06")

KING_TOL = {"SPX": 25.0}
KING_TOL_DEFAULT = 5.0
MATERIAL_FRAC = 0.05

FEATS = (
    # same-instant UW chain
    "g", "call_gex", "put_gex", "gex_value", "abs_gex", "dex_value",
    "net_dex", "call_dex", "put_dex",
    # OI + migration
    "net_oi", "tot_oi", "abs_oi", "doi_net", "doi_gross",
    # volume + ask/bid imbalance
    "net_volume", "tot_volume", "cab", "pab", "imb",
    # iv
    "iv",
    # strike-relative structure (x = (s - spot)/spot)
    "x", "ax", "x2", "sgx", "expd",
    "g_x", "g_sgx", "abs_g_expd", "g_expd", "net_oi_expd", "net_oi_x",
    # column-shape normalizations
    "g_colnorm", "g_z",
    # accumulation proxies from our own history (uw_cache walk)
    "cum_net_volume", "cum_imb", "cum_doi_net", "ewma_g_slow", "g_dev_slow",
    "ewma_g_fast", "g_dev_fast", "n_batches",
)

GROUPS = {
    "chain": ["g", "call_gex", "put_gex", "gex_value", "abs_gex", "dex_value",
              "net_dex"],
    "oi_vol": ["net_oi", "tot_oi", "abs_oi", "doi_net", "doi_gross",
               "net_volume", "tot_volume", "cab", "pab", "imb", "iv"],
    "shape": ["x", "ax", "x2", "sgx", "expd", "g_x", "g_sgx", "abs_g_expd",
              "g_expd", "net_oi_expd", "net_oi_x", "g_colnorm", "g_z"],
    "accum": ["cum_net_volume", "cum_imb", "cum_doi_net", "ewma_g_slow",
              "g_dev_slow", "ewma_g_fast", "g_dev_fast", "n_batches"],
}
GROUPS["all"] = [f for g in ("chain", "oi_vol", "shape", "accum")
                 for f in GROUPS[g]]

EWMA_SLOW = 0.9    # per-batch step (~4min cadence -> half-life ~26 min)
EWMA_FAST = 0.5

FEAT_INDEX = {name: i for i, name in enumerate(FEATS)}


def _jgzload(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def _jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def is_stale_record(rec) -> bool:
    """Per-record RE staliness (spec §5.2): |asOf - window_start| > 2 s."""
    try:
        win_start = datetime.fromisoformat(
            f"{rec['day']}T{rec['window'][:2]}:{rec['window'][2:4]}:"
            f"{rec['window'][4:6]}+00:00")
        asof = datetime.fromisoformat(str(rec["asOf"]).replace("Z", "+00:00"))
        return abs((asof - win_start).total_seconds()) > 2
    except Exception:
        return bool(rec.get("stale_symbol"))


# ---------------------------------------------------------------- data walk

def load_index():
    with open(os.path.join(FITSET_DIR, "index.json")) as f:
        return json.load(f)


def walk_fit_records():
    """Fit records in harness order (symbol, uw_ts, asOf), stale skipped."""
    index = load_index()
    instants = sorted(index["instants"],
                      key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))
    for e in instants:
        p = os.path.join(FITSET_DIR, f"{e['key'].replace('/', '_')}.json.gz")
        if os.path.exists(p):
            rec = _jgzload(p)
            if is_stale_record(rec):
                continue
            yield rec


class Accumulator:
    """Per-(strike, expiry) accumulation state walked over uw_cache batches."""

    def __init__(self):
        self.q_slow = {}
        self.q_fast = {}
        self.cum_net_volume = defaultdict(float)
        self.cum_imb = defaultdict(float)
        self.cum_doi_net = defaultdict(float)
        self.n_batches = defaultdict(int)

    def ingest(self, rows):
        out = {}
        for r in rows:
            key = (float(r["strike"]), r["expiry_date"])
            g = float(r["call_gex"] or 0.0) - float(r["put_gex"] or 0.0)
            q_s_prev = self.q_slow.get(key)
            q_f_prev = self.q_fast.get(key)
            self.q_slow[key] = (EWMA_SLOW * q_s_prev + (1 - EWMA_SLOW) * g
                                if q_s_prev is not None else g)
            self.q_fast[key] = (EWMA_FAST * q_f_prev + (1 - EWMA_FAST) * g
                                if q_f_prev is not None else g)
            imb = ((float(r["call_ask_vol"] or 0) - float(r["call_bid_vol"] or 0))
                   - (float(r["put_ask_vol"] or 0) - float(r["put_bid_vol"] or 0)))
            doi = ((float(r["call_oi"] or 0) - float(r["call_prev_oi"] or 0))
                   - (float(r["put_oi"] or 0) - float(r["put_prev_oi"] or 0)))
            self.cum_net_volume[key] += float(r["net_volume"] or 0.0)
            self.cum_imb[key] += imb
            self.cum_doi_net[key] += doi
            self.n_batches[key] += 1
            out[key] = {
                "cum_net_volume": self.cum_net_volume[key],
                "cum_imb": self.cum_imb[key],
                "cum_doi_net": self.cum_doi_net[key],
                "ewma_g_slow": self.q_slow[key],
                "g_dev_slow": g - q_s_prev if q_s_prev is not None else 0.0,
                "ewma_g_fast": self.q_fast[key],
                "g_dev_fast": g - q_f_prev if q_f_prev is not None else 0.0,
                "n_batches": float(self.n_batches[key]),
            }
        return out


def feature_row(r, acc_feats, spot, strike, col_stats):
    g = float(r["call_gex"] or 0.0) - float(r["put_gex"] or 0.0)
    cg = float(r["call_gex"] or 0.0)
    pg = float(r["put_gex"] or 0.0)
    coi = float(r["call_oi"] or 0.0)
    poi = float(r["put_oi"] or 0.0)
    dcoi = coi - float(r["call_prev_oi"] or 0.0)
    dpoi = poi - float(r["put_prev_oi"] or 0.0)
    cab = float(r["call_ask_vol"] or 0.0) - float(r["call_bid_vol"] or 0.0)
    pab = float(r["put_ask_vol"] or 0.0) - float(r["put_bid_vol"] or 0.0)
    cvol = float(r["call_volume"] or 0.0)
    pvol = float(r["put_volume"] or 0.0)
    x = (strike - spot) / spot if spot else 0.0
    ax = abs(x)
    expd = math.exp(-ax / 0.02)
    sgn = 1.0 if x > 0 else (-1.0 if x < 0 else 0.0)
    f = {
        "g": g,
        "call_gex": cg,
        "put_gex": pg,
        "gex_value": float(r["gex_value"] or 0.0),
        "abs_gex": float(r["abs_gex"] or 0.0),
        "dex_value": float(r["dex_value"] or 0.0),
        "net_dex": float(r["call_dex"] or 0.0) - float(r["put_dex"] or 0.0),
        "call_dex": float(r["call_dex"] or 0.0),
        "put_dex": float(r["put_dex"] or 0.0),
        "net_oi": coi - poi,
        "tot_oi": coi + poi,
        "abs_oi": float(r["abs_oi"] or 0.0),
        "doi_net": dcoi - dpoi,
        "doi_gross": abs(dcoi) + abs(dpoi),
        "net_volume": float(r["net_volume"] or 0.0),
        "tot_volume": cvol + pvol,
        "cab": cab,
        "pab": pab,
        "imb": cab - pab,
        "iv": float(r["iv"] or 0.0),
        "x": x,
        "ax": ax,
        "x2": x * x,
        "sgx": sgn,
        "expd": expd,
        "g_x": g * x,
        "g_sgx": g * sgn,
        "abs_g_expd": float(r["abs_gex"] or 0.0) * expd,
        "g_expd": g * expd,
        "net_oi_expd": (coi - poi) * expd,
        "net_oi_x": (coi - poi) * x,
        "g_colnorm": g / (col_stats["g_abs_sum"] + 1e-30),
        "g_z": (g - col_stats["g_mean"]) / (col_stats["g_std"] + 1e-30),
    }
    f.update(acc_feats)
    return f


class Materialized:
    """One-pass walk product: per-record cell arrays + design matrices."""

    def __init__(self):
        self.cells = []          # (n,) float64 Skylit cell values
        self.feats = []          # (n, F) float32 design rows
        self.day = []            # (n,) uint8 day index per cell
        self.rec_slices = []     # per record: (start, end, rec)
        self.rec_ij = []         # per record: (i_idx, j_idx) arrays per row
        self.days = []

    def finalize(self):
        self.cells = np.concatenate(self.cells) if self.cells else np.zeros(0)
        self.feats = (np.concatenate(self.feats) if self.feats
                      else np.zeros((0, len(FEATS)), dtype=np.float32))
        self.day = (np.concatenate(self.day) if self.day
                    else np.zeros(0, dtype=np.uint8))


def materialize() -> Materialized:
    index = load_index()
    days = sorted({e["day"] for e in index["instants"]})
    day_idx = {d: i for i, d in enumerate(days)}
    instants = sorted(index["instants"],
                      key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))
    recs_by_key = {}
    for e in instants:
        p = os.path.join(FITSET_DIR, f"{e['key'].replace('/', '_')}.json.gz")
        if os.path.exists(p):
            rec = _jgzload(p)
            if is_stale_record(rec):
                continue
            recs_by_key.setdefault((rec["symbol"], rec["uw_ts"]), []).append(rec)

    cache = defaultdict(list)
    for fn in sorted(os.listdir(UWCACHE_DIR)):
        if fn.endswith(".json.gz"):
            path = os.path.join(UWCACHE_DIR, fn)
            rows = _jgzload(path)
            if rows:
                cache[rows[0]["ticker"]].append((rows[0]["timestamp"], path))
    for sym in cache:
        cache[sym].sort()

    M = Materialized()
    M.days = days
    t0 = time.time()
    n_rec = 0
    for sym in sorted(cache):
        acc = Accumulator()
        for ts, path in cache[sym]:
            rows = _jgzload(path)
            acc_out = acc.ingest(rows)
            recs = recs_by_key.get((sym, ts))
            if not recs:
                continue
            by_cell = {(float(r["strike"]), r["expiry_date"]): r for r in rows}
            for rec in recs:
                n_rec += 1
                strikes = [float(s) for s in rec["strikes"]]
                exps = rec["expiries"]
                C = np.array(rec["cells"], dtype=float)
                per_col = {}
                for e in exps:
                    gs = []
                    for s in strikes:
                        r = by_cell.get((s, e))
                        if r is not None:
                            gs.append(float(r["call_gex"] or 0.0)
                                      - float(r["put_gex"] or 0.0))
                    if gs:
                        ga = np.array(gs)
                        per_col[e] = {"g_abs_sum": float(np.abs(ga).sum()),
                                      "g_mean": float(ga.mean()),
                                      "g_std": float(ga.std())}
                    else:
                        per_col[e] = {"g_abs_sum": 0.0, "g_mean": 0.0,
                                      "g_std": 1.0}
                cells_l, feats_l, i_idx, j_idx = [], [], [], []
                for j, e in enumerate(exps):
                    cs = per_col[e]
                    for i, s in enumerate(strikes):
                        r = by_cell.get((s, e))
                        if r is None:
                            continue
                        fd = feature_row(r, acc_out.get((s, e), {}),
                                         rec.get("spot"), s, cs)
                        cells_l.append(C[i, j])
                        feats_l.append([fd[name] for name in FEATS])
                        i_idx.append(i)
                        j_idx.append(j)
                if not cells_l:
                    continue
                start = (M.rec_slices[-1][1] if M.rec_slices else 0)
                M.cells.append(np.array(cells_l, dtype=np.float64))
                M.feats.append(np.array(feats_l, dtype=np.float32))
                M.day.append(np.full(len(cells_l), day_idx[rec["day"]],
                                     dtype=np.uint8))
                M.rec_slices.append((start, start + len(cells_l), rec))
                M.rec_ij.append((np.array(i_idx, dtype=np.int32),
                                 np.array(j_idx, dtype=np.int32)))
                if n_rec % 200 == 0:
                    print(f"  ... {n_rec} records, {time.time()-t0:.0f}s",
                          flush=True)
    M.finalize()
    print(f"materialized: {n_rec} records, {M.cells.size} cells, "
          f"{time.time()-t0:.0f}s")
    return M


# ------------------------------------------------- within-column cos^2 stats

def _col_stats(t, p, keys, min_n=5):
    """Per-column (cos^2, spearman) lists."""
    order = np.argsort(keys, kind="stable")
    ks = keys[order]
    tc = t[order]
    pc = p[order]
    boundaries = np.flatnonzero(np.diff(ks)) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [len(ks)]))
    c2, sp = [], []
    for a, b in zip(starts, ends):
        t2 = tc[a:b]
        p2 = pc[a:b]
        if len(t2) < min_n:
            continue
        cc = float(np.dot(t2, t2))
        hh = float(np.dot(p2, p2))
        if cc > 0 and hh > 0:
            num = float(np.dot(t2, p2))
            c2.append(num * num / (cc * hh))
        if not np.all(t2 == t2[0]) and not np.all(p2 == p2[0]):
            rt = np.argsort(np.argsort(t2)).astype(np.float64)
            rp = np.argsort(np.argsort(p2)).astype(np.float64)
            rt -= rt.mean()
            rp -= rp.mean()
            den = math.sqrt(float(np.dot(rt, rt)) * float(np.dot(rp, rp)))
            if den > 0:
                sp.append(float(np.dot(rt, rp)) / den)
    return c2, sp


def _summ(v):
    if not v:
        return None
    a = np.array(v)
    return {"n": int(a.size), "median": round(float(np.median(a)), 4),
            "p25": round(float(np.percentile(a, 25)), 4),
            "p75": round(float(np.percentile(a, 75)), 4)}


def _build_colkeys(M: Materialized, mask=None):
    """(record_id * 100 + expiry_idx) per cell -> unique column per (rec, e)."""
    keys = np.zeros(M.cells.size, dtype=np.int64)
    for rid, (start, end, rec) in enumerate(M.rec_slices):
        _i, j = M.rec_ij[rid]
        keys[start:end] = rid * 100 + j
    return keys[mask] if mask is not None else keys


# ---------------------------------------------------------------- commands

def cmd_features(execute: bool) -> int:
    M = materialize()
    g = M.feats[:, FEAT_INDEX["g"]].astype(np.float64)
    mask = g != 0
    cells = M.cells[mask]
    colkeys = _build_colkeys(M, mask)
    out_feats = {}
    for i, name in enumerate(FEATS):
        c2, _ = _col_stats(cells, M.feats[mask, i].astype(np.float64), colkeys)
        out_feats[name] = _summ(c2)
    _, sp_g = _col_stats(cells, g[mask], colkeys)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/e06_cell_model.py features",
        "n_records": len(M.rec_slices),
        "n_cells_scored": int(mask.sum()),
        "definition": "per-(record,expiry) cos^2 with per-column LS scale; "
                      "mask g!=0 within column, n>=5 (E0.2 col_r2)",
        "baseline_g": out_feats["g"],
        "spearman_g": _summ(sp_g),
        "features": out_feats,
    }
    print("baseline g:", json.dumps(out["baseline_g"]))
    print("spearman g:", json.dumps(out["spearman_g"]))
    top = sorted(out_feats.items(),
                 key=lambda kv: -(kv[1]["median"] if kv[1] else -1))[:15]
    for name, s in top:
        print(f"  {name:16s} median cos2 {s['median']}  "
              f"(p25 {s['p25']} p75 {s['p75']}, n {s['n']})")
    if execute:
        path = os.path.join(OUT_DIR, "feature_cos2.json")
        _jdump(out, path)
        print("written:", path)
    else:
        print("(dry-run; pass --execute to write)")
    return 0


def cmd_fit(execute: bool, ridge: float = 1e-8, iters: int = 12) -> int:
    """ALS fit of theta per feature group (scale-honest objective):
    J(theta) = mean over columns of cos^2(c_col, (X theta)_col), per-column LS
    scale lambda_col profiled. LODO: fit on all-but-one day, score held-out.
    """
    M = materialize()
    g = M.feats[:, FEAT_INDEX["g"]].astype(np.float64)
    mask = g != 0
    colkeys = _build_colkeys(M, mask)
    days = M.days
    group_sel = {
        "chain": GROUPS["chain"],
        "chain+oi_vol": GROUPS["chain"] + GROUPS["oi_vol"],
        "chain+shape": GROUPS["chain"] + GROUPS["shape"],
        "chain+accum": GROUPS["chain"] + GROUPS["accum"],
        "all": GROUPS["all"],
    }
    results = {}
    for gname, sel in group_sel.items():
        print(f"== group {gname} (F={len(sel)})")
        cols = [FEAT_INDEX[f] for f in sel]
        X = M.feats[mask][:, cols].astype(np.float64)
        c = M.cells[mask]
        d = M.day[mask]
        means = X.mean(axis=0)
        norms = np.sqrt(np.maximum(X.var(axis=0), 1e-30))
        Xs = (X - means) / norms
        F = Xs.shape[1]

        def fit_theta(day_mask, tag):
            Xm = np.ascontiguousarray(Xs[day_mask])
            cm = np.ascontiguousarray(c[day_mask])
            km = colkeys[day_mask]
            theta = np.zeros(F)
            theta[0] = 1.0
            j_hist = []
            ncol = 0
            order = np.argsort(km, kind="stable")
            ks = km[order]
            Xm = Xm[order]
            cm = cm[order]
            boundaries = np.flatnonzero(np.diff(ks)) + 1
            starts = np.concatenate(([0], boundaries))
            ends = np.concatenate((boundaries, [len(ks)]))
            sizes = ends - starts
            if len(starts) == 0:
                return theta, j_hist
            # reduceat needs strictly increasing indices; starts is sorted
            for _it in range(iters):
                h_all = Xm @ theta
                t_h = np.add.reduceat(cm * h_all, starts)
                t_t = np.add.reduceat(cm * cm, starts)
                h_h = np.add.reduceat(h_all * h_all, starts)
                ok = (h_h > 0) & (t_t > 0) & (sizes >= 5)
                lam_seg = np.zeros(len(starts))
                lam_seg[ok] = t_h[ok] / h_h[ok]
                J = float(((t_h[ok] ** 2) / (t_t[ok] * h_h[ok])).sum())
                ncol = int(ok.sum())
                if ncol == 0:
                    break
                lam_cell = np.repeat(lam_seg, ends - starts)
                w_cell = lam_cell * lam_cell
                xtx = Xm.T @ (Xm * w_cell[:, None])
                xty = Xm.T @ (cm * lam_cell)
                theta = _solve_ridge(xtx, xty, ridge)
                nrm = float(np.linalg.norm(theta))
                if nrm > 0:
                    theta = theta / nrm
                j_hist.append(round(J / ncol, 5))
                if len(j_hist) > 2 and abs(j_hist[-1] - j_hist[-2]) < 1e-6:
                    break
            print(f"  {tag}: J={j_hist[-1] if j_hist else None} "
                  f"(ncol {ncol}, iters {len(j_hist)})")
            return theta, j_hist

        def eval_theta(day_mask, theta_):
            pred = Xs[day_mask] @ theta_
            c2, _ = _col_stats(c[day_mask], pred, colkeys[day_mask])
            return float(np.median(c2)) if c2 else None

        full_mask = np.ones(len(c), dtype=bool)
        theta, j_hist = fit_theta(full_mask, "full")
        lodo = {}
        for di, day in enumerate(days):
            th_d, _ = fit_theta(d != di, f"train(not {day})")
            lodo[day] = eval_theta(d == di, th_d)
            print(f"  LODO {day}: held-out median cos2 = {lodo[day]}")
        results[gname] = {
            "features": sel,
            "theta_standardized": [round(float(x), 6) for x in theta],
            "standardization": {
                "means": [round(float(x), 6) for x in means],
                "norms": [round(float(x), 6) for x in norms],
            },
            "j_history": j_hist,
            "insample_median_cos2": eval_theta(full_mask, theta),
            "lodo_median_cos2": lodo,
        }
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/e06_cell_model.py fit",
        "days": days,
        "n_days": len(days),
        "n_records": len(M.rec_slices),
        "objective": "mean per-column cos^2 (per-column LS scale profiled); "
                     "ALS alternating scale/theta; ridge 1e-8",
        "note": "incremental by re-run: refit over the growing Tier-A set "
                "(daily refit cron adds days)",
        "results": results,
    }
    print(json.dumps({k: {"insample_median_cos2": v["insample_median_cos2"],
                          "lodo_median_cos2": v["lodo_median_cos2"]}
                      for k, v in results.items()}, indent=1, default=str))
    if execute:
        path = os.path.join(OUT_DIR, "cell_theta.json")
        _jdump(out, path)
        print("written:", path)
    else:
        print("(dry-run; pass --execute to write)")
    return 0


def _solve_ridge(a, b, ridge):
    a = a + ridge * np.eye(a.shape[0])
    try:
        return np.linalg.solve(a, b)
    except np.linalg.LinAlgError:
        return np.linalg.lstsq(a, b, rcond=None)[0]


def _score_v(v_full, v_sk, strikes, ntypes, symbol):
    vmax = max((abs(v) for v in v_sk), default=0.0)
    if vmax == 0:
        return None
    material = [i for i, v in enumerate(v_sk)
                if abs(v) >= MATERIAL_FRAC * vmax]
    v_ours = [v_full.get(s, 0.0) for s in strikes]
    den = sum(x * x for x in v_ours)
    c_scale = (sum(a * b for a, b in zip(v_sk, v_ours)) / den) if den > 0 else 0.0
    v_hat = [c_scale * x for x in v_ours]
    apes = sorted(abs(v_hat[i] - v_sk[i]) / max(abs(v_sk[i]), 1e-12)
                  for i in material)
    med = apes[len(apes) // 2] if apes else None
    ki = next((i for i, t in enumerate(ntypes) if t == "king"), None)
    if ki is None:
        ki = max(range(len(strikes)), key=lambda i: (abs(v_sk[i]), -strikes[i]))
    T = strikes[ki]
    P = max(range(len(strikes)), key=lambda i: (abs(v_ours[i]), -strikes[i]))
    tol = KING_TOL.get(symbol, KING_TOL_DEFAULT)
    top_pred = sorted(range(len(strikes)),
                      key=lambda i: (-abs(v_ours[i]), strikes[i]))[:6]
    top_true = sorted(range(len(strikes)),
                      key=lambda i: (-abs(v_sk[i]), strikes[i]))[:6]
    top6 = len({strikes[i] for i in top_pred} & {strikes[i] for i in top_true})
    return {"node_med_ape": med, "king_exact": strikes[P] == T,
            "king_within_tol": abs(strikes[P] - T) <= tol,
            "top6_overlap": top6}


def _oracle_weights_h(h_cols, grid, cells, y, exps, mode):
    """e05b_king_fix.oracle_weights numerics on an arbitrary basis h_cols."""
    if mode == "free":
        a = {}
        for j, e in enumerate(exps):
            num = den = 0.0
            cm = h_cols.get(e, {})
            for i, s in enumerate(grid):
                g = cm.get(s, 0.0)
                num += float(cells[i][j]) * g
                den += g * g
            a[e] = num / den if den > 0 else 0.0
        return a
    E = len(exps)
    xtx = [[0.0] * E for _ in range(E)]
    xty = [0.0] * E
    for i, s in enumerate(grid):
        row = [(j, h_cols.get(e, {}).get(s, 0.0)) for j, e in enumerate(exps)]
        row = [(j, v) for j, v in row if v != 0.0]
        if not row:
            continue
        yi = y[i]
        for j1, r1 in row:
            xty[j1] += r1 * yi
            for j2, r2 in row:
                xtx[j1][j2] += r1 * r2
    for j in range(E):
        xtx[j][j] += 1e-9
    Mat = [xtx[i] + [xty[i]] for i in range(E)]
    for i in range(E):
        piv = max(range(i, E), key=lambda r: abs(Mat[r][i]))
        Mat[i], Mat[piv] = Mat[piv], Mat[i]
        if abs(Mat[i][i]) < 1e-300:
            continue
        for r in range(E):
            if r == i:
                continue
            f = Mat[r][i] / Mat[i][i]
            for cc in range(i, E + 1):
                Mat[r][cc] -= f * Mat[i][cc]
    a = {}
    for j, e in enumerate(exps):
        a[e] = (Mat[j][E] / Mat[j][j]) if abs(Mat[j][j]) > 1e-300 else 0.0
    return a


def cmd_eval(execute: bool, group: str = "all") -> int:
    """V-mode evaluation.

    Models: h = g (baseline pin: 35.42%/83.32% king, oracle 40.86%/68.60%)
    and h = theta.phi (from data/e06/cell_theta.json, standardized with the
    stored means/norms -- in-sample theta, caveat recorded in output).
    Shippable path: V = sum_e a_e * h with a_e = normative psi EWMA weights
    (exposure.cross_expiry_weights). Bound test: oracle free/joint on the h
    basis (their numbers used as LS targets -> bound only).
    """
    theta_path = os.path.join(OUT_DIR, "cell_theta.json")
    tj = json.load(open(theta_path)) if os.path.exists(theta_path) else None
    theta = means = norms = sel = None
    if tj and group in tj["results"]:
        r = tj["results"][group]
        sel = r["features"]
        theta = np.array(r["theta_standardized"], dtype=np.float64)
        means = np.array(r["standardization"]["means"], dtype=np.float64)
        norms = np.array(r["standardization"]["norms"], dtype=np.float64)
    else:
        print("WARNING: no cell_theta.json / group -- baseline g only")

    models = ["g_baseline"] + ([f"theta_{group}"] if theta is not None else [])
    stats = {m: {"n": 0, "exact": 0, "tol": 0, "top6": 0, "apes": [],
                 "oracle_free_exact": 0, "oracle_joint_exact": 0,
                 "oracle_free_tol": 0, "oracle_joint_tol": 0}
             for m in models}

    M = materialize()
    slice_of = {}
    for rid, (start, end, rec) in enumerate(M.rec_slices):
        slice_of[(rec["symbol"], rec["uw_ts"], rec["day"], rec["window"])] = \
            (rid, start, end)

    state = defaultdict(dict)
    prev_ts = {}
    batch_cache = {}
    n = 0
    t0 = time.time()
    for rec in walk_fit_records():
        key = (rec["symbol"], rec["uw_ts"], rec["day"], rec["window"])
        hit = slice_of.get(key)
        if hit is None:
            continue
        rid, start, end = hit
        n += 1
        sym = rec["symbol"]
        ts = rec["uw_ts"]
        grid = [float(s) for s in rec["strikes"]]
        y = [float(v) for v in rec["node_values"]]
        ntypes = rec.get("node_types") or [None] * len(grid)
        exps = rec["expiries"]
        ck = (sym, ts)
        if ck not in batch_cache:
            rows = _rec_to_rows(rec)
            batch = exp.normalize_batch(rows, ts=ts, prev_ts=prev_ts.get(sym),
                                        spot=rec.get("spot"))
            w = exp.cross_expiry_weights(batch, state[sym])
            state[sym] = dict(w)
            prev_ts[sym] = ts
            batch_cache[ck] = (w, batch["rows"])
        w, batch_rows = batch_cache[ck]

        g_cols = defaultdict(lambda: defaultdict(float))
        for row in batch_rows:
            g_cols[row["expiry_date"]][row["strike"]] += exp.net_gex(row)

        h_models = {"g_baseline": dict(g_cols)}
        if theta is not None:
            cols = [FEAT_INDEX[f] for f in sel]
            Xs = (M.feats[start:end][:, cols].astype(np.float64) - means) / norms
            hv = Xs @ theta
            i_idx, j_idx = M.rec_ij[rid]
            th_cols = defaultdict(lambda: defaultdict(float))
            for k in range(len(hv)):
                th_cols[exps[j_idx[k]]][grid[i_idx[k]]] += float(hv[k])
            h_models[f"theta_{group}"] = dict(th_cols)

        for m in models:
            h_cols = h_models[m]
            v_full = defaultdict(float)
            for e, cm in h_cols.items():
                ae = w.get(e, 0.0)
                if ae == 0.0:
                    continue
                for s, val in cm.items():
                    v_full[s] += ae * val
            sc = _score_v(v_full, y, grid, ntypes, sym)
            if sc is None:
                continue
            st = stats[m]
            st["n"] += 1
            st["exact"] += sc["king_exact"]
            st["tol"] += sc["king_within_tol"]
            st["top6"] += sc["top6_overlap"]
            st["apes"].append(sc["node_med_ape"])
            for mode in ("free", "joint"):
                aw = _oracle_weights_h(h_cols, grid, rec["cells"], y, exps,
                                       mode)
                vo = defaultdict(float)
                for e, cm in h_cols.items():
                    ae = aw.get(e, 0.0)
                    if ae == 0.0:
                        continue
                    for s, val in cm.items():
                        vo[s] += ae * val
                so = _score_v(vo, y, grid, ntypes, sym)
                if so:
                    st[f"oracle_{mode}_exact"] += so["king_exact"]
                    st[f"oracle_{mode}_tol"] += so["king_within_tol"]
        if n % 200 == 0:
            print(f"  ... {n} records, {time.time()-t0:.0f}s", flush=True)

    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "script": "scripts/e06_cell_model.py eval", "group": group,
           "n_records": n,
           "theta_insample_caveat": "theta fit on ALL days (cell_theta.json "
                                    "full fit) -- upper bound of the shape "
                                    "bet on this set; LODO cos2 in "
                                    "cell_theta.json is the honest number",
           "models": {}}
    for m, st in stats.items():
        nn = max(st["n"], 1)
        apes = [a for a in st["apes"] if a is not None]
        out["models"][m] = {
            "n": st["n"],
            "node_med_ape_p50": round(float(np.median(apes)), 4) if apes else None,
            "node_med_ape_p90": round(float(np.percentile(apes, 90)), 4) if apes else None,
            "king_exact_rate": round(st["exact"] / nn, 4),
            "king_within_tol_rate": round(st["tol"] / nn, 4),
            "top6_overlap_mean": round(st["top6"] / nn, 4),
            "oracle_free_exact_rate": round(st["oracle_free_exact"] / nn, 4),
            "oracle_free_within_tol_rate": round(st["oracle_free_tol"] / nn, 4),
            "oracle_joint_exact_rate": round(st["oracle_joint_exact"] / nn, 4),
            "oracle_joint_within_tol_rate": round(st["oracle_joint_tol"] / nn, 4),
        }
    print(json.dumps(out["models"], indent=1))
    print("\npublished pins: g basis king 35.42%/83.32% (gamma=0.7 psi), "
          "oracle_free 40.86%, oracle_joint 68.60%")
    if execute:
        path = os.path.join(OUT_DIR, f"eval_models_{group}.json")
        _jdump(out, path)
        print("written:", path)
    else:
        print("(dry-run; pass --execute to write)")
    return 0


def _rec_to_rows(rec):
    rows = []
    fk = ("net_gex", "call_gex", "put_gex", "call_oi", "put_oi",
          "call_volume", "put_volume", "call_ask_vol", "call_bid_vol",
          "put_ask_vol", "put_bid_vol", "call_prev_oi", "put_prev_oi", "iv")
    for strike_s, emap in rec["uw"].items():
        for expiry, feats in emap.items():
            if len(feats) < len(fk):
                continue
            row = {"strike": float(strike_s), "expiry_date": expiry}
            for i, key in enumerate(fk[1:-1], start=1):
                row[key] = float(feats[i]) if feats[i] is not None else 0.0
            rows.append(row)
    return rows


def cmd_verify() -> int:
    bad = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "backend")):
        for fn in files:
            if fn.endswith(".py"):
                p = os.path.join(root, fn)
                src = open(p).read()
                for token in ("SignalForge", "signalforge"):
                    if token in src and "clean-room" not in src.lower():
                        bad.append((p, token))
    print("import-scan issues:", bad or "none")
    ok = not bad
    for fn in ("feature_cos2.json", "cell_theta.json", "eval_models_all.json"):
        p = os.path.join(OUT_DIR, fn)
        ex = os.path.exists(p)
        print(f"artifact {fn}: {'OK' if ex else 'MISSING'}")
        ok = ok and ex
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["features", "fit", "eval", "verify"])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--group", default="all")
    args = ap.parse_args()
    if args.command == "features":
        return cmd_features(args.execute)
    if args.command == "fit":
        return cmd_fit(args.execute)
    if args.command == "eval":
        return cmd_eval(args.execute, args.group)
    return cmd_verify()


if __name__ == "__main__":
    sys.exit(main())
