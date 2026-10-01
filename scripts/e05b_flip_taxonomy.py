#!/usr/bin/env python3
"""E0.5b king-parity flip taxonomy (card E0.5b, gap G2).

Classifies every king argmax miss of the E0.3 model on the Tier-A set into a
mechanism taxonomy, all counts traceable to real script runs:

  exact               P == T
  near_tie_intrinsic  their own surface ties T and P (y(T) >= 0.9 * y(P))
  near_tie_ours       our surface ties T and P  (o(T) >= 0.9 * o(P))
  sign_cancellation   gross mass |a_e g| at T >= at P but net |V| at T < at P
                      (the mass is there and cancels -> a_e sign structure wrong)
  expiry_mislocal     gross mass at P > at T (cross-expiry magnitudes put the
                      mass on the wrong strike); sub-flag: dominant expiry at P
                      (argmax_e |a_e g(P,e)|) vs their dominant expiry at T
                      (argmax_e |C_sk(T,e)|) -- driver-column mismatch
  far_other           residual

Diagnostics per record (also emitted per-row CSV):
  - |P - T| in strike units and tol units (tol = 25 SPX / 5 others, spec 3.3)
  - sign agreement of our LS-scaled value vs theirs at T and at P
  - per-expiry contributions at T and P (ours), Skylit cells at T and P
  - a_e magnitude spread (max/min nonzero |a_e| over the batch's expiries)

Value-level definition: king = argmax_s |V(s)| over the Skylit grid strikes,
V(s) = sum_e a_e * g(s,e) (spec 2). The taxonomy uses OUR per-expiry
contributions a_e*g (mechanism inside V) rather than post-hoc labels.

Usage:
  python3 scripts/e05b_flip_taxonomy.py taxonomy                # -> data/e05b/
  python3 scripts/e05b_flip_taxonomy.py taxonomy --out data/e05b/before_check
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import e03_batch_harness as h  # noqa: E402
from backend.core import exposure as exp  # noqa: E402

FITSET_DIR = h.FITSET_DIR
DEFAULT_OUT = os.path.join(REPO, "data", "e05b")
TOL = h.KING_TOL
TOL_DEFAULT = h.KING_TOL_DEFAULT
NEAR_TIE_FRAC = 0.9


def _jgzload(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def load_instants():
    index = h.load_index()
    return sorted(index["instants"], key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))


def per_expiry_contribs(batch, weights, strike):
    """a_e * g(strike, e) per expiry for one strike (0.0 where no row)."""
    out = defaultdict(float)
    for row in batch["rows"]:
        if abs(row["strike"] - strike) < 1e-9:
            out[row["expiry_date"]] += weights.get(row["expiry_date"], 0.0) * exp.net_gex(row)
    return dict(out)


def classify(rec, T, P, y, o, contrib_T, contrib_P, cells_T, cells_P, tol):
    """Return (class, details). y/o are per-grid-strike dicts; T/P floats."""
    yT, yP = abs(y.get(T, 0.0)), abs(y.get(P, 0.0))
    oT, oP = abs(o.get(T, 0.0)), abs(o.get(P, 0.0))
    gross_T = sum(abs(v) for v in contrib_T.values())
    gross_P = sum(abs(v) for v in contrib_P.values())
    dom_e_ours = max(contrib_P.items(), key=lambda kv: abs(kv[1]))[0] if contrib_P else None
    dom_e_sk_T = max(cells_T.items(), key=lambda kv: abs(kv[1]))[0] if cells_T else None
    dom_e_sk_P = max(cells_P.items(), key=lambda kv: abs(kv[1]))[0] if cells_P else None
    details = {
        "y_T": yT, "y_P": yP, "o_T": oT, "o_P": oP,
        "gross_T": gross_T, "gross_P": gross_P,
        "dom_expiry_ours_P": dom_e_ours,
        "dom_expiry_sk_T": dom_e_sk_T,
        "dom_expiry_sk_P": dom_e_sk_P,
        "driver_mismatch": bool(dom_e_ours and dom_e_sk_T and dom_e_ours != dom_e_sk_T),
    }
    if T == P:
        return "exact", details
    # their own surface ties the pair: |y(P)| >= 0.9 * |y(T)| (note T is their
    # argmax so y(T) >= y(P) by construction -- the ratio must read P vs T)
    if yT > 0 and yP >= NEAR_TIE_FRAC * yT:
        return "near_tie_intrinsic", details
    if oP > 0 and oT >= NEAR_TIE_FRAC * oP:
        return "near_tie_ours", details
    if gross_T >= gross_P:
        return "sign_cancellation", details
    return "expiry_mislocal", details


def taxonomy(out_dir: str, gamma: float = exp.MAG_GAMMA) -> int:
    os.makedirs(out_dir, exist_ok=True)
    insts = load_instants()
    weights_cache = {}
    prev_batch_ts = {}
    state = defaultdict(dict)
    rows = []
    n_scored = 0
    n_stale = 0

    for n, e in enumerate(insts, 1):
        path = os.path.join(FITSET_DIR, e["key"].replace("/", "_") + ".json.gz")
        rec = _jgzload(path)
        if h.is_stale_record(rec):
            n_stale += 1
            continue
        sym = rec["symbol"]
        ts = rec["uw_ts"]
        ck = (sym, ts)
        if ck not in weights_cache:
            prev = prev_batch_ts.get(sym)
            batch = exp.normalize_batch(h.rec_to_rows(rec), ts=ts, prev_ts=prev,
                                        spot=rec.get("spot"))
            w = exp.cross_expiry_weights(batch, state[sym], gamma=gamma)
            state[sym] = dict(w)
            weights_cache[ck] = (w, batch)
            prev_batch_ts[sym] = ts
        w, batch = weights_cache[ck]

        out = h.score_record(rec, w)
        if not out["scored"]:
            continue
        n_scored += 1
        strikes = out["strikes"]
        y = dict(zip(strikes, out["v_sk"]))
        o = dict(zip(strikes, out["v_ours"]))
        T, P = out["king_true"], out["king_pred"]
        tol = TOL.get(sym, TOL_DEFAULT)
        contrib_T = per_expiry_contribs(batch, w, T)
        contrib_P = per_expiry_contribs(batch, w, P)
        cells_T, cells_P = {}, {}
        exps = rec["expiries"]
        for j, ee in enumerate(exps):
            for s, crow in zip(strikes, rec["cells"]):
                if abs(s - T) < 1e-9:
                    cells_T[ee] = float(crow[j])
                if abs(s - P) < 1e-9:
                    cells_P[ee] = float(crow[j])
        cls, det = classify(rec, T, P, y, o, contrib_T, contrib_P, cells_T, cells_P, tol)

        nz = [abs(a) for a in w.values() if a != 0.0]
        spread = (max(nz) / min(nz)) if nz and min(nz) > 0 else None
        vhat_T = out["v_hat"][out["strikes"].index(T)]
        vhat_P = out["v_hat"][out["strikes"].index(P)]
        rows.append({
            "key": e["key"], "symbol": sym, "day": rec["day"], "uw_ts": ts,
            "king_true": T, "king_pred": P,
            "err_strike": P - T, "err_tol_units": abs(P - T) / tol,
            "class": cls,
            "sign_agree_T": (vhat_T * y.get(T, 0.0)) > 0,
            "sign_agree_P": (vhat_P * y.get(P, 0.0)) > 0,
            "c_scale": out["c_scale"],
            "a_spread": spread,
            **det,
        })
        if n % 300 == 0:
            print(f"  ... {n}/{len(insts)} ({n_scored} scored)", flush=True)

    per_rec = os.path.join(out_dir, "flip_taxonomy_per_record.csv")
    with open(per_rec, "w", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wcsv.writeheader()
        wcsv.writerows(rows)

    # ---- aggregates
    def agg(rs):
        c = Counter(r["class"] for r in rs)
        return {"n": len(rs), **{k: c.get(k, 0) for k in
                ("exact", "near_tie_intrinsic", "near_tie_ours", "sign_cancellation",
                 "expiry_mislocal", "far_other")},
                "exact_rate": round(c.get("exact", 0) / max(len(rs), 1), 4)}

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/e05b_flip_taxonomy.py taxonomy",
        "model": "E0.3 baseline (data/e05b/before outputs + identical weight walk)",
        "psi_magnitude_gamma": gamma,
        "input": "data/e02/fit_dataset (post-refresh, 2026-10-01)",
        "n_scored": n_scored, "n_stale_skipped": n_stale,
        "near_tie_frac": NEAR_TIE_FRAC,
        "tol": {"SPX": 25.0, "default": 5.0},
        "overall": agg(rows),
        "per_symbol": {s: agg([r for r in rows if r["symbol"] == s]) for s in sorted({r["symbol"] for r in rows})},
        "per_day": {d: agg([r for r in rows if r["day"] == d]) for d in sorted({r["day"] for r in rows})},
    }
    # miss-only diagnostics
    misses = [r for r in rows if r["class"] != "exact"]
    for scope, rs in (("misses", misses),):
        if not rs:
            continue
        errs = sorted(r["err_tol_units"] for r in rs)
        summary[scope] = {
            "n": len(rs),
            "err_tol_units_p50": errs[len(errs) // 2],
            "err_tol_units_p90": errs[int(0.9 * (len(errs) - 1))],
            "adjacent_or_same_grid_step": sum(1 for r in rs if abs(r["err_strike"]) <= 1.0) / len(rs),
            "sign_disagree_at_T": sum(1 for r in rs if not r["sign_agree_T"]) / len(rs),
            "driver_mismatch_rate": sum(1 for r in rs if r.get("driver_mismatch")) / len(rs),
            "by_class_err_p50": {
                cl: sorted(r["err_tol_units"] for r in rs if r["class"] == cl)[
                    sum(1 for r in rs if r["class"] == cl) // 2]
                for cl in sorted({r["class"] for r in rs})},
            "by_class_driver_mismatch": {
                cl: round(sum(1 for r in rs if r["class"] == cl and r.get("driver_mismatch"))
                          / max(sum(1 for r in rs if r["class"] == cl), 1), 4)
                for cl in sorted({r["class"] for r in rs})},
        }
        summary["per_symbol_misses"] = {}
        for s in sorted({r["symbol"] for r in rs}):
            srs = [r for r in rs if r["symbol"] == s]
            errs = sorted(r["err_tol_units"] for r in srs)
            summary["per_symbol_misses"][s] = {
                "n": len(srs),
                "err_tol_p50": errs[len(errs) // 2],
                "frac_err_le_1tol": round(sum(1 for r in srs if r["err_tol_units"] <= 1.0) / len(srs), 4),
                "frac_adjacent": round(sum(1 for r in srs if abs(r["err_strike"]) <= 1.0) / len(srs), 4),
                "sign_disagree_T_rate": round(sum(1 for r in srs if not r["sign_agree_T"]) / len(srs), 4),
                "a_spread_p50": sorted(r["a_spread"] for r in srs if r["a_spread"])[len(srs) // 2]
                if any(r["a_spread"] for r in srs) else None,
            }
    # a_e spread overall
    spreads = sorted(r["a_spread"] for r in rows if r["a_spread"])
    if spreads:
        summary["a_magnitude_spread"] = {
            "p50": spreads[len(spreads) // 2], "p90": spreads[int(0.9 * (len(spreads) - 1))],
            "max": spreads[-1],
        }

    out_json = os.path.join(out_dir, "flip_taxonomy.json")
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print(json.dumps(summary, indent=1, default=str))
    print(f"\nwrote {out_json}\nwrote {per_rec} ({len(rows)} rows)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_t = sub.add_parser("taxonomy")
    p_t.add_argument("--out", default=DEFAULT_OUT)
    p_t.add_argument("--gamma", type=float, default=exp.MAG_GAMMA,
                     help="psi magnitude temper (E0.5b); 1.0 = pre-E0.5b model")
    args = ap.parse_args()
    if args.cmd == "taxonomy":
        return taxonomy(args.out, args.gamma)
    return 2


if __name__ == "__main__":
    sys.exit(main())
