#!/usr/bin/env python3
"""E0.6 accumulation features from leandata (read-only) + cell-shape probe.

Judge directive 2026-10-01 (goal re-check): pursue within-cell shape /
accumulation features from UW data and our own history (leandata accumulation
proxies) against the required metrics (within-column R^2 0.089 baseline,
node APE ~1.00, king exact 35.42%).

Feature sources (all read-only, `/Volumes/X10 Pro/leandata/parquet/`, docs:
docs/data/leandata-inventory.md; loader: scripts/read_leandata.py):

- options_minute (SPY/QQQ/IWM/SPX, 2026-09-15 -> 2026-09-25, per-OCC minute
  volume/trade counts): per-(strike, expiry) cumulative interaction history
  -> the "accumulation / history of interaction" doctrine at CELL level.
  Windows END before the Tier-A capture days (09-28/29/30) -> no leakage.
- stock_1min (SPY/QQQ/IWM) / index_minute (SPX): per-strike spot-path
  interaction (touch minutes, crossings, days touched over trailing windows).

Commands:

  python3 scripts/e06_accum_features.py build [--execute]   # -> data/e06/accum/
  python3 scripts/e06_accum_features.py probe [--execute]   # -> data/e06/accum/accum_cos2.json

Clean-room; leandata never written. No secrets.
"""
from __future__ import annotations

import argparse
import glob
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
LEANDATA = os.environ.get("GAMMASUMMIT_LEANDATA_ROOT",
                          "/Volumes/X10 Pro/leandata")
PARQ = os.path.join(LEANDATA, "parquet")
OUT_DIR = os.path.join(REPO, "data", "e06", "accum")
FITSET_DIR = os.path.join(REPO, "data", "e02", "fit_dataset")
UWCACHE_DIR = os.path.join(REPO, "data", "e02", "uw_cache")

SYMS = ("SPY", "QQQ", "IWM", "SPX")
_TOUCH_CACHE = {}
OPT_SINCE = "2026-09-15"      # options_minute coverage start
SPOT_SINCE = "2026-08-01"     # spot-path lookback for touch windows


def _jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)
    os.replace(tmp, path)


def _jgzdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)
    os.replace(tmp, path)


