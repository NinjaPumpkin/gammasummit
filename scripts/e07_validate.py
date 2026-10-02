#!/usr/bin/env python3
"""E0.7 validation — UW-only ticker score vs Skylit observed picks (replay).

Compares data/e07/uw_features_<date>.json (UW PHX only) against the observed
Skylit surfaces saved in data/e07/skylit_api/ for the same historical dates:

  ground truth A  top_tickers_premium   Skylit's own premium-ranked ticker list
  ground truth B  unusual_volume + unusual_oi tickers (contract lists aggregated)
  ground truth C  attention set = top-25(A) ∪ B

Metrics per date (sample sizes always reported):
  V1 Spearman rho(UW premium rank, Skylit premium rank) over common tickers
  V2 P@K / R@K of UW score_v0 top-K vs A_K (K = 25/50/100)
     + sanity ceiling: UW premium-only rank vs A (should be high; proxy check)
  V3 P@K / R@K of UW score_v0 top-K vs B (K = 50/100)
  V4 P@K / R@K of UW score_v0 top-K vs C (K = 50/100)

Output: data/e07/validation_report.json + validation_report.md
Usage: python3 scripts/e07_validate.py --dates 2026-09-29 2026-09-30 2026-10-01
"""
from __future__ import annotations

import argparse
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E07 = os.path.join(ROOT, "data", "e07")
SK = os.path.join(E07, "skylit_api")


def load(fn: str):
    with open(fn) as f:
        return json.load(f)


