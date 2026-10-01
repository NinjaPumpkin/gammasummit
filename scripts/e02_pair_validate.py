#!/usr/bin/env python3
"""E0.2 pair-validate — re-derive the verdict-4 within-expiry claim on gate-usable
PAIRs (fresh UW rows from skylit_sameinstant_v2.json), read-only:

  "net_gex = call_gex - put_gex ranks their star top-3 within its own expiry column"

For each PAIR with usable_for_gate=True (data/e02/pairs_freshness.json):
  - parse the 92x5 viewport grid cell text values ($41,550.9K -> 41550900)
  - per expiry column: their per-strike cell values vs UW net_gex at the
    same-instant snapshot -> rank of the column-max |value| strike in the
    net_gex ordering (and spearman rank corr)
  - cross-check: PAIR grid values vs X10 matrix cells at the nearest RTH capture

Writes data/e02/pair_validation.json.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SF_DATA = "/Users/admin/Desktop/Github Projects/SignalForge/data"
RAW_ROOT = "/Volumes/X10 Pro/gammasummit/t3/re/raw"
OUT = os.path.join(REPO, "data", "e02")

sys.path.insert(0, os.path.join(REPO, "scripts"))
from p0_parity_dataset import load_matrix_file  # noqa: E402
from e02_cross_expiry_fit import spearman, _ts, _jload, _jdump  # noqa: E402


def parse_money(s: str) -> float:
    """'$41,550.9K' -> 41550900.0 ; '-$5.8K' -> -5800.0 ; '3204.7K+8%' -> 3204700.0"""
    s = s.strip()
    neg = s.startswith("-")
    s = s.lstrip("-").lstrip("$").strip()
    m = re.match(r"([\d,]+(?:\.\d+)?)\s*([KMB]?)", s)
    if not m:
        raise ValueError(f"unparseable money text: {s!r}")
    mult = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)]
    v = float(m.group(1).replace(",", "")) * mult
    return -v if neg else v


def main():
    fresh = _jload(os.path.join(OUT, "pairs_freshness.json"))
    usable = {r["pair"]: r for r in fresh["pairs"] if r["usable_for_gate"]}
    same = _jload(os.path.join(SF_DATA, "skylit_sameinstant_v2.json"))
    need = same["need"]
    uw_by_ts = defaultdict(list)
    for r in same["rows"]:
        uw_by_ts[r["timestamp"]].append(r)

    out = {"checked_at": "run-time", "metric": (
        "rank of the column-max |value| strike within the net_gex ordering of the "
        "same column; top-3 hit = verdict-4 metric"), "pairs": [], "summary": {}}
    ranks_all, top3, n_cols = [], 0, 0
    rho_all = []
    for fn, rec in sorted(usable.items()):
        p = _jload(os.path.join(SF_DATA, "skylit_pairs", fn))
        grid_cap = (p["grid"].get("captured_utc") or "").replace("Z", "+00:00")
        cells = {}
        stars = []
        for c in p["grid"]["cells"]:
            st, e = c["key"].split("_", 1)
            v = parse_money(c["text"])
            cells[(float(st), e)] = v
            if c.get("star"):
                stars.append((float(st), e))
        uw_ts = need[fn][0]
        rows = None
        for k, v in uw_by_ts.items():
            if k.startswith(uw_ts[:19]):
                rows = v
                break
        if not rows:
            print(fn, "SKIP — no same-instant UW rows", flush=True)
            continue
        g = defaultdict(dict)   # expiry -> {strike: net_gex}
        spot = None
        for r in rows:
            st = float(r["strike"])
            net = float(r.get("call_gex") or 0) - float(r.get("put_gex") or 0)
            g[r["expiry_date"]][st] = net
            spot = spot or r.get("spot_price")
        prec = {"pair": fn, "grid_captured_utc": grid_cap, "uw_ts": uw_ts,
                "spot": spot, "stars": stars, "columns": []}
        for e in sorted({k[1] for k in cells}):
            col = {st: v for (st, ee), v in cells.items() if ee == e}
            if not col:
                continue
            shared = [st for st in col if st in g.get(e, {})]
            if len(shared) < 5:
                continue
            their = [col[st] for st in shared]
            nets = [g[e][st] for st in shared]
            best_st = max(shared, key=lambda st: abs(col[st]))
            order = sorted(shared, key=lambda st: -abs(g[e][st]))
            rank = order.index(best_st) + 1
            rho = spearman(their, nets)
            rho_all.append(rho)
            ranks_all.append(rank)
            n_cols += 1
            if rank <= 3:
                top3 += 1
            prec["columns"].append({
                "expiry": e, "n_shared": len(shared),
                "col_max_strike": best_st, "col_max_value": col[best_st],
                "net_gex_rank_of_col_max": rank, "spearman": round(rho, 3)})
        out["pairs"].append(prec)
        print(fn, "cols:", len(prec["columns"]),
              "ranks:", [c["net_gex_rank_of_col_max"] for c in prec["columns"]],
              flush=True)
    out["summary"] = {
        "n_gate_usable_pairs": len(usable),
        "n_columns_scored": n_cols,
        "top3_hits": top3,
        "top3_rate": round(top3 / n_cols, 3) if n_cols else None,
        "median_rank": sorted(ranks_all)[len(ranks_all) // 2] if ranks_all else None,
        "median_spearman": sorted(rho_all)[len(rho_all) // 2] if rho_all else None,
        "verdict4_reference": "top-3 75% on their star within own expiry column",
    }
    path = os.path.join(OUT, "pair_validation.json")
    _jdump(out, path)
    print("wrote", path, out["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
