#!/usr/bin/env python3
"""E0.3 batch harness: run backend/core/exposure.py over the P0 parity dataset.

Input = data/e02/fit_dataset/ — the Tier-A aligned (RE instant, UW batch)
records materialized from the E0.1 parity dataset (data/p0 manifest +
scripts/p0_parity_dataset.py loaders; RE Skylit node values + UW
gamma_data_v2 rows at the same instant). 1,691 records over
2026-09-28/29/30 (25/788/878), symbols SPX/SPY/QQQ/IWM.

Per record the harness:
  1. builds the UW batch (rows from rec["uw"], ts = rec["uw_ts"], prev_ts =
     the symbol's previous distinct UW batch -> spec §6.3 gap rule),
  2. runs exposure.cross_expiry_weights (EWMA state per symbol across batches),
  3. computes node values V(s), cells C(s,e), king/stars,
  4. compares per node against the Skylit targets (node_values, node_types).

Outputs (--execute):
  data/e03/node_comparison.csv.gz   per-node rows (skip V_skylit == V_ours == 0)
  data/e03/star_comparison.csv      per (record, expiry) star comparison
  data/e03/per_record.csv           per-record metrics
  data/e03/summary.json             per-day + overall aggregates, provenance

Comparison metrics are scale-honest: the model is scale-free up to one positive
scalar per batch (spec §6.8), so node APE uses the per-record least-squares
scalar c = <V_skylit, V_ours>/<V_ours, V_ours> over grid strikes; king/top6/
star placement are scale-invariant and compared directly. Domain = the Skylit
grid strikes (same domain as the E0.2 residual report); the production-domain
king (all UW strikes) is recorded alongside.

Scoring excludes stale RE records (per-record |asOf - window_start| > 2 s) per
spec §5.2.

Usage:
  python3 scripts/e03_batch_harness.py run              # dry-run (default)
  python3 scripts/e03_batch_harness.py run --execute    # write data/e03/
  python3 scripts/e03_batch_harness.py verify           # clean-room + outputs
"""
from __future__ import annotations

import argparse
import ast
import csv
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from backend.core import exposure as exp  # noqa: E402

FITSET_DIR = os.path.join(REPO, "data", "e02", "fit_dataset")
DEFAULT_OUT = os.path.join(REPO, "data", "e03")

# Stored per (strike, expiry) in fit records (E0.2 prepare, scripts/
# e02_cross_expiry_fit.py FEAT_KEYS). feats[0] is net_gex; the harness feeds
# exposure.py the named UW columns and lets it re-derive g = call - put.
FEAT_KEYS = ("net_gex", "call_gex", "put_gex", "call_oi", "put_oi",
             "call_volume", "put_volume", "call_ask_vol", "call_bid_vol",
             "put_ask_vol", "put_bid_vol", "call_prev_oi", "put_prev_oi", "iv")
_ROW_KEYS = FEAT_KEYS[1:-1]  # call_gex .. put_prev_oi (iv unused by the layer)

KING_TOL = {"SPX": 25.0}  # ±tol: 25 SPX points / 5 points SPY/QQQ/IWM (spec §3.3)
KING_TOL_DEFAULT = 5.0
MATERIAL_FRAC = 0.05  # |V| >= 5% of max|V| = material nodes (E0.2 APE def)


