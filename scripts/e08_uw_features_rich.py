#!/usr/bin/env python3
"""E0.8 — richer UW per-ticker features for the E0.7 replay days (clean-room).

Extends scripts/e07_uw_features.py's feature set with the H1/H2 contract-level
aggregates from top_chains (censored top-15 capture — see
data/e08/h1h2_backtest_report.md) and writes files in the SAME shape e07_validate.py
consumes, so the validation harness can be re-run with --rank-field variants:

  score_h1       0.5*pct(n_flag_rvol) + 0.5*pct(n_flag_oi)   (H1 overlay-union proxy)
  score_h2       premium percentile vs own trailing 20d       (H2 surprise score)
  score_v0_rich  mean of available cross-sectional pct ranks over the richer
                 feature set (premium, volume, contracts, ask_share, rvol_cens_max,
                 n_flag_rvol, n_flag_oi, oi_abs_sum, prem_pctile_20d)

Inputs: data/e08/topchains_<date>.json caches written by e08_h1h2_backtest.py
(UW PHX top_chains, deduped per option_symbol; both sorts).
Outputs: data/e08/uw_features_rich_<date>.json

Usage:
  python3 scripts/e08_uw_features_rich.py --dates 2026-09-29 2026-09-30 2026-10-01
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E08 = os.path.join(ROOT, "data", "e08")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from e08_h1h2_backtest import ContractHist, norm_occ  # noqa: E402


def load_cached_days() -> dict[str, list[dict]]:
    out = {}
    for fn in sorted(glob.glob(os.path.join(E08, "topchains_*.json"))):
        day = os.path.basename(fn)[len("topchains_"):-len(".json")]
        rows = json.load(open(fn))
        for r in rows:
            r["date"] = day
            r["occ"] = norm_occ(r.get("option_symbol") or "")
            r["volume"] = float(r.get("volume") or 0)
            r["premium"] = float(r.get("avg_price") or 0) * float(r.get("volume") or 0) * 100.0
            r["oi"] = float(r.get("open_interest") or 0)
            r["prev_oi"] = float(r.get("prev_oi") or 0)
        out[day] = rows
    return out


def pct(values: dict[str, float]) -> dict[str, float]:
    items = sorted((v, t) for t, v in values.items() if v is not None)
    n = len(items)
    return {t: (i / (n - 1)) if n > 1 else 0.5 for i, (_, t) in enumerate(items)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="+", required=True)
    args = ap.parse_args()

    days = load_cached_days()
    all_days = sorted(days)
    print(f"cached top_chains days: {len(all_days)} ({all_days[0]}..{all_days[-1]})", file=sys.stderr)

    for D in args.dates:
        if D not in days:
            raise SystemExit(f"missing cache for {D} — run scripts/e08_h1h2_backtest.py first")
        prior = [d for d in all_days if d < D][-25:]
        rows_all = [r for d in prior + [D] for r in days[d]]

        by_occ: dict[str, list[dict]] = defaultdict(list)
        for r in rows_all:
            by_occ[r["occ"]].append(r)

        # contract-level flags on D
        flags = []
        for occ, rs in by_occ.items():
            rs.sort(key=lambda r: r["date"])
            rs = [r for r in rs if r["date"] <= D]
            if not rs or rs[-1]["date"] != D:
                continue
            flags.append(ContractHist.flags(rs, D, min_base_obs=5, with_oi=True))

        occ2tk = {r["occ"]: r["ticker"] for r in days[D]}
        feats: dict[str, dict] = defaultdict(lambda: {
            "premium": 0.0, "volume": 0.0, "n_contracts": 0, "ask": 0.0, "bid": 0.0, "mid": 0.0,
            "rvol_cens_max": 0.0, "n_flag_rvol": 0, "n_flag_oi": 0, "oi_abs_sum": 0.0,
            "h2_max": 0.0,
        })
        for r in days[D]:
            a = feats[r["ticker"]]
            a["premium"] += r["premium"]
            a["volume"] += r["volume"]
            a["n_contracts"] += 1
            a["ask"] += float(r.get("ask_volume") or 0)
            a["bid"] += float(r.get("bid_volume") or 0)
            a["mid"] += float(r.get("mid_volume") or 0)
        for f in flags:
            tk = occ2tk.get(f["occ"])
            if tk is None:
                continue
            a = feats[tk]
            if f["rvol"] == f["rvol"] and f["rvol"] != float("inf"):
                a["rvol_cens_max"] = max(a["rvol_cens_max"], f["rvol"])
            a["n_flag_rvol"] += 1 if f["flag_rvol"] else 0
            a["n_flag_oi"] += 1 if f.get("flag_oi") else 0
            a["oi_abs_sum"] += abs(f.get("oi_change") or 0.0)
            if f["prem_pctile_20d"] == f["prem_pctile_20d"]:
                a["h2_max"] = max(a["h2_max"], f["prem_pctile_20d"])

        # ticker-level H2: day premium vs own trailing 20d premium
        prem_hist: dict[str, list[float]] = defaultdict(list)
        for d in prior:
            for r in days[d]:
                prem_hist[r["ticker"]].append(r["premium"])
        tick_prem_day = {t: a["premium"] for t, a in feats.items()}
        # aggregate prior-day premiums per ticker per day (dedup already done per day file)
        prior_day_prem: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for d in prior:
            seen: dict[str, float] = defaultdict(float)
            for r in days[d]:
                seen[r["ticker"]] += r["premium"]
            for t, v in seen.items():
                prior_day_prem[t][d] = v
        for t, a in feats.items():
            hist = [prior_day_prem[t][d] for d in prior if d in prior_day_prem[t]]
            hist = hist[-20:]
            v = tick_prem_day[t]
            below = sum(1 for h in hist if h < v)
            ties = sum(1 for h in hist if h == v)
            a["prem_pctile_20d"] = (below + 0.5 * ties) / len(hist) if hist else None
            a["baseline_days"] = len(hist)
            denom = a["bid"] + a["ask"] + a["mid"]
            a["ask_share"] = a["ask"] / denom if denom else None

        # cross-sectional percentile scores
        p_prem = pct({t: a["premium"] for t, a in feats.items()})
        p_vol = pct({t: a["volume"] for t, a in feats.items()})
        p_nc = pct({t: a["n_contracts"] for t, a in feats.items()})
        p_ask = pct({t: a["ask_share"] for t, a in feats.items() if a["ask_share"] is not None})
        p_rvol = pct({t: a["rvol_cens_max"] for t, a in feats.items()})
        p_nfr = pct({t: a["n_flag_rvol"] for t, a in feats.items()})
        p_nfo = pct({t: a["n_flag_oi"] for t, a in feats.items()})
        p_ois = pct({t: a["oi_abs_sum"] for t, a in feats.items()})
        p_h2 = pct({t: a["prem_pctile_20d"] for t, a in feats.items()
                    if a["prem_pctile_20d"] is not None})

        ranked = []
        for t, a in feats.items():
            score_h1 = (0.5 * p_nfr.get(t, 0.5) + 0.5 * p_nfo.get(t, 0.5))
            score_h2 = a["prem_pctile_20d"]
            rich_vals = [p_prem.get(t), p_vol.get(t), p_nc.get(t), p_ask.get(t), p_rvol.get(t),
                         p_nfr.get(t), p_nfo.get(t), p_ois.get(t), p_h2.get(t)]
            rich_vals = [v for v in rich_vals if v is not None]
            score_v0_rich = sum(rich_vals) / len(rich_vals) if rich_vals else None
            ranked.append({
                "ticker": t,
                "premium": a["premium"],
                "volume": a["volume"],
                "n_contracts": a["n_contracts"],
                "ask_share": a["ask_share"],
                "rvol_cens_max": a["rvol_cens_max"],
                "n_flag_rvol": a["n_flag_rvol"],
                "n_flag_oi": a["n_flag_oi"],
                "oi_abs_sum": a["oi_abs_sum"],
                "prem_pctile_20d": a["prem_pctile_20d"],
                "baseline_days": a["baseline_days"],
                "score_h1": score_h1,
                "score_h2": score_h2,
                "score_v0_rich": score_v0_rich,
            })
        ranked.sort(key=lambda r: -(r["score_v0_rich"] or -1))

        out = {
            "date": D,
            "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "UW PHX top_chains (censored top-15 capture, dedup option_symbol), "
                      "contract-level H1/H2 aggregates via scripts/e08_uw_features_rich.py",
            "baseline_days": prior,
            "n_tickers": len(ranked),
            "score_v0_definition": "rich: mean of cross-sectional pct ranks over "
                                   "(premium, volume, n_contracts, ask_share, rvol_cens_max, "
                                   "n_flag_rvol, n_flag_oi, oi_abs_sum, prem_pctile_20d); "
                                   "rank variants: score_h1 (H1 union proxy), score_h2 (H2 surprise)",
            "ranked": ranked,
        }
        fn = os.path.join(E08, f"uw_features_rich_{D}.json")
        with open(fn, "w") as f:
            json.dump(out, f, indent=1)
        print(f"wrote {fn} n_tickers={len(ranked)}", file=sys.stderr)


if __name__ == "__main__":
    main()