def spearman(a: dict[str, float], b: dict[str, float]) -> tuple[float, int]:
    keys = sorted(set(a) & set(b))
    n = len(keys)
    if n < 3:
        return float("nan"), n

    def ranks(d):
        order = sorted(keys, key=lambda k: d[k])
        r = {k: 0.0 for k in keys}
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and d[order[j + 1]] == d[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in order[i:j + 1]:
                r[k] = avg
            i = j + 1
        return r

    ra, rb = ranks(a), ranks(b)
    ma = sum(ra[k] for k in keys) / n
    mb = sum(rb[k] for k in keys) / n
    cov = sum((ra[k] - ma) * (rb[k] - mb) for k in keys)
    va = sum((ra[k] - ma) ** 2 for k in keys) ** 0.5
    vb = sum((rb[k] - mb) ** 2 for k in keys) ** 0.5
    return (cov / (va * vb)) if va and vb else float("nan"), n


def pr_at_k(pred: list[str], truth: set[str], k: int) -> dict:
    top = pred[:k]
    hits = [t for t in top if t in truth]
    return {
        "k": k,
        "n_pred": len(top),
        "n_truth": len(truth),
        "hits": len(hits),
        "precision": len(hits) / len(top) if top else None,
        "recall": len(hits) / len(truth) if truth else None,
        "hit_tickers": hits,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="+", required=True)
    args = ap.parse_args()

    report = {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "uw_source": "data/e07/uw_features_<date>.json (UW PHX only; score_v0 = unfitted "
                     "equal-weight percentile mean, top_chains-truncated premium proxy)",
        "skylit_source": "data/e07/skylit_api/<date>_*.json (Flowseeker API daily rollups, "
                         "captured 2026-10-02)",
        "dates": {},
    }

    for D in args.dates:
        uf = load(os.path.join(E07, f"uw_features_{D}.json"))
        sk_prem = load(os.path.join(SK, f"{D}_top_tickers_premium.json"))["data"]
        uv = load(os.path.join(SK, f"{D}_unusual_volume.json"))["data"]
        uo = load(os.path.join(SK, f"{D}_unusual_oi.json"))["data"]

        uw_rank = [r["ticker"] for r in uf["ranked"] if r.get("score_v0") is not None]
        uw_score = {r["ticker"]: r["score_v0"] for r in uf["ranked"] if r.get("score_v0") is not None}
        uw_prem = {r["ticker"]: r["premium"] for r in uf["ranked"]}

        sk_rank = [r["ticker"] for r in sk_prem]
        sk_prem_val = {r["ticker"]: r["totalPremium"] for r in sk_prem}

        truth_prem = set(sk_rank)
        truth_unusual = {r["ticker"] for r in uv} | {r["ticker"] for r in uo}
        truth_attention = set(sk_rank[:25]) | truth_unusual

        v1_rho, v1_n = spearman(uw_prem, sk_prem_val)
        v1b_rho, v1b_n = spearman(uw_score, sk_prem_val)

        day = {
            "universe": {"uw_n": len(uf["ranked"]), "skylit_n": len(sk_prem)},
            "V1_spearman_uw_prem_vs_skylit_prem": {"rho": v1_rho, "n_common": v1_n},
            "V1b_spearman_uw_score_vs_skylit_prem": {"rho": v1b_rho, "n_common": v1b_n},
            "V2_score_vs_top_premium": [pr_at_k(uw_rank, truth_prem, k) for k in (25, 50, 100)],
            "V2_ceiling_uw_prem_only_vs_top_premium": [
                pr_at_k(sorted(uw_prem, key=lambda t: -uw_prem[t]), truth_prem, k) for k in (25, 50, 100)],
            "V3_score_vs_unusual": {
                "truth_n": len(truth_unusual),
                "truth_tickers": sorted(truth_unusual),
                "rows": [pr_at_k(uw_rank, truth_unusual, k) for k in (50, 100, 150)],
            },
            "V4_score_vs_attention": {
                "truth_n": len(truth_attention),
                "rows": [pr_at_k(uw_rank, truth_attention, k) for k in (50, 100, 150)],
            },
        }
        report["dates"][D] = day

    fn = os.path.join(E07, "validation_report.json")
    with open(fn, "w") as f:
        json.dump(report, f, indent=1)

    # markdown render
    md = ["# E0.7 validation report — UW score vs Skylit observed picks", "",
          f"Generated: {report['generated_utc']}",
          f"UW source: {report['uw_source']}",
          f"Skylit source: {report['skylit_source']}", ""]
    for D, day in report["dates"].items():
        md.append(f"## {D}")
        md.append(f"- universes: UW n={day['universe']['uw_n']} · Skylit n={day['universe']['skylit_n']}")
        v1 = day["V1_spearman_uw_prem_vs_skylit_prem"]
        v1b = day["V1b_spearman_uw_score_vs_skylit_prem"]
        md.append(f"- V1 Spearman(UW premium proxy, Skylit total premium): rho={v1['rho']:.3f} (n={v1['n_common']})")
        md.append(f"- V1b Spearman(UW score_v0, Skylit total premium): rho={v1b['rho']:.3f} (n={v1b['n_common']})")
        md.append("- V2 score_v0 vs Skylit top-premium tickers (precision / recall / hits@n_truth):")
        for r in day["V2_score_vs_top_premium"]:
            md.append(f"    - K={r['k']}: P={r['precision']:.2f} R={r['recall']:.2f} hits={r['hits']}/{r['n_truth']}")
        md.append("- V2 ceiling (UW premium-only rank vs same truth):")
        for r in day["V2_ceiling_uw_prem_only_vs_top_premium"]:
            md.append(f"    - K={r['k']}: P={r['precision']:.2f} R={r['recall']:.2f} hits={r['hits']}/{r['n_truth']}")
        md.append(f"- V3 score_v0 vs unusual sets (truth n={day['V3_score_vs_unusual']['truth_n']}):")
        for r in day["V3_score_vs_unusual"]["rows"]:
            md.append(f"    - K={r['k']}: P={r['precision']:.2f} R={r['recall']:.2f} hits={r['hits']}/{r['n_truth']}")
        md.append(f"- V4 score_v0 vs attention set (truth n={day['V4_score_vs_attention']['truth_n']}):")
        for r in day["V4_score_vs_attention"]["rows"]:
            md.append(f"    - K={r['k']}: P={r['precision']:.2f} R={r['recall']:.2f} hits={r['hits']}/{r['n_truth']}")
        md.append("")
    fn_md = os.path.join(E07, "validation_report.md")
    with open(fn_md, "w") as f:
        f.write("\n".join(md))
    print("\n".join(md))
    print(f"\nwrote {fn} + {fn_md}")


if __name__ == "__main__":
    main()