def _jgzload(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def _ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def is_stale_record(rec) -> bool:
    """RE-side staliness (spec §5.2): per-record |asOf - window_start| <= 2 s.

    The normative rule is per record (the record IS one capture's symbol-record
    and carries its own asOf). The E0.1 per-(symbol,day) map
    (data/p0/re_inventory.json:asof_stale_by_symbol_day) is advisory — it flags
    whole (symbol, day) pairs that contain ANY stale record; excluding those
    wholesale would drop ~80% of records, and the E0.2 fits/residuals score
    with the per-record rule, so the harness does too. rec["stale_symbol"] is
    used only as a fallback when the record cannot be parsed."""
    try:
        win_start = datetime.fromisoformat(
            f"{rec['day']}T{rec['window'][:2]}:{rec['window'][2:4]}:{rec['window'][4:6]}+00:00")
        asof = _ts(rec["asOf"])
        return abs((asof - win_start).total_seconds()) > 2
    except Exception:
        return bool(rec.get("stale_symbol"))


def rec_to_rows(rec) -> list:
    """fit record uw dict -> UW gamma_data_v2-shaped rows for exposure.py."""
    rows = []
    for strike_s, emap in rec["uw"].items():
        for expiry, feats in emap.items():
            if len(feats) < len(FEAT_KEYS):
                continue
            row = {"strike": float(strike_s), "expiry_date": expiry}
            for i, key in enumerate(_ROW_KEYS, start=1):
                row[key] = float(feats[i]) if feats[i] is not None else 0.0
            rows.append(row)
    return rows


def day_of(ts_iso: str) -> str:
    return ts_iso[:10]


# ---------------------------------------------------------------- scoring

def score_record(rec, weights, state=None) -> dict:
    """Compare exposure.py output against the Skylit targets of one record.

    `state` = the symbol's §10 cell-state store (post-update for this batch);
    when given, the model is the state-augmented one (spec §10.3).
    """
    strikes = [float(s) for s in rec["strikes"]]
    v_sk = [float(v) for v in rec["node_values"]]
    ntypes = rec.get("node_types") or [None] * len(strikes)

    batch_rows = rec_to_rows(rec)
    batch = exp.normalize_batch(batch_rows, ts=rec["uw_ts"], spot=rec.get("spot"))
    if state is None:
        v_ours_full = exp.node_values(batch, weights)
        cells_ours = exp.cell_values(batch, weights)
    else:
        v_ours_full = exp.stateful_node_values(batch, weights, state)
        cells_ours = exp.stateful_cell_values(batch, weights, state)

    # comparison domain = Skylit grid strikes (production domain kept apart)
    v_ours = [v_ours_full.get(s, 0.0) for s in strikes]

    # per-record LS scale scalar (spec §6.8: V is scale-free up to one scalar)
    den = sum(x * x for x in v_ours)
    c_scale = (sum(a * b for a, b in zip(v_sk, v_ours)) / den) if den > 0 else 0.0
    v_hat = [c_scale * x for x in v_ours]

    vmax = max((abs(v) for v in v_sk), default=0.0)
    if vmax == 0:
        return {"scored": False, "reason": "all-zero skylit nodes"}
    material = [i for i, v in enumerate(v_sk) if abs(v) >= MATERIAL_FRAC * vmax]
    apes = [abs(v_hat[i] - v_sk[i]) / max(abs(v_sk[i]), 1e-12) for i in material]
    apes_sorted = sorted(apes)
    med = apes_sorted[len(apes_sorted) // 2] if apes_sorted else None
    p90 = apes_sorted[min(int(0.9 * len(apes_sorted)), len(apes_sorted) - 1)] if apes_sorted else None

    king_true_i = next((i for i, n in enumerate(ntypes) if n == "king"), None)
    if king_true_i is None:
        king_true_i = max(range(len(strikes)), key=lambda i: (abs(v_sk[i]), -strikes[i]))
    king_pred_i = max(range(len(strikes)), key=lambda i: (abs(v_ours[i]), -strikes[i]))
    king_true, king_pred = strikes[king_true_i], strikes[king_pred_i]
    king_full = max(v_ours_full.items(), key=lambda kv: (abs(kv[1]), -kv[0]))[0] if v_ours_full else None
    tol = KING_TOL.get(rec["symbol"], KING_TOL_DEFAULT)

    top_pred = sorted(range(len(strikes)), key=lambda i: (-abs(v_ours[i]), strikes[i]))[:6]
    top_true = sorted(range(len(strikes)), key=lambda i: (-abs(v_sk[i]), strikes[i]))[:6]
    top6_overlap = len({strikes[i] for i in top_pred} & {strikes[i] for i in top_true})

    # star comparison (star = argmax |C| cell; per-expiry star = column max)
    exps = rec["expiries"]
    cells_sk = rec["cells"]
    star_rows = []
    for j, e in enumerate(exps):
        best_i, best_v = None, 0.0
        for i, s in enumerate(strikes):
            v = abs(float(cells_sk[i][j]))
            if v > best_v:
                best_i, best_v = i, v
        if best_i is None:
            continue  # all-zero skylit column: no star
        ours_best, ours_v = None, 0.0
        ours_ranked = sorted(
            ((s, abs(cv)) for (s, ee), cv in cells_ours.items() if ee == e),
            key=lambda kv: (-kv[1], kv[0]))
        if ours_ranked:
            ours_best, ours_v = ours_ranked[0]
        if ours_best is None:
            continue
        ours_top3 = {s for s, _v in ours_ranked[:3]}
        star_rows.append({
            "expiry": e,
            "skylit_star_strike": strikes[best_i],
            "skylit_star_abs": best_v,
            "ours_star_strike": ours_best,
            "ours_star_abs": ours_v,
            "star_exact": ours_best == strikes[best_i],
            "skylit_star_in_ours_top3": strikes[best_i] in ours_top3,
            "ours_star_on_grid": ours_best in set(strikes),
        })
    g_best_i = g_best_j = None
    g_best_v = 0.0
    for i in range(len(strikes)):
        for j in range(len(exps)):
            v = abs(float(cells_sk[i][j]))
            if v > g_best_v:
                g_best_i, g_best_j, g_best_v = i, j, v
    ours_g = max(cells_ours.items(), key=lambda kv: (abs(kv[1]), -kv[0][0])) if cells_ours else None
    g_exact = (g_best_i is not None and ours_g is not None
               and ours_g[0][0] == strikes[g_best_i] and ours_g[0][1] == exps[g_best_j])

    return {
        "scored": True,
        "c_scale": c_scale,
        "node_med_ape": med,
        "node_p90_ape": p90,
        "n_material": len(material),
        "king_true": king_true,
        "king_pred": king_pred,
        "king_pred_full": king_full,
        "king_exact": king_pred == king_true,
        "king_within_tol": abs(king_pred - king_true) <= tol,
        "top6_overlap": top6_overlap,
        "star_rows": star_rows,
        "star_exact_n": sum(1 for r in star_rows if r["star_exact"]),
        "star_top3_n": sum(1 for r in star_rows if r["skylit_star_in_ours_top3"]),
        "star_total_n": len(star_rows),
        "global_star_exact": g_exact,
        "skylit_global_star": (strikes[g_best_i], exps[g_best_j]) if g_best_i is not None else None,
        "ours_global_star": ours_g[0] if ours_g else None,
        "v_ours": v_ours,
        "v_hat": v_hat,
        "v_sk": v_sk,
        "ntypes": ntypes,
        "strikes": strikes,
        "king_pred_i": king_pred_i,
        "top_pred_set": {strikes[i] for i in top_pred},
        "top_true_set": {strikes[i] for i in top_true},
        "n_rows": batch["n_rows"],
        "dropped_stale_rows": batch["dropped_stale_rows"],
    }


# ---------------------------------------------------------------- run

def load_index():
    with open(os.path.join(FITSET_DIR, "index.json")) as f:
        return json.load(f)


def run(out_dir: str, execute: bool, limit: int = 0, state_layer: bool = False,
        gamma: float = exp.MAG_GAMMA) -> int:
    index = load_index()
    instants = sorted(index["instants"],
                      key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))
    if limit:
        instants = instants[:limit]

    per_record_rows = []
    node_rows = []
    star_rows_all = []
    state = defaultdict(dict)          # symbol -> {expiry: a_e}
    cell_state = defaultdict(exp.new_cell_state)  # symbol -> §10 state store
    weights_cache = {}                 # (symbol, uw_ts) -> weights
    prev_batch_ts = {}                 # symbol -> last distinct uw_ts
    exp_dots = []
    n_stale_skipped = 0
    n_scored = 0

    for n, e in enumerate(instants, 1):
        path = os.path.join(FITSET_DIR, e["key"].replace("/", "_") + ".json.gz")
        rec = _jgzload(path)
        if is_stale_record(rec):
            n_stale_skipped += 1
            continue
        sym = rec["symbol"]
        ts = rec["uw_ts"]
        cache_key = (sym, ts)
        if cache_key not in weights_cache:
            prev = prev_batch_ts.get(sym)
            batch = exp.normalize_batch(rec_to_rows(rec), ts=ts, prev_ts=prev,
                                        spot=rec.get("spot"))
            w = exp.cross_expiry_weights(batch, state[sym], gamma=gamma)
            state[sym] = dict(w)
            if state_layer:
                cell_state[sym] = exp.update_cell_state(batch, cell_state[sym])
            weights_cache[cache_key] = w
            prev_batch_ts[sym] = ts
            for expiry in w:
                col_x = exp.expiry_features(batch, expiry)
                exp_dots.append(exp.THETA[0] + sum(t * x for t, x in zip(exp.THETA[1:], col_x)))
        w = weights_cache[cache_key]

        out = score_record(rec, w, state=cell_state[sym] if state_layer else None)
        if not out["scored"]:
            continue
        n_scored += 1
        per_record_rows.append({
            "key": e["key"], "symbol": sym, "day": rec["day"], "uw_ts": ts,
            "dt_s": e.get("dt_s"), "asOf": rec["asOf"],
            "n_rows": out["n_rows"], "dropped_stale_rows": out["dropped_stale_rows"],
            "c_scale": out["c_scale"],
            "node_med_ape": out["node_med_ape"], "node_p90_ape": out["node_p90_ape"],
            "n_material": out["n_material"],
            "king_true": out["king_true"], "king_pred": out["king_pred"],
            "king_pred_full": out["king_pred_full"],
            "king_exact": out["king_exact"], "king_within_tol": out["king_within_tol"],
            "top6_overlap": out["top6_overlap"],
            "skylit_global_star_strike": out["skylit_global_star"][0] if out["skylit_global_star"] else "",
            "skylit_global_star_expiry": out["skylit_global_star"][1] if out["skylit_global_star"] else "",
            "ours_global_star_strike": out["ours_global_star"][0] if out["ours_global_star"] else "",
            "ours_global_star_expiry": out["ours_global_star"][1] if out["ours_global_star"] else "",
            "global_star_exact": out["global_star_exact"],
            "star_exact_n": out["star_exact_n"], "star_top3_n": out["star_top3_n"],
            "star_total_n": out["star_total_n"],
        })
        for r in out["star_rows"]:
            star_rows_all.append({"key": e["key"], "symbol": sym, "day": rec["day"], **r})
        # per-node rows: skip nodes where both sides are zero
        for i, s in enumerate(out["strikes"]):
            vs, vo, vh = out["v_sk"][i], out["v_ours"][i], out["v_hat"][i]
            if vs == 0.0 and vo == 0.0:
                continue
            ape = abs(vh - vs) / max(abs(vs), 1e-12) if vs != 0.0 else ""
            node_rows.append({
                "key": e["key"], "symbol": sym, "day": rec["day"], "uw_ts": ts,
                "strike": s, "v_skylit": vs, "v_ours": vo, "scale_c": out["c_scale"],
                "v_ours_scaled": vh, "ape": ape,
                "node_type": out["ntypes"][i], "skylit_king": out["king_true"] == s,
                "ours_king": out["king_pred"] == s,
                "in_skylit_top6": s in out["top_true_set"],
                "in_ours_top6": s in out["top_pred_set"],
            })
        if n % 200 == 0:
            print(f"  ... {n}/{len(instants)} records, {n_scored} scored, "
                  f"{len(node_rows)} node rows", flush=True)

    summary = summarize(per_record_rows, star_rows_all, n_scored, n_stale_skipped,
                        exp_dots, len(instants))
    summary["psi_magnitude_gamma"] = gamma
    if gamma != exp.MAG_GAMMA:
        summary["model"] = (f"backend/core/exposure.py (clean-room, E0.3) with "
                            f"psi gamma={gamma} (pre-E0.5b at gamma=1.0)")
    if state_layer:
        summary["model"] = ("backend/core/exposure.py §10 state-augmented model "
                            f"(LAMBDA_CELL={exp.LAMBDA_CELL}, STATE_BETA={exp.STATE_BETA})")
        summary["state_layer"] = {"lambda_cell": exp.LAMBDA_CELL,
                                  "state_beta": list(exp.STATE_BETA),
                                  "spec": "cross-expiry-layer-spec.md §10"}
    print_summary(summary)

    if not execute:
        print(f"\nDRY-RUN: would write node_comparison.csv.gz ({len(node_rows)} rows), "
              f"star_comparison.csv ({len(star_rows_all)} rows), "
              f"per_record.csv ({len(per_record_rows)} rows), summary.json -> {out_dir}")
        print("re-run with --execute to write")
        return 0

    os.makedirs(out_dir, exist_ok=True)
    with gzip.open(os.path.join(out_dir, "node_comparison.csv.gz"), "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(node_rows[0].keys()))
        w.writeheader()
        w.writerows(node_rows)
    for name, rows in (("star_comparison.csv", star_rows_all),
                       ("per_record.csv", per_record_rows)):
        with open(os.path.join(out_dir, name), "w", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    print(f"\nwrote {out_dir}/node_comparison.csv.gz ({len(node_rows)} rows), "
          f"star_comparison.csv ({len(star_rows_all)}), per_record.csv "
          f"({len(per_record_rows)}), summary.json")
    return 0


def summarize(per_record_rows, star_rows_all, n_scored, n_stale_skipped,
              exp_dots, n_total) -> dict:
    def agg(rows):
        if not rows:
            return {}
        meds = sorted(r["node_med_ape"] for r in rows if r["node_med_ape"] is not None)
        return {
            "n_records": len(rows),
            "king_exact_rate": round(sum(r["king_exact"] for r in rows) / len(rows), 4),
            "king_within_tol_rate": round(sum(r["king_within_tol"] for r in rows) / len(rows), 4),
            "top6_overlap_mean": round(sum(r["top6_overlap"] for r in rows) / len(rows), 4),
            "node_med_ape_median": round(meds[len(meds) // 2], 4) if meds else None,
            "global_star_exact_rate": round(sum(bool(r["global_star_exact"]) for r in rows) / len(rows), 4),
            "star_exact_rate": (round(sum(r["star_exact_n"] for r in rows) /
                                      max(sum(r["star_total_n"] for r in rows), 1), 4)),
            "star_top3_rate": (round(sum(r["star_top3_n"] for r in rows) /
                                     max(sum(r["star_total_n"] for r in rows), 1), 4)),
        }

    by_day = {}
    for day in sorted({r["day"] for r in per_record_rows}):
        by_day[day] = agg([r for r in per_record_rows if r["day"] == day])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "harness": "scripts/e03_batch_harness.py",
        "model": "backend/core/exposure.py (clean-room, E0.3)",
        "input": "data/e02/fit_dataset (E0.1 parity dataset Tier-A aligned records)",
        "n_records_total": n_total,
        "n_scored": n_scored,
        "n_skipped_stale": n_stale_skipped,
        "theta_dot_range": [min(exp_dots), max(exp_dots)] if exp_dots else None,
        "overall": agg(per_record_rows),
        "per_day": by_day,
        "notes": [
            "node APE after per-record LS scale scalar (scale-free model, spec 6.8); "
            "material nodes |V| >= 5% max|V|",
            "king/top6/star compared on the Skylit grid strikes; king_pred_full "
            "(all UW strikes) in per_record.csv",
            "stale RE records excluded per spec 5.2 per-record rule "
            "(|asOf - window_start| > 2s)",
        ],
    }


def print_summary(s):
    print(f"\nscored {s['n_scored']}/{s['n_records_total']} records "
          f"({s['n_skipped_stale']} stale skipped)")
    print("overall:", json.dumps(s["overall"], indent=1))
    for day, agg in s["per_day"].items():
        print(day, json.dumps(agg))


# ---------------------------------------------------------------- verify

def import_graph() -> dict:
    """AST import graph of backend/**.py — clean-room evidence."""
    graph = {}
    for root, _dirs, files in os.walk(os.path.join(REPO, "backend")):
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, REPO)
            with open(path) as f:
                tree = ast.parse(f.read(), filename=rel)
            mods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    mods.add(("*" * node.level + (node.module or "")))
            graph[rel] = sorted(mods)
    return graph


def verify(out_dir: str) -> int:
    ok = True
    graph = import_graph()
    print("backend import graph:")
    for rel, mods in sorted(graph.items()):
        print(f"  {rel}: {', '.join(mods) if mods else '(none)'}")
    banned = re.compile(r"signalforge", re.I)
    offenders = {rel: [m for m in mods if banned.search(m)] for rel, mods in graph.items()}
    offenders = {rel: m for rel, m in offenders.items() if m}
    print("imports referencing any external trading system:", offenders or "NONE")
    ok &= not offenders

    # textual scan: no import/from statement anywhere in backend/ names it
    pat = re.compile(r"^\s*(?:from|import)\s+\S*signalforge", re.I | re.M)
    hits = []
    for root, _dirs, files in os.walk(os.path.join(REPO, "backend")):
        for name in files:
            if name.endswith(".py"):
                p = os.path.join(root, name)
                with open(p) as f:
                    if pat.search(f.read()):
                        hits.append(p)
    print("textual import-scan hits:", hits or "NONE")
    ok &= not hits

    # stdlib-only import check for the core module itself
    stdlib = {"__future__", "math", "datetime", "typing", "collections", "json",
              "os", "sys", "re", "gzip", "csv", "argparse", "ast", "statistics", "time"}
    core_mods = set(graph.get("backend/core/exposure.py", []))
    non_stdlib = {m for m in core_mods if m.split(".")[0] not in stdlib}
    print("backend/core/exposure.py non-stdlib imports:", non_stdlib or "NONE")
    ok &= not non_stdlib

    # outputs present + counts consistent
    summary_p = os.path.join(out_dir, "summary.json")
    node_p = os.path.join(out_dir, "node_comparison.csv.gz")
    rec_p = os.path.join(out_dir, "per_record.csv")
    star_p = os.path.join(out_dir, "star_comparison.csv")
    for p in (summary_p, node_p, rec_p, star_p):
        exists = os.path.exists(p)
        print(f"output {os.path.relpath(p, REPO)}: {'OK' if exists else 'MISSING'}")
        ok &= exists
    if ok:
        summary = json.load(open(summary_p))
        with open(rec_p) as f:
            n_rec_rows = sum(1 for _ in f) - 1
        with gzip.open(node_p, "rt") as f:
            n_node_rows = sum(1 for _ in f) - 1
        print(f"per_record rows: {n_rec_rows} (summary n_scored={summary['n_scored']}), "
              f"node rows: {n_node_rows}")
        ok &= n_rec_rows == summary["n_scored"] and n_node_rows > 0
    print("VERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--execute", action="store_true",
                       help="write outputs (default: dry-run)")
    p_run.add_argument("--limit", type=int, default=0, help="cap records (smoke runs)")
    p_run.add_argument("--out-dir", default=DEFAULT_OUT)
    p_run.add_argument("--state-layer", action="store_true",
                       help="score with the §10 state-augmented model (E0.5a)")
    p_run.add_argument("--gamma", type=float, default=exp.MAG_GAMMA,
                       help="psi magnitude temper (E0.5b); 1.0 = pre-E0.5b model")
    p_v = sub.add_parser("verify")
    p_v.add_argument("--out-dir", default=DEFAULT_OUT)
    args = ap.parse_args()
    if args.cmd == "run":
        return run(args.out_dir, args.execute, args.limit, args.state_layer, args.gamma)
    return verify(args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
