#!/usr/bin/env python3
"""E0.5b king-fix variant sweep (card E0.5b, gap G2).

Value-level correction candidates for the king = argmax|V| selection gap, all
evaluated with the harness scoring rule (grid strikes, tie-break smallest
strike, tol 25 SPX / 5 others) on the Tier-A fit_dataset walk:

  V0 baseline       a_e from spec 3.4 EWMA (exposure.py), g basis
  Vmag(gamma)       a_e <- sgn(a_e)*|a_e|^gamma   (gamma grid; magnitude spread
                    tempering -- our spread p50 11,370x vs their empirical
                    free-weight spread p50 623x, probe4)
  Vclip(R)          |a_e| spread clipped to max/min <= R (R grid)
  Vbasis(cpflip)    within-cell basis B3 (e02_basis_check cpflip def)
  Vbasis(oi_size)   within-cell basis B4
  Vsign(x)          column sign: net_col (normative) | always_pos |
                    cpflip_sum | flow_net
  Vfree             ORACLE per-record per-column LS weights vs their cells
                    (NOT shippable -- upper bound)
  Vjoint            ORACLE per-record joint LS weights vs their node values
                    (NOT shippable -- upper bound for ANY a_e model on the
                    given within-cell basis)

Usage:
  python3 scripts/e05b_king_fix.py sweep --out data/e05b/sweep.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import e03_batch_harness as h  # noqa: E402
from backend.core import exposure as exp  # noqa: E402

FITSET_DIR = h.FITSET_DIR
TOL = h.KING_TOL
TOL_DEFAULT = h.KING_TOL_DEFAULT


def _jgzload(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


# ---------------------------------------------------------------- bases
def cell_basis(row, basis):
    """Within-cell g-type value for one UW row under a named basis."""
    if basis == "net_gex":
        return exp.net_gex(row)
    if basis == "cpflip":
        flip_c = 1.0 if row["call_ask_vol"] > row["call_bid_vol"] else -1.0
        flip_p = 1.0 if row["put_ask_vol"] > row["put_bid_vol"] else -1.0
        return flip_c * abs(row["call_gex"]) - flip_p * abs(row["put_gex"])
    if basis == "oi_size":
        flip_c = 1.0 if row["call_ask_vol"] > row["call_bid_vol"] else -1.0
        flip_p = 1.0 if row["put_ask_vol"] > row["put_bid_vol"] else -1.0
        return (flip_c * (row["call_volume"] + 0.5 * row["call_oi"])
                - flip_p * (row["put_volume"] + 0.5 * row["put_oi"]))
    raise ValueError(basis)


def column_sign(col, mode):
    if mode == "net_col":
        return 1.0 if col["net"] >= 0 else -1.0
    if mode == "always_pos":
        return 1.0
    if mode == "cpflip_sum":
        return 1.0 if col["cpflip"] >= 0 else -1.0
    if mode == "flow_net":
        return 1.0 if col["flow"] >= 0 else -1.0
    raise ValueError(mode)


def mag_map(a, mode, param):
    """Magnitude correction on one |a_e| (sign preserved outside)."""
    if mode == "none":
        return abs(a)
    if mode == "pow":
        return abs(a) ** param
    raise ValueError(mode)


def clip_spread(mags, cap):
    """Scale mags (list of nonnegative) so max/min <= cap (min>0 assumed)."""
    if not mags:
        return mags
    lo, hi = min(mags), max(mags)
    if lo > 0 and hi / lo > cap:
        # compress multiplicatively around the geometric mean
        import math
        gm = math.exp(sum(math.log(m) for m in mags) / len(mags))
        lo2, hi2 = gm / (cap ** 0.5), gm * (cap ** 0.5)
        out = []
        for m in mags:
            if m < lo2:
                out.append(lo2)
            elif m > hi2:
                out.append(hi2)
            else:
                out.append(m)
        return out
    return mags


# ---------------------------------------------------------------- walk
def walk_records():
    insts = sorted(h.load_index()["instants"], key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))
    prev_ts, state = {}, defaultdict(dict)
    batch_cache = {}
    for e in insts:
        rec = _jgzload(os.path.join(FITSET_DIR, e["key"].replace("/", "_") + ".json.gz"))
        if h.is_stale_record(rec):
            continue
        sym, ts = rec["symbol"], rec["uw_ts"]
        ck = (sym, ts)
        if ck not in batch_cache:
            batch = exp.normalize_batch(h.rec_to_rows(rec), ts=ts, prev_ts=prev_ts.get(sym),
                                        spot=rec.get("spot"))
            w = exp.cross_expiry_weights(batch, state[sym])
            state[sym] = dict(w)
            # raw psi + column aggregates for variant construction
            cols = {}
            for row in batch["rows"]:
                ee = row["expiry_date"]
                col = cols.setdefault(ee, defaultdict(float))
                g = exp.net_gex(row)
                col["net"] += g
                col["flow"] += ((row["call_ask_vol"] - row["call_bid_vol"])
                                - (row["put_ask_vol"] - row["put_bid_vol"]))
                flip_c = 1.0 if row["call_ask_vol"] > row["call_bid_vol"] else -1.0
                flip_p = 1.0 if row["put_ask_vol"] > row["put_bid_vol"] else -1.0
                col["cpflip"] += flip_c * abs(row["call_gex"]) - flip_p * abs(row["put_gex"])
            batch_cache[ck] = (batch, w, cols)
            prev_ts[sym] = ts
        yield rec, ck, batch_cache[ck]


def per_expiry_strikes(batch, basis):
    """{expiry: {strike: value}} summed over rows (per batch)."""
    out = defaultdict(lambda: defaultdict(float))
    for row in batch["rows"]:
        out[row["expiry_date"]][row["strike"]] += cell_basis(row, basis)
    return out


def king_of(v_full, grid):
    """argmax |V| over grid strikes with harness tie-break (smallest strike)."""
    best, best_i = None, None
    for i, s in enumerate(grid):
        v = v_full.get(s, 0.0)
        key = (abs(v), -s)
        if best is None or key > best:
            best, best_i = key, s
    return best_i


def oracle_weights(rec, batch, grid, mode, basis):
    """Per-record per-expiry LS weights vs their cells (free) or node values
    (joint) over the grid strikes. Uses THEIR numbers -- bound only."""
    exps = rec["expiries"]
    cells = rec["cells"]
    y = [float(v) for v in rec["node_values"]]
    es = per_expiry_strikes(batch, basis)
    cols_map = {e: es.get(e, {}) for e in exps}
    if mode == "free":
        a = {}
        for j, e in enumerate(exps):
            num = den = 0.0
            cm = cols_map[e]
            for i, s in enumerate(grid):
                g = cm.get(s, 0.0)
                num += float(cells[i][j]) * g
                den += g * g
            a[e] = num / den if den > 0 else 0.0
        return a
    # joint: normal equations on grid strikes, tiny ridge for stability.
    # Rows are sparse (a strike carries only a few expiries) -> iterate nonzeros.
    E = len(exps)
    xtx = [[0.0] * E for _ in range(E)]
    xty = [0.0] * E
    for i, s in enumerate(grid):
        row = [(j, cols_map[e].get(s, 0.0)) for j, e in enumerate(exps)]
        row = [(j, v) for j, v in row if v != 0.0]
        if not row:
            continue
        yi = y[i]
        for j1, r1 in row:
            xty[j1] += r1 * yi
            for j2, r2 in row:
                xtx[j1][j2] += r1 * r2
    # gaussian elimination (tiny ridge on the diagonal for stability)
    for j in range(E):
        xtx[j][j] += 1e-9
    M = [xtx[i] + [xty[i]] for i in range(E)]
    for i in range(E):
        piv = max(range(i, E), key=lambda r: abs(M[r][i]))
        M[i], M[piv] = M[piv], M[i]
        if abs(M[i][i]) < 1e-300:
            continue
        for r in range(E):
            if r == i:
                continue
            f = M[r][i] / M[i][i]
            for c in range(i, E + 1):
                M[r][c] -= f * M[i][c]
    a = {}
    for j, e in enumerate(exps):
        a[e] = (M[j][E] / M[j][j]) if abs(M[j][j]) > 1e-300 else 0.0
    return a


def sweep(out_path: str) -> int:
    variants = []
    variants.append({"name": "V0_baseline", "mag": "none", "sign": "net_col"})
    for g in (0.0, 0.25, 0.5, 0.7, 0.85):
        variants.append({"name": f"Vmag_pow{g}", "mag": "pow", "mag_param": g, "sign": "net_col"})
    for r in (13.3, 50.0, 623.0, 3740.0):
        variants.append({"name": f"Vclip_{r}", "mag": "none", "sign": "net_col", "clip": r})
    for b in ("cpflip", "oi_size"):
        variants.append({"name": f"Vbasis_{b}", "mag": "none", "sign": "net_col", "basis": b})
        variants.append({"name": f"Vbasis_{b}_pow0.5", "mag": "pow", "mag_param": 0.5,
                         "sign": "net_col", "basis": b})
    variants.append({"name": "Vsign_cpflip", "mag": "none", "sign": "cpflip_sum"})
    variants.append({"name": "Vsign_flow", "mag": "none", "sign": "flow_net"})
    variants.append({"name": "V0_pow0.7_clip623", "mag": "pow", "mag_param": 0.7,
                     "sign": "net_col", "clip": 623.0})
    variants.append({"name": "ORACLE_free", "oracle": "free", "basis": "net_gex"})
    variants.append({"name": "ORACLE_joint", "oracle": "joint", "basis": "net_gex"})
    variants.append({"name": "ORACLE_free_cpflip", "oracle": "free", "basis": "cpflip"})
    variants.append({"name": "ORACLE_joint_cpflip", "oracle": "joint", "basis": "cpflip"})

    stats = {v["name"]: {"n": 0, "exact": 0, "tol": 0,
                         "per_symbol": defaultdict(lambda: [0, 0, 0]),
                         "per_day": defaultdict(lambda: [0, 0, 0])} for v in variants}

    n = 0
    for rec, ck, (batch, w_norm, cols) in walk_records():
        n += 1
        sym = rec["symbol"]
        grid = [float(s) for s in rec["strikes"]]
        y = [float(v) for v in rec["node_values"]]
        ntypes = rec.get("node_types") or [None] * len(grid)
        ki = next((i for i, t in enumerate(ntypes) if t == "king"), None)
        if ki is None:
            ki = max(range(len(grid)), key=lambda i: (abs(y[i]), -grid[i]))
        T = grid[ki]
        tol = TOL.get(sym, TOL_DEFAULT)
        day = rec["day"]

        bases_needed = {v.get("basis", "net_gex") for v in variants}
        es = {b: per_expiry_strikes(batch, b) for b in bases_needed}

        # raw psi per expiry rebuilt from normative weights? need psi sign+magnitude
        # -- use the same recursion output w_norm for 'none' magnitude variants and
        # rebuild magnitudes from |psi| for pow variants: a = sgn(w)*|psi|^g is NOT
        # the EWMA; instead temper the CURRENT a_e (post-EWMA) -- that is the
        # honest object feeding V.
        for v in variants:
            name = v["name"]
            if v.get("oracle"):
                basis = v.get("basis", "net_gex")
                a = oracle_weights(rec, batch, grid, v["oracle"], basis)
                emap = es[basis]
            else:
                basis = v.get("basis", "net_gex")
                emap = es[basis]
                a = dict(w_norm)
                if v.get("mag") == "pow":
                    p = v["mag_param"]
                    a = {e: (1.0 if x > 0 else (-1.0 if x < 0 else 0.0)) * (abs(x) ** p)
                         for e, x in a.items()}
                if v.get("clip") is not None:
                    nz = {e: x for e, x in a.items() if x != 0.0}
                    mags = clip_spread([abs(x) for x in nz.values()], v["clip"])
                    a = dict(a)
                    for (e, x), m in zip(nz.items(), mags):
                        a[e] = (1.0 if x > 0 else -1.0) * m
                if v.get("sign"):
                    sgmode = v["sign"]
                    if sgmode != "net_col":
                        a = dict(a)
                        for e, x in a.items():
                            col = cols.get(e)
                            if col is not None and x != 0.0:
                                a[e] = column_sign(col, sgmode) * abs(x)
            v_full = defaultdict(float)
            for e, cm in emap.items():
                ae = a.get(e, 0.0)
                if ae == 0.0:
                    continue
                for s, val in cm.items():
                    v_full[s] += ae * val
            P = king_of(v_full, grid)
            if P is None:
                continue
            st = stats[name]
            st["n"] += 1
            ex = (P == T)
            wt = abs(P - T) <= tol
            st["exact"] += ex
            st["tol"] += wt
            for key, dd in (("per_symbol", sym), ("per_day", day)):
                slot = st[key][dd]
                slot[0] += 1
                slot[1] += ex
                slot[2] += wt
        if n % 200 == 0:
            print(f"  ... {n} records", flush=True)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/e05b_king_fix.py sweep",
        "n_records": n,
        "variants": {},
    }
    for v in variants:
        name = v["name"]
        st = stats[name]
        out["variants"][name] = {
            "config": {k: val for k, val in v.items() if k != "name"},
            "n": st["n"],
            "king_exact_rate": round(st["exact"] / max(st["n"], 1), 4),
            "king_within_tol_rate": round(st["tol"] / max(st["n"], 1), 4),
            "per_symbol": {s: {"n": c[0], "exact_rate": round(c[1] / max(c[0], 1), 4),
                               "tol_rate": round(c[2] / max(c[0], 1), 4)}
                           for s, c in sorted(st["per_symbol"].items())},
            "per_day": {d: {"n": c[0], "exact_rate": round(c[1] / max(c[0], 1), 4),
                            "tol_rate": round(c[2] / max(c[0], 1), 4)}
                        for d, c in sorted(st["per_day"].items())},
        }
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(json.dumps({k: (v["king_exact_rate"], v["king_within_tol_rate"])
                      for k, v in out["variants"].items()}, indent=1))
    print(f"wrote {out_path}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sweep")
    p.add_argument("--out", default=os.path.join(REPO, "data", "e05b", "sweep.json"))
    args = ap.parse_args()
    return sweep(args.out)


if __name__ == "__main__":
    sys.exit(main())