def _jgzload(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def occ_strike(occ: str) -> float:
    """OCC: root(6) + yyMMdd + C/P + strike*1000 (8 digits)."""
    return float(occ[-8:]) / 1000.0


def build_optvol():
    import pyarrow.parquet as pq
    out = {}
    for sym in SYMS:
        p = os.path.join(PARQ, "options_minute", f"ticker={sym}",
                         "year=2026.parquet")
        if not os.path.exists(p):
            print(f"  {sym}: no options_minute file")
            continue
        t0 = time.time()
        tbl = pq.read_table(p, columns=["occ", "expiry", "right", "t", "v", "n"])
        occ = tbl.column("occ").to_pylist()
        exp = tbl.column("expiry").to_pylist()
        right = tbl.column("right").to_pylist()
        ts = tbl.column("t").to_pylist()
        vol = tbl.column("v").to_pylist()
        ntr = tbl.column("n").to_pylist()
        agg = {}
        for i in range(len(occ)):
            t = str(ts[i])
            if t < OPT_SINCE:
                continue
            key = (occ_strike(occ[i]), str(exp[i]))
            a = agg.setdefault(key, {"vol_c": 0.0, "vol_p": 0.0, "n_c": 0.0,
                                     "n_p": 0.0, "days": set(), "last": "",
                                     "vol2d": 0.0})
            v = float(vol[i] or 0.0)
            nn = float(ntr[i] or 0.0)
            if right[i] == "C":
                a["vol_c"] += v
                a["n_c"] += nn
            else:
                a["vol_p"] += v
                a["n_p"] += nn
            a["days"].add(t[:10])
            if t > a["last"]:
                a["last"] = t
            if t >= "2026-09-23":
                a["vol2d"] += v
        rows = {}
        for (s, e), a in agg.items():
            rows[f"{s:g}|{e}"] = [
                round(a["vol_c"], 2), round(a["vol_p"], 2),
                round(a["n_c"], 2), round(a["n_p"], 2),
                len(a["days"]), a["last"][:10], round(a["vol2d"], 2),
            ]
        out[sym] = rows
        print(f"  {sym}: {len(rows)} (strike,expiry) cells from "
              f"{len(occ)} rows in {time.time()-t0:.0f}s")
    return out


def build_spot():
    """Per-symbol minute close path since SPOT_SINCE (2026 files)."""
    import pyarrow.parquet as pq
    out = {}
    for sym in SYMS:
        if sym == "SPX":
            p = os.path.join(PARQ, "index_minute", "ticker=SPX",
                             "year=2026.parquet")
            tcol, ccol = "ts", "c"
        else:
            p = os.path.join(PARQ, "stock_1min", f"ticker={sym}",
                             "year=2026.parquet")
            tcol, ccol = "t", "c"
        if not os.path.exists(p):
            print(f"  {sym}: no spot file")
            continue
        import pyarrow.parquet as pq
        names = pq.read_schema(p).names
        ccol = "c" if "c" in names else "close"
        tcol = tcol if tcol in names else "t" if "t" in names else "ts"
        tbl = pq.read_table(p, columns=[tcol, ccol])
        ts = tbl.column(tcol).to_pylist()
        cl = tbl.column(ccol).to_pylist()
        pts = [(str(t), float(c)) for t, c in zip(ts, cl)
               if t is not None and c is not None and str(t) >= SPOT_SINCE]
        pts.sort()
        out[sym] = pts
        print(f"  {sym}: {len(pts)} spot minutes since {SPOT_SINCE}")
    return out


def cmd_build(execute):
    print("building options_minute per-(strike,expiry) interaction history:")
    ov = build_optvol()
    print("building spot paths:")
    sp = build_spot()
    if execute:
        for sym in ov:
            _jgzdump(ov[sym], os.path.join(OUT_DIR, f"optvol_{sym}.json.gz"))
        for sym in sp:
            _jgzdump(sp[sym], os.path.join(OUT_DIR, f"spot_{sym}.json.gz"))
        _jdump({"generated_at": datetime.now(timezone.utc).isoformat(),
                "script": "scripts/e06_accum_features.py build",
                "optvol_cells": {s: len(v) for s, v in ov.items()},
                "spot_minutes": {s: len(v) for s, v in sp.items()},
                "optvol_window": [OPT_SINCE, "2026-09-25"],
                "spot_window_start": SPOT_SINCE},
               os.path.join(OUT_DIR, "build_manifest.json"))
        print("written:", OUT_DIR)
    else:
        print("(dry-run; pass --execute to write)")
    return 0


# ---------------------------------------------------------------- probe

def _col_stats(t, p, keys, min_n=5):
    order = np.argsort(keys, kind="stable")
    ks = keys[order]
    tc = t[order]
    pc = p[order]
    boundaries = np.flatnonzero(np.diff(ks)) + 1
    starts = np.concatenate(([0], boundaries))
    ends = np.concatenate((boundaries, [len(ks)]))
    c2, sp_ = [], []
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
                sp_.append(float(np.dot(rt, rp)) / den)
    return c2, sp_


def touch_features_np(c_arr, day_codes, strike, band, since_idx):
    """Vectorized: touch minutes / crossings / days touched for one strike.
    c_arr: sorted-close float array; day_codes: int per bar; since_idx: start."""
    seg = c_arr[since_idx:]
    dseg = day_codes[since_idx:]
    mask = np.abs(seg - strike) <= band
    tch = int(mask.sum())
    days = int(np.unique(dseg[mask]).size) if tch else 0
    side = np.sign(seg - strike)
    nz = np.flatnonzero(side)
    cross = 0
    if len(nz) > 1:
        filled = side[nz]
        cross = int((filled[1:] * filled[:-1] < 0).sum())
    return tch, cross, days


def cmd_probe(execute):
    # accumulation maps from build artifacts
    ov = {}
    sp = {}
    for sym in SYMS:
        p = os.path.join(OUT_DIR, f"optvol_{sym}.json.gz")
        if os.path.exists(p):
            ov[sym] = _jgzload(p)
        p = os.path.join(OUT_DIR, f"spot_{sym}.json.gz")
        if os.path.exists(p):
            sp[sym] = _jgzload(p)
    if not ov:
        raise SystemExit("run `build --execute` first")

    files = sorted(glob.glob(os.path.join(FITSET_DIR, "2026*.json.gz")))
    import random
    random.seed(7)
    samp = random.sample(files, min(200, len(files)))

    feats = ("g", "ovol_net", "ovol_total", "ovol_cpimb", "ovol_trades_net",
             "ovol_days", "ovol_last2d", "tch_30d", "cross_30d", "days_tch",
             "g_x_ovol", "abs_g_x_ovol", "ovol_x", "tch7_x")
    acc = {f: [] for f in feats}
    acc_matched = {"g": [], "ovol_total": [], "g_x_ovol": [],
                   "g_plus_ovol_fit": []}
    n_rec = 0
    t0 = time.time()
    for fp in samp:
        rec = json.load(gzip.open(fp, "rt"))
        sym = rec["symbol"]
        if sym not in ov:
            continue
        n_rec += 1
        strikes = [float(s) for s in rec["strikes"]]
        exps = rec["expiries"]
        C = np.array(rec["cells"], dtype=float)
        spot = rec.get("spot") or 0.0
        # uw rows for g
        fn = os.path.join(UWCACHE_DIR, __import__("re").sub(
            r"[^0-9A-Za-z]", "_", f"{rec['uw_ts']}_{sym}") + ".json.gz")
        if not os.path.exists(fn):
            continue
        rows = json.load(gzip.open(fn, "rt"))
        uw = {(float(r["strike"]), r["expiry_date"]): r for r in rows}
        # strike-level touch features (band = half nearest-neighbor gap),
        # vectorized per symbol with day codes + window start indices
        tf = {}
        if sym in sp:
            pts = sp[sym]
            c_arr = np.array([p[1] for p in pts], dtype=np.float64)
            t_list = [p[0] for p in pts]
            day_map = {}
            day_codes = np.array([day_map.setdefault(t[:10], len(day_map))
                                  for t in t_list], dtype=np.int32)
            i30 = int(np.searchsorted(t_list, "2026-08-28"))
            i7 = int(np.searchsorted(t_list, "2026-09-21"))
            for i, s in enumerate(strikes):
                nb = [abs(s - x) for x in (strikes[i - 1] if i else None,
                                           strikes[i + 1]
                                           if i + 1 < len(strikes) else None)
                      if x is not None]
                band = min(nb) / 2 if nb else 2.5
                bkey = round(band, 2)
                ck2 = (sym, s, bkey)
                if ck2 in _TOUCH_CACHE:
                    tf[s] = _TOUCH_CACHE[ck2]
                    continue
                t30, c30, d30 = touch_features_np(c_arr, day_codes, s, band, i30)
                t7, _c7, _d7 = touch_features_np(c_arr, day_codes, s, band, i7)
                tf[s] = (t30, c30, d30, t7)
                _TOUCH_CACHE[ck2] = tf[s]
        for j, e in enumerate(exps):
            c, F = [], {f: [] for f in feats}
            for i, s in enumerate(strikes):
                r = uw.get((s, e))
                if r is None:
                    continue
                o = ov[sym].get(f"{s:g}|{e}")
                t30, c30, d30, t7 = tf.get(s, (0.0, 0.0, 0.0, 0.0))
                g = float(r["call_gex"] or 0) - float(r["put_gex"] or 0)
                ag = float(r["abs_gex"] or 0)
                x = (s - spot) / spot if spot else 0.0
                if o:
                    vc, vp, nc, np_, nd, _last, v2 = o
                    ovol_net = vc - vp
                    ovol_total = vc + vp
                    oimb = (vc - vp) / (vc + vp + 1.0)
                    tnet = nc - np_
                else:
                    ovol_net = ovol_total = oimb = tnet = 0.0
                    nd = v2 = 0
                c.append(float(C[i, j]))
                F["g"].append(g)
                F["ovol_net"].append(ovol_net)
                F["ovol_total"].append(ovol_total)
                F["ovol_cpimb"].append(oimb)
                F["ovol_trades_net"].append(tnet)
                F["ovol_days"].append(float(nd))
                F["ovol_last2d"].append(float(v2))
                F["tch_30d"].append(float(t30))
                F["cross_30d"].append(float(c30))
                F["days_tch"].append(float(d30))
                F["g_x_ovol"].append(g * ovol_total)
                F["abs_g_x_ovol"].append(ag * ovol_total)
                F["ovol_x"].append(ovol_total * x)
                F["tch7_x"].append(float(t7))
            if len([v for v in F["g"] if v != 0]) < 5:
                continue
            ck = np.full(len(c), hash((id(rec), j)) % (1 << 30))
            for f in feats:
                v = np.array(F[f], dtype=float)
                if np.all(v == 0):
                    continue
                c2, _ = _col_stats(np.array(c), v, ck)
                acc[f].extend(c2)
            # matched-subset controls: columns where optvol history EXISTS
            # (any ovol feature nonzero) -- apples-to-apples vs g_x_ovol
            ov_here = np.array(F["ovol_total"], dtype=float)
            if not np.all(ov_here == 0):
                cc = np.array(c)
                g_here = np.array(F["g"], dtype=float)
                ok = ov_here != 0
                if int(ok.sum()) >= 5:
                    ck_m = ck[ok]
                    for key, v in (("g", g_here[ok]),
                                   ("ovol_total", ov_here[ok]),
                                   ("g_x_ovol", g_here[ok] * ov_here[ok])):
                        c2, _ = _col_stats(cc[ok], v, ck_m)
                        acc_matched[key].extend(c2)
                    # 2-feature per-column LS fit (g, ovol_total) -- free
                    # 2D LS per column, then cos^2 of the fitted shape
                    X2 = np.stack([g_here[ok], ov_here[ok]], axis=1)
                    y2 = cc[ok]
                    try:
                        coef, *_ = np.linalg.lstsq(X2, y2, rcond=None)
                        pred = X2 @ coef
                        c2, _ = _col_stats(y2, pred, ck_m)
                        acc_matched["g_plus_ovol_fit"].extend(c2)
                    except np.linalg.LinAlgError:
                        pass
        if n_rec % 50 == 0:
            print(f"  ... {n_rec} records, {time.time()-t0:.0f}s", flush=True)

    def summ(v):
        if not v:
            return None
        a = np.array(v)
        return {"n": int(a.size), "median": round(float(np.median(a)), 4),
                "p25": round(float(np.percentile(a, 25)), 4),
                "p75": round(float(np.percentile(a, 75)), 4)}

    out = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "script": "scripts/e06_accum_features.py probe",
           "n_records": n_rec,
           "definition": "per-(record,expiry) cos^2 with per-column LS scale "
                         "(E0.2 col_r2 definition), mask g!=0, n>=5",
           "baseline_note": "full-set g baseline 0.0941 (feature_cos2.json); "
                            "g on THIS sample listed below for comparability",
           "features": {f: summ(acc[f]) for f in feats},
           "matched_subset_note": "columns where trailing options-vol history "
                                  "exists (any ovol feature nonzero) -- "
                                  "apples-to-apples vs g_x_ovol; "
                                  "g_plus_ovol_fit = PER-COLUMN 2-feature LS "
                                  "= oracle bound of that model class "
                                  "(hindsight coefficients, not shippable)",
           "matched_subset": {k: summ(v) for k, v in acc_matched.items()}}
    for f in feats:
        s = out["features"][f]
        print(f"  {f:16s} {s}")
    print("matched subset (optvol history present):")
    for k, s in out["matched_subset"].items():
        print(f"  {k:16s} {s}")
    if execute:
        path = os.path.join(OUT_DIR, "accum_cos2.json")
        _jdump(out, path)
        print("written:", path)
    else:
        print("(dry-run; pass --execute to write)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["build", "probe"])
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    if args.command == "build":
        return cmd_build(args.execute)
    return cmd_probe(args.execute)


if __name__ == "__main__":
    sys.exit(main())
