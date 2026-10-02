#!/usr/bin/env python3
"""E0.7 scratch probe — which score variant tracks WHICH Skylit surface?

Variants (all computable from UW PHX features in uw_features_<date>.json):
  premium       day premium percentile only
  unusual       mean pct of [vol_oi, oi_change_pct, rvol, prem_pct_vs_base, ask_share]
  score_v0      mean pct of all 8 features (as built in e07_uw_features.py)
  prem_x_unus   0.5*premium_pct + 0.5*unusual_pct  (two-axis blend)
  prem_then_un  premium rank primary, unusualness tiebreak within +-5 rank band

Ground truths: top_tickers_premium (A), unusual sets (B), attention (C).
"""
from __future__ import annotations

import json
import os

E07 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "e07")
SK = os.path.join(E07, "skylit_api")
DATES = ["2026-09-29", "2026-09-30", "2026-10-01"]


def pct_rank(vals):
    items = sorted((v, t) for t, v in vals.items() if v is not None)
    n = len(items)
    return {t: (i / (n - 1) if n > 1 else 0.5) for i, (_, t) in enumerate(items)}


def pr(pred, truth, k):
    top = pred[:k]
    hits = sum(1 for t in top if t in truth)
    return hits / len(top) if top else 0, hits / len(truth) if truth else 0, hits


for D in DATES:
    uf = json.load(open(os.path.join(E07, f"uw_features_{D}.json")))
    rows = [r for r in uf["ranked"] if r.get("score_v0") is not None]
    F = {r["ticker"]: r for r in rows}

    prem_pct = pct_rank({t: f["premium"] for t, f in F.items()})
    un_keys = ["vol_oi", "oi_change_pct", "rvol", "prem_pct_vs_base", "ask_share"]
    un_pct = {}
    for k in un_keys:
        m = pct_rank({t: f[k] for t, f in F.items() if f.get(k) is not None})
        for t, v in m.items():
            un_pct.setdefault(t, []).append(v)
    un_pct = {t: sum(v) / len(v) for t, v in un_pct.items()}

    prem_rank = sorted(F, key=lambda t: -(prem_pct.get(t, -1)))
    un_rank = sorted(F, key=lambda t: -(un_pct.get(t, -1)))
    v0_rank = sorted(F, key=lambda t: -(F[t]["score_v0"] or -1))
    blend = {t: 0.5 * prem_pct.get(t, 0) + 0.5 * un_pct.get(t, 0) for t in F}
    blend_rank = sorted(F, key=lambda t: -blend[t])
    # premium primary with unusualness re-rank inside +-5 band
    band = []
    i = 0
    order = prem_rank
    while i < len(order):
        j = min(i + 5, len(order))
        chunk = sorted(order[i:j], key=lambda t: -(un_pct.get(t, -1)))
        band += chunk
        i = j
    band_rank = band

    A = {r["ticker"] for r in json.load(open(f"{SK}/{D}_top_tickers_premium.json"))["data"]}
    B = {r["ticker"] for r in json.load(open(f"{SK}/{D}_unusual_volume.json"))["data"]} | \
        {r["ticker"] for r in json.load(open(f"{SK}/{D}_unusual_oi.json"))["data"]}
    C = set(list(A)[:25]) | B

    print(f"== {D}  (UW n={len(F)}, |A|={len(A)}, |B|={len(B)}, |C|={len(C)})")
    for name, rank in [("premium", prem_rank), ("unusual", un_rank), ("score_v0", v0_rank),
                       ("prem_x_unus", blend_rank), ("prem_band_unus", band_rank)]:
        line = f"  {name:14s}"
        for tname, truth in (("A", A), ("B", B), ("C", C)):
            for k in (25, 50, 100):
                p, r, h = pr(rank, truth, k)
                line += f"  {tname}@{k}: P{p:.2f}/R{r:.2f}"
        print(line)
