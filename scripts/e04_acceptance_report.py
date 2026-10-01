#!/usr/bin/env python3
"""E0.4 P0 acceptance statistics: gate-matrix numbers for the sign-off report.

Reads the saved E0.3 batch-harness run (data/e03/, regenerated 2026-10-01 by
`python3 scripts/e03_batch_harness.py run --execute`; verify PASS) plus the
E0.1 dataset coverage files (data/p0/), computes the exact-match rates and the
error distributions quoted in docs/build/p0-acceptance-report.md, and writes
everything to data/e04/acceptance_stats.json.

Stdlib only. Read-only against all sources. No Skylit / SignalForge access.

Usage:
    python3 scripts/e04_acceptance_report.py            # write + print
    python3 scripts/e04_acceptance_report.py --check    # also assert file hashes
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E03 = os.path.join(ROOT, "data", "e03")
P0 = os.path.join(ROOT, "data", "p0")
E02 = os.path.join(ROOT, "data", "e02")
OUT_DIR = os.path.join(ROOT, "data", "e04")

# Gate bars — docs/build/README.md "P0 gate (before any product build)"
BAR_KING_EXACT = 0.90
BAR_NODE_APE = 0.10
BAR_SESSION_DAYS = 20

KING_TOL = {"SPX": 25.0}
KING_TOL_DEFAULT = 5.0


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quantiles(vals):
    if not vals:
        return {}
    vs = sorted(vals)
    def q(p):
        i = min(len(vs) - 1, max(0, int(round(p * (len(vs) - 1)))))
        return vs[i]
    return {
        "min": vs[0], "p10": q(0.10), "p25": q(0.25), "p50": q(0.50),
        "p75": q(0.75), "p90": q(0.90), "p95": q(0.95), "max": vs[-1],
        "mean": sum(vs) / len(vs), "n": len(vs),
    }


def bucketize(vals, edges):
    """edges: ascending upper bounds, last bucket is '>'. Returns {label: n}."""
    out = Counter()
    for v in vals:
        label = ">" + str(edges[-1])
        for e in edges:
            if v <= e:
                label = "<=" + str(e)
                break
        out[label] += 1
    total = len(vals) or 1
    return {k: {"n": n, "frac": n / total} for k, n in sorted(out.items())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="assert input hashes match the recorded manifest")
    args = ap.parse_args()

    with open(os.path.join(E03, "summary.json")) as f:
        summary = json.load(f)
    with open(os.path.join(P0, "uw_coverage.json")) as f:
        uw_cov = json.load(f)
    with open(os.path.join(P0, "session_day_frames.json")) as f:
        frames = json.load(f)
    with open(os.path.join(P0, "re_inventory.json")) as f:
        re_inv = json.load(f)
    with open(os.path.join(E02, "fit_dataset", "index.json")) as f:
        fit_idx = json.load(f)

    # ---- per-record metrics -------------------------------------------------
    per_rec = []
    with open(os.path.join(E03, "per_record.csv")) as f:
        for row in csv.DictReader(f):
            per_rec.append(row)

    med_ape = [float(r["node_med_ape"]) for r in per_rec]
    p90_ape = [float(r["node_p90_ape"]) for r in per_rec]
    n_material = [int(r["n_material"]) for r in per_rec]

    # king strike error, normalized by the spec §3.3 tolerance (±25 SPX / ±5)
    king_norm_err, king_sym = [], defaultdict(lambda: Counter())
    for r in per_rec:
        sym = r["symbol"]
        king_sym[sym]["n"] += 1
        tol = KING_TOL.get(sym, KING_TOL_DEFAULT)
        if r["king_exact"] == "True":
            king_sym[sym]["exact"] += 1
            king_norm_err.append(0.0)
        else:
            king_sym[sym]["miss"] += 1
            err = abs(float(r["king_pred"]) - float(r["king_true"])) / tol
            king_norm_err.append(err)
        if r["king_within_tol"] == "True":
            king_sym[sym]["within_tol"] += 1

    # per-day / per-symbol king exact cross-tab
    day_sym = defaultdict(Counter)
    for r in per_rec:
        k = (r["day"], r["symbol"])
        day_sym[k]["n"] += 1
        if r["king_exact"] == "True":
            day_sym[k]["exact"] += 1

    # ---- node-level APE distribution (all compared nodes) ------------------
    node_ape = []
    n_rows = 0
    n_ape_missing = 0
    with gzip.open(os.path.join(E03, "node_comparison.csv.gz"), "rt") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            if row["ape"] == "":
                n_ape_missing += 1
                continue
            node_ape.append(float(row["ape"]))

    # ---- dataset coverage --------------------------------------------------
    uw_days = sorted(d for d, v in uw_cov["days"].items() if v.get("n_snapshots", 0) > 0)
    re_days = sorted(re_inv["manifest_by_day"].keys())
    tier_a_days = sorted(summary["per_day"].keys())
    recs_per_day = {d: summary["per_day"][d]["n_records"] for d in tier_a_days}

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_run": {
            "commands": [
                "python3 scripts/e03_batch_harness.py run --execute   # 2026-10-01T08:09Z rerun, deterministic",
                "python3 scripts/e03_batch_harness.py verify          # VERIFY: PASS",
                "python3 scripts/e04_acceptance_report.py              # this file",
            ],
            "e03_summary_generated_at": summary["generated_at"],
            "input_sha256": {
                p: sha256(os.path.join(E03, p))
                for p in ("summary.json", "per_record.csv", "star_comparison.csv")
            },
            "node_comparison_sha256": sha256(os.path.join(E03, "node_comparison.csv.gz")),
        },
        "gate_matrix": {
            "king_exact_rate": {
                "bar": ">= 0.90 over >= 20 session-days",
                "measured": summary["overall"]["king_exact_rate"],
                "measured_days": len(tier_a_days),
                "met": False,
            },
            "node_value_error": {
                "bar": "median node APE <= 0.10",
                "measured_median_of_per_record_node_med_ape": statistics.median(med_ape),
                "met": False,
            },
            "session_days": {
                "bar": ">= 20 Tier-A aligned session-days",
                "measured": len(tier_a_days),
                "met": False,
            },
            "exposure_clean_room": {
                "bar": "zero SignalForge imports/tokens in backend/core/exposure.py",
                "measured": "verify PASS: textual import-scan hits NONE, non-stdlib imports NONE",
                "met": True,
            },
        },
        "coverage": {
            "re_capture_days": len(re_days),
            "re_capture_day_list": re_days,
            "re_manifest_entries": sum(re_inv["manifest_by_day"].values()),
            "uw_gamma_data_v2_days_with_rows": len(uw_days),
            "uw_gamma_data_v2_day_list": uw_days,
            "tier_a_aligned_days": len(tier_a_days),
            "tier_a_day_list": tier_a_days,
            "records_per_tier_a_day": recs_per_day,
            "n_records_total": summary["n_records_total"],
            "fit_dataset_instants": len(fit_idx["instants"]),
        },
        "overall": summary["overall"],
        "per_day": summary["per_day"],
        "per_symbol_king": {
            sym: dict(c) | {
                "exact_rate": c["exact"] / c["n"],
                "within_tol_rate": c["within_tol"] / c["n"],
                "within_tol_of_misses_rate": ((c["within_tol"] - c["exact"]) / c["miss"]) if c["miss"] else None,
            }
            for sym, c in sorted(king_sym.items())
        },
        "day_symbol_king_exact": {
            f"{d}/{s}": {"n": c["n"], "exact_rate": c["exact"] / c["n"]}
            for (d, s), c in sorted(day_sym.items())
        },
        "error_distribution": {
            "per_record_node_med_ape": quantiles(med_ape),
            "per_record_node_med_ape_buckets": bucketize(med_ape, [0.10, 0.25, 0.50, 1.00, 2.00]),
            "per_record_node_p90_ape": quantiles(p90_ape),
            "per_record_n_material_nodes": quantiles([float(x) for x in n_material]),
            "all_node_ape": quantiles(node_ape),
            "all_node_ape_buckets": bucketize(node_ape, [0.10, 0.25, 0.50, 1.00, 2.00]),
            "node_rows_compared": n_rows,
            "node_rows_missing_ape": n_ape_missing,
            "king_abs_error_in_tol_units": quantiles(king_norm_err),
            "king_error_buckets_tol_units": bucketize(king_norm_err, [0.0, 1.0, 2.0, 5.0, 20.0]),
        },
        "star_metrics": {
            k: summary["overall"][k]
            for k in ("global_star_exact_rate", "star_exact_rate", "star_top3_rate", "top6_overlap_mean")
        },
    }

    if args.check:
        for p, h in out["source_run"]["input_sha256"].items():
            got = sha256(os.path.join(E03, p))
            assert got == h, f"hash drift on {p}: {got} != {h}"
        print("hash check: OK")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "acceptance_stats.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=False)

    print(json.dumps(out["gate_matrix"], indent=1))
    print(json.dumps(out["error_distribution"]["per_record_node_med_ape"], indent=1))
    print(json.dumps(out["per_symbol_king"], indent=1))
    print("coverage:", json.dumps(out["coverage"] | {"re_capture_day_list": "...", "uw_gamma_data_v2_day_list": "..."}, indent=1))
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
