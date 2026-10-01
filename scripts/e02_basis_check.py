#!/usr/bin/env python3
"""E0.2 basis-check — within-expiry basis sensitivity on the REAL 1s range frames.

Question: is the residual gap in the cross-expiry layer fit caused by the
weighting layer or by the within-expiry strike-value BASIS? For a bounded set
of range windows (2 per session-day x 4 symbols), fit the aggregate node
surface V(s,t) at 0.2 Hz on per-expiry basis columns and compare joint R^2:

  B1 net_gex   = call_gex - put_gex                      (task-established)
  B2 gross_gex = call_gex + put_gex
  B3 cpflip    = sgn(call_ask>call_bid)*|call_gex| - sgn(put_ask>put_bid)*|put_gex|
                 (verdict-3 sign convention family, fresh data)
  B4 oi_size   = sgn(call_ask>call_bid)*(call_volume+0.5*call_oi)
                 - sgn(put_ask>put_bid)*(put_volume+0.5*put_oi)

Read-only over X10 + data/e02 cache. Writes data/e02/basis_check.json.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
import sys
from collections import defaultdict

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_ROOT = "/Volumes/X10 Pro/gammasummit/t3/re/raw"
OUT = os.path.join(REPO, "data", "e02")
FITSET = os.path.join(OUT, "fit_dataset")

sys.path.insert(0, os.path.join(REPO, "scripts"))
from e02_cross_expiry_fit import (TICKERS, _jgzload, _jload, _jdump, _ts,  # noqa: E402
                                  load_range_file_path)

WINDOWS_PER_DAY = 2
SUBSAMPLE = 5


def build_basis(rec):
    """Return (strikes, exps, dict basis_name -> S x E matrix)."""
    exps = rec["expiries"]
    eidx = {e: j for j, e in enumerate(exps)}
    strikes = [float(x) for x in rec["strikes"]]
    sidx = {s: i for i, s in enumerate(strikes)}
    S, E = len(strikes), len(exps)
    mats = {k: np.zeros((S, E)) for k in ("B1_net_gex", "B2_gross_gex", "B3_cpflip", "B4_oi_size")}
    for st_str, emap in rec["uw"].items():
        i = sidx.get(float(st_str))
        if i is None:
            continue
        for e, f in emap.items():
            j = eidx.get(e)
            if j is None:
                continue
            net, call_g, put_g = f[0], f[1], f[2]
            call_oi, put_oi, call_vol, put_vol = f[3], f[4], f[5], f[6]
            call_ask, call_bid, put_ask, put_bid = f[7], f[8], f[9], f[10]
            flip_c = 1.0 if call_ask > call_bid else -1.0
            flip_p = 1.0 if put_ask > put_bid else -1.0
            mats["B1_net_gex"][i, j] = net
            mats["B2_gross_gex"][i, j] = call_g + put_g
            mats["B3_cpflip"][i, j] = flip_c * abs(call_g) - flip_p * abs(put_g)
            mats["B4_oi_size"][i, j] = (flip_c * (call_vol + 0.5 * call_oi)
                                        - flip_p * (put_vol + 0.5 * put_oi))
    return strikes, exps, mats


def frame_r2(B, vals):
    keep = np.abs(B).sum(axis=0) > 0
    if int(keep.sum()) < 2:
        return None
    Bk = B[:, keep]
    GtG = Bk.T @ Bk
    lam = 1e-3 * float(np.trace(GtG)) / max(1, Bk.shape[1])
    try:
        ah = np.linalg.solve(GtG + lam * np.eye(Bk.shape[1]), Bk.T @ vals)
    except np.linalg.LinAlgError:
        return None
    pred = Bk @ ah
    ss = float(((vals - pred) ** 2).sum())
    st = float(((vals - vals.mean()) ** 2).sum())
    return 1 - ss / st if st > 0 else None


def main():
    idx = _jload(os.path.join(FITSET, "index.json"))
    inst_by = defaultdict(list)
    for e in idx["instants"]:
        inst_by[(e["day"], e["symbol"])].append(e)
    out = {"method": "joint ridge LSQ of V(s,t) on per-expiry basis columns, "
                     "0.2 Hz subsample, g frozen at nearest UW record per window",
           "per_basis_r2": defaultdict(list), "windows": []}
    days = sorted({e["day"] for e in idx["instants"]})
    for day in days:
        for sym in TICKERS:
            recs = inst_by.get((day, sym))
            win_dir = os.path.join(RAW_ROOT, "range", "gamma", day)
            if not recs or not os.path.isdir(win_dir):
                continue
            files = [f for f in sorted(os.listdir(win_dir))
                     if not f.startswith("._") and f.endswith(".json.gz")]
            step = max(1, len(files) // WINDOWS_PER_DAY)
            picked = files[::step][:WINDOWS_PER_DAY]
            for fn in picked:
                rng = load_range_file_path(os.path.join(win_dir, fn))
                sd = rng["symbols"].get(sym)
                if not sd or not sd["frames"]:
                    continue
                wstart = _ts(rng["from"].replace("Z", "+00:00"))
                near = min(recs, key=lambda e: abs((_ts(e["asOf"].replace("Z", "+00:00"))
                                                    - wstart).total_seconds()))
                rec = _jgzload(os.path.join(FITSET, f"{near['key'].replace('/', '_')}.json.gz"))
                strikes, exps, mats = build_basis(rec)
                sidx = {s: i for i, s in enumerate(strikes)}
                per_axis = {}
                for ax in sd["axes"]:
                    pairs = [(ri, sidx[float(s)]) for ri, s in enumerate(ax.get("strikes", []))
                             if float(s) in sidx]
                    if not pairs:
                        continue
                    rows_r = [p[0] for p in pairs]
                    rows_m = [p[1] for p in pairs]
                    per_axis[ax.get("id", 0)] = (rows_r, {k: v[rows_m, :] for k, v in mats.items()})
                if not per_axis:
                    continue
                r2s = defaultdict(list)
                n_frames = 0
                for fi, fr in enumerate(sd["frames"]):
                    if fi % SUBSAMPLE != 0:
                        continue
                    pa = per_axis.get(fr.get("axis", 0))
                    if pa is None:
                        continue
                    rows_r, bmats = pa
                    vals_all = fr.get("values", [])
                    if len(vals_all) <= max(rows_r):
                        continue
                    vals = np.array(vals_all, dtype=float)[rows_r]
                    if float(np.abs(vals).max()) == 0:
                        continue
                    n_frames += 1
                    for k, B in bmats.items():
                        r2 = frame_r2(B, vals)
                        if r2 is not None:
                            r2s[k].append(r2)
                            out["per_basis_r2"][k].append(r2)
                wrec = {"day": day, "symbol": sym, "window": fn, "n_frames": n_frames}
                for k in ("B1_net_gex", "B2_gross_gex", "B3_cpflip", "B4_oi_size"):
                    wrec[k] = round(statistics.median(r2s[k]), 4) if r2s[k] else None
                out["windows"].append(wrec)
                print(wrec, flush=True)
    summary = {}
    for k, v in out["per_basis_r2"].items():
        v = sorted(v)
        summary[k] = {"n_frames": len(v), "r2_median": round(v[len(v) // 2], 4) if v else None,
                      "r2_p25": round(v[len(v) // 4], 4) if v else None,
                      "r2_p75": round(v[3 * len(v) // 4], 4) if v else None}
    out["summary"] = summary
    del out["per_basis_r2"]
    path = os.path.join(OUT, "basis_check.json")
    _jdump(out, path)
    print("wrote", path)
    for k, s in summary.items():
        print(f"  {k}: {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
