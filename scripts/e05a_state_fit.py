#!/usr/bin/env python3
"""E0.5a fit: cell-level dynamic state layer (spec §10) — profiled-LS fit.

Walks the growing Tier-A set (data/e02/fit_dataset) exactly like the E0.3
batch harness (same record order, same stale rule, same EWMA gap rule), keeps
the §10 state per symbol via backend/core/exposure.py (fit == production
semantics by construction), and fits:

  LAMBDA_CELL  -- cell-state decay, grid search (spec §10.5.2)
  STATE_BETA   -- 8 state-augmented value coefficients, linear in beta

Objective (profiled per-record LS scale, same scoring as the harness):
  J(beta) = sum_r cos^2(v_r, Phi_r beta)
solved by power iteration on the reweighted quadratic surrogate
A = sum_r (u_r u_r^T)/(beta^T G_r beta) with u_r = Phi_r^T v_r,
G_r = Phi_r^T Phi_r (both beta-independent -> computed once per record).

Also reports: baseline J (beta = e1 = the E0.3 model shape), per-record node
APE after LS scale for baseline vs fitted, and leave-one-day-out stability.

Subcommands:
  fit [--apply]            fit + write data/e05a/state_fit.json
                           (--apply also patches LAMBDA_CELL/STATE_BETA into
                           backend/core/exposure.py, backing it up first)
  report                   before/after node-error report from data/e05a/
                           {before,after} harness runs -> before_after_report.{json,md}

Daily refit cadence: run `fit --apply` as part of cron gammasummit-e02-daily-refit
(one new Tier-A day accrues per RTH session; spec §10.4.4). PILOT-GRADE on
< 20 aligned days — the <=10% gate bar is measured by gate card t_b157a485.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
from backend.core import exposure as exp  # noqa: E402
from e03_batch_harness import (FITSET_DIR, _jgzload, is_stale_record,  # noqa: E402
                               load_index, rec_to_rows)

OUT_DIR = os.path.join(REPO, "data", "e05a")
EXPOSURE_PY = os.path.join(REPO, "backend", "core", "exposure.py")
LAM_GRID = (0.5, 0.7, 0.79, 0.9, 0.95, 0.98, 0.99)
P = 8
BETA0 = (1.0,) + (0.0,) * (P - 1)
MATERIAL_FRAC = 0.05
COMMANDS = [
    "python3 scripts/e05a_state_fit.py fit --apply",
    "python3 scripts/e03_batch_harness.py run --execute --out-dir data/e05a/before",
    "python3 scripts/e03_batch_harness.py run --execute --state-layer --out-dir data/e05a/after",
    "python3 scripts/e05a_state_fit.py report",
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- walk

def walk(lams, cache_dir=None):
    """One harness-order walk. Returns (records_meta, per-lam (u, G, nv2) lists).

    records_meta: [key, day] per scored record. For each lam: list of
    (u: 8-vec, G: 8x8, nv2: float) aligned with records_meta.
    When cache_dir is given, entries are persisted per lam so later refits
    skip the walk (validated against the fit index sha256).
    """
    index = load_index()
    instants = sorted(index["instants"],
                      key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))
    w_state = defaultdict(dict)
    st = {lam: defaultdict(exp.new_cell_state) for lam in lams}
    weights_cache = {}
    prev_batch_ts = {}
    meta = []
    acc = {lam: [] for lam in lams}
    for n, e in enumerate(instants, 1):
        rec = _jgzload(os.path.join(FITSET_DIR, e["key"].replace("/", "_") + ".json.gz"))
        if is_stale_record(rec):
            continue
        v = [float(x) for x in rec["node_values"]]
        if max((abs(x) for x in v), default=0.0) == 0:
            continue
        sym, ts = rec["symbol"], rec["uw_ts"]
        cache_key = (sym, ts)
        if cache_key not in weights_cache:
            prev = prev_batch_ts.get(sym)
            batch = exp.normalize_batch(rec_to_rows(rec), ts=ts, prev_ts=prev,
                                        spot=rec.get("spot"))
            w = exp.cross_expiry_weights(batch, w_state[sym])
            w_state[sym] = dict(w)
            weights_cache[cache_key] = (w, batch)
            prev_batch_ts[sym] = ts
        w, batch = weights_cache[cache_key]
        strikes = [float(s) for s in rec["strikes"]]
        meta.append((e["key"], rec["day"]))
        for lam in lams:
            st[lam][sym] = exp.update_cell_state(batch, st[lam][sym], lam=lam)
            design = exp.state_node_design(batch, w, st[lam][sym])
            u = [0.0] * P
            g = [[0.0] * P for _ in range(P)]
            nv2 = 0.0
            for s, vj in zip(strikes, v):
                row = design.get(s, ZERO_ROW)
                nv2 += vj * vj
                for a in range(P):
                    u[a] += row[a] * vj
                    for b in range(a, P):
                        g[a][b] += row[a] * row[b]
            for a in range(P):
                for b in range(a):
                    g[a][b] = g[b][a]
            acc[lam].append((u, g, nv2))
        if n % 400 == 0:
            print(f"  ... {n}/{len(instants)} instants, {len(meta)} scored", flush=True)
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        index_sha = sha256(os.path.join(FITSET_DIR, "index.json"))
        with open(os.path.join(cache_dir, "meta.json"), "w") as f:
            json.dump({"index_sha256": index_sha, "days": sorted({d for _k, d in meta}),
                       "n_records": len(meta), "records": [list(m) for m in meta],
                       "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                      f, indent=1)
        for lam in lams:
            with gzip.open(os.path.join(cache_dir, f"lam_{lam}.json.gz"), "wt") as f:
                json.dump([{"u": u, "g": g, "nv2": nv2} for u, g, nv2 in acc[lam]], f)
        print(f"fit cache written under {cache_dir}")
    return meta, acc


def load_cache(cache_dir, lams):
    """Load walk entries from cache; returns (meta, acc) or None on mismatch."""
    try:
        with open(os.path.join(cache_dir, "meta.json")) as f:
            meta_raw = json.load(f)
        if meta_raw["index_sha256"] != sha256(os.path.join(FITSET_DIR, "index.json")):
            return None
        meta = [(k, d) for k, d in meta_raw["records"]]
        acc = {}
        for lam in lams:
            with gzip.open(os.path.join(cache_dir, f"lam_{lam}.json.gz"), "rt") as f:
                raw = json.load(f)
            acc[lam] = [(r["u"], r["g"], r["nv2"]) for r in raw]
        if any(len(v) != len(meta) for v in acc.values()):
            return None
        return meta, acc
    except (OSError, KeyError, ValueError, TypeError):
        return None


ZERO_ROW = (0.0,) * P


# ---------------------------------------------------------------- fit math

def quad(beta, g):
    return sum(beta[a] * g[a][b] * beta[b] for a in range(P) for b in range(P))


def fit_beta(entries, iters=20):
    """Power iteration on the reweighted surrogate (spec §10.5.2).

    Multi-start (e1, uniform, gex/flow split) — the surrogate majorizes J at
    the current beta but J is not concave, so a single start can stall at
    beta = e1 (observed on the Tier-A set: several lambda candidates leave the
    baseline direction unchanged). Best J over starts wins.
    """
    starts = [list(BETA0),
              [1.0 / math.sqrt(P)] * P,
              [0.5, 0.5, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0]]
    best_beta, best_j = list(BETA0), eval_j(BETA0, entries)
    for start in starts:
        beta = list(start)
        j = eval_j(beta, entries)
        for _ in range(iters):
            a_mat = [[0.0] * P for _ in range(P)]
            for u, g, nv2 in entries:
                den = quad(beta, g)
                if den <= 0:
                    continue
                wgt = 1.0 / den
                for a in range(P):
                    for b in range(P):
                        a_mat[a][b] += wgt * u[a] * u[b]
            v = list(beta)
            for _ in range(200):
                nv = [sum(a_mat[a][b] * v[b] for b in range(P)) for a in range(P)]
                nrm = math.sqrt(sum(x * x for x in nv))
                if nrm == 0:
                    break
                v = [x / nrm for x in nv]
            new_j = eval_j(v, entries)
            if new_j <= j:
                break
            beta, j = v, new_j
        if j > best_j:
            best_beta, best_j = beta, j
    return refine_beta(best_beta, best_j, entries)


def _normalize(v):
    nrm = math.sqrt(sum(x * x for x in v))
    return [x / nrm for x in v] if nrm else list(BETA0)


def grad_j(beta, entries):
    """Gradient of J(beta) = sum_r (u.beta)^2 / (beta^T G beta / nv2 ...)."""
    grad = [0.0] * P
    for u, g, nv2 in entries:
        if nv2 <= 0:
            continue
        q = quad(beta, g)
        if q <= 0:
            continue
        ub = sum(a * b for a, b in zip(u, beta))
        c1 = 2.0 * ub / (q * nv2)
        c2 = 2.0 * ub * ub / (q * q * nv2)
        gb = [sum(g[a][b] * beta[b] for b in range(P)) for a in range(P)]
        for a in range(P):
            grad[a] += c1 * u[a] - c2 * gb[a]
    return grad


def refine_beta(beta, j, entries, iters=50):
    """Projected gradient ascent on the unit sphere with backtracking.

    The power-iteration surrogate can stall at a fixed point that is not a
    stationary point of J (observed: beta returned unchanged at its seed);
    gradient refinement escapes such stalls.
    """
    beta = _normalize(beta)
    j = eval_j(beta, entries)
    for _ in range(iters):
        gr = grad_j(beta, entries)
        gn = math.sqrt(sum(x * x for x in gr))
        if gn == 0:
            break
        d = [x / gn for x in gr]
        improved = False
        for eta in (1.0, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001):
            cand = _normalize([b + eta * x for b, x in zip(beta, d)])
            cj = eval_j(cand, entries)
            if cj > j:
                beta, j = cand, cj
                improved = True
                break
        if not improved:
            break
    return beta, j


def eval_j(beta, entries):
    """J(beta) = sum_r cos^2(v_r, Phi_r beta) (per-record LS scale profiled)."""
    total = 0.0
    for u, g, nv2 in entries:
        den = quad(beta, g)
        if den <= 0 or nv2 <= 0:
            continue
        total += (sum(b * x for b, x in zip(beta, u)) ** 2) / (den * nv2)
    return total


def eval_ape(beta, lam):
    """Walk 2: per-record node APE after LS scale + cos^2, for one beta."""
    index = load_index()
    instants = sorted(index["instants"],
                      key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))
    w_state = defaultdict(dict)
    st = defaultdict(exp.new_cell_state)
    weights_cache = {}
    prev_batch_ts = {}
    out = []
    for e in instants:
        rec = _jgzload(os.path.join(FITSET_DIR, e["key"].replace("/", "_") + ".json.gz"))
        if is_stale_record(rec):
            continue
        v = [float(x) for x in rec["node_values"]]
        vmax = max((abs(x) for x in v), default=0.0)
        if vmax == 0:
            continue
        sym, ts = rec["symbol"], rec["uw_ts"]
        cache_key = (sym, ts)
        if cache_key not in weights_cache:
            prev = prev_batch_ts.get(sym)
            batch = exp.normalize_batch(rec_to_rows(rec), ts=ts, prev_ts=prev,
                                        spot=rec.get("spot"))
            w = exp.cross_expiry_weights(batch, w_state[sym])
            w_state[sym] = dict(w)
            weights_cache[cache_key] = (w, batch)
            prev_batch_ts[sym] = ts
        w, batch = weights_cache[cache_key]
        st[sym] = exp.update_cell_state(batch, st[sym], lam=lam)
        design = exp.state_node_design(batch, w, st[sym])
        strikes = [float(s) for s in rec["strikes"]]
        pred = [sum(b * x for b, x in zip(beta, design.get(s, ZERO_ROW)))
                for s in strikes]
        idx = [i for i, x in enumerate(v) if abs(x) >= MATERIAL_FRAC * vmax]
        tgt = [v[i] for i in idx]
        y = [pred[i] for i in idx]
        den = sum(x * x for x in y)
        c = (sum(a * b for a, b in zip(tgt, y)) / den) if den > 0 else 0.0
        apes = sorted(abs(c * b - a) / max(abs(a), 1e-12) for a, b in zip(tgt, y))
        med = apes[len(apes) // 2]
        d = sum(a * b for a, b in zip(tgt, y))
        na = math.sqrt(sum(a * a for a in tgt)) or 1.0
        nb = math.sqrt(sum(b * b for b in y)) or 1.0
        out.append((rec["day"], med, (d / (na * nb)) ** 2))
    return out


def quantiles(vals):
    if not vals:
        return {}
    vs = sorted(vals)
    def q(p):
        return vs[min(len(vs) - 1, max(0, int(round(p * (len(vs) - 1)))))]
    return {"min": vs[0], "p25": q(0.25), "p50": q(0.50), "p75": q(0.75),
            "p90": q(0.90), "max": vs[-1], "mean": sum(vs) / len(vs), "n": len(vs)}


# ---------------------------------------------------------------- fit cmd

def cmd_fit(apply: bool) -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    cache_dir = os.path.join(OUT_DIR, "fit_cache")
    cached = load_cache(cache_dir, LAM_GRID)
    if cached is not None:
        meta, acc = cached
        print(f"fit cache hit: {len(meta)} records from {cache_dir}")
    else:
        print(f"walk 1: {len(LAM_GRID)} lambda candidates on {FITSET_DIR}")
        meta, acc = walk(LAM_GRID, cache_dir=cache_dir)
    print(f"scored records: {len(meta)}")
    lam_table = {}
    best = None
    for lam in LAM_GRID:
        beta, j = fit_beta(acc[lam])
        lam_table[str(lam)] = {"J": round(j, 6),
                               "J_baseline": round(eval_j(BETA0, acc[lam]), 6),
                               "beta": [round(b, 6) for b in beta]}
        print(f"  lam={lam}: J={j:.4f} (baseline {lam_table[str(lam)]['J_baseline']:.4f})")
        if best is None or j > best[1]:
            best = (lam, j, beta, acc[lam])
    assert best is not None  # LAM_GRID is non-empty
    lam_star, j_star, beta_star, entries_star = best

    # leave-one-day-out on lam_star (beta fitted on the other days)
    days = sorted({d for _k, d in meta})
    loto = {}
    for hold in days:
        train = [en for en, (_k, d) in zip(entries_star, meta) if d != hold]
        test = [en for en, (_k, d) in zip(entries_star, meta) if d == hold]
        b, _j = fit_beta(train)
        loto[hold] = {"n_test": len(test),
                      "J_test": round(eval_j(b, test), 6),
                      "J_test_baseline": round(eval_j(BETA0, test), 6),
                      "beta": [round(x, 6) for x in b]}

    print(f"walk 2: evaluation at lam*={lam_star}")
    ape_base = eval_ape(BETA0, lam_star)
    ape_fit = eval_ape(beta_star, lam_star)
    base_meds = [m for _d, m, _c in ape_base]
    fit_meds = [m for _d, m, _c in ape_fit]
    fit_cos = [c for _d, _m, c in ape_fit]
    base_cos = [c for _d, _m, c in ape_base]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/e05a_state_fit.py",
        "spec": "docs/build/cross-expiry-layer-spec.md §10",
        "commands": COMMANDS,
        "input": {"fit_dataset": "data/e02/fit_dataset",
                  "index_sha256": sha256(os.path.join(FITSET_DIR, "index.json")),
                  "n_records_scored": len(meta),
                  "days": days},
        "lambda_grid": {str(lam): {"J": lam_table[str(lam)]["J"]} for lam in LAM_GRID},
        "lambda_star": lam_star,
        "lambda_table": lam_table,
        "state_beta": [round(b, 9) for b in beta_star],
        "objective": {
            "def": "J(beta) = sum_r cos^2(v_r, Phi_r beta); per-record LS scale profiled out",
            "J_fitted": round(j_star, 6),
            "J_baseline_e1": round(eval_j(BETA0, entries_star), 6),
        },
        "per_record_node_med_ape_after_ls_scale": {
            "baseline_e1": quantiles(base_meds),
            "fitted": quantiles(fit_meds),
        },
        "per_record_cos2_material_nodes": {
            "baseline_e1": quantiles(base_cos),
            "fitted": quantiles(fit_cos),
        },
        "leave_one_day_out": loto,
        "honest_note": (
            "PILOT-GRADE: fitted on 3 Tier-A days (< 20 aligned days per spec "
            "§9/§10.4.4) — overfit risk real; coefficients must be re-fit as days "
            "accrue (daily refit: python3 scripts/e05a_state_fit.py fit --apply, "
            "cron gammasummit-e02-daily-refit). The 'median node APE <= 10% over "
            "'>= 20 session-days' gate bar is measured by gate card t_b157a485 at "
            "re-measure (~2026-10-28). Strikes absent from the UW grid (24.2% of "
            "compared Tier-A nodes) are unreachable for any UW-only model (spec "
            "§10.4.5)."),
        "constants_for_exposure_py": {
            "LAMBDA_CELL": lam_star,
            "STATE_BETA": [round(b, 9) for b in beta_star],
        },
    }
    path = os.path.join(OUT_DIR, "state_fit.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", path)
    print("LAMBDA_CELL =", lam_star)
    print("STATE_BETA =", out["state_beta"])
    print("per-record node med APE p50: baseline",
          quantiles(base_meds).get("p50"), "-> fitted", quantiles(fit_meds).get("p50"))
    if apply:
        apply_constants(lam_star, out["state_beta"])
    return 0


def apply_constants(lam, beta):
    """Patch LAMBDA_CELL/STATE_BETA into exposure.py (backup first)."""
    backup = EXPOSURE_PY + ".pre-e05a.bak"
    if not os.path.exists(backup):
        shutil.copy2(EXPOSURE_PY, backup)
        print("backup:", backup)
    with open(EXPOSURE_PY) as f:
        src = f.read()
    lam_repr = repr(float(lam))
    beta_repr = "(" + ", ".join(repr(round(float(b), 9)) for b in beta) + ("," if len(beta) == 1 else "") + ")"
    src2, n1 = re.subn(r"^LAMBDA_CELL: float = .*$",
                       f"LAMBDA_CELL: float = {lam_repr}", src, count=1, flags=re.M)
    src2, n2 = re.subn(r"^STATE_BETA: Tuple\[float, \.\.\.\] = .*$",
                       f"STATE_BETA: Tuple[float, ...] = {beta_repr}", src2,
                       count=1, flags=re.M)
    if n1 != 1 or n2 != 1:
        raise SystemExit(f"apply failed: lam subs {n1}, beta subs {n2}")
    with open(EXPOSURE_PY, "w") as f:
        f.write(src2)
    print(f"applied LAMBDA_CELL={lam_repr} STATE_BETA={beta_repr} -> backend/core/exposure.py")


# ---------------------------------------------------------------- report cmd

def load_run(d):
    with open(os.path.join(d, "summary.json")) as f:
        summary = json.load(f)
    per_rec = []
    with open(os.path.join(d, "per_record.csv")) as f:
        for row in csv.DictReader(f):
            per_rec.append(row)
    node_ape = []
    n_rows = 0
    with gzip.open(os.path.join(d, "node_comparison.csv.gz"), "rt") as f:
        for row in csv.DictReader(f):
            n_rows += 1
            if row["ape"] != "":
                node_ape.append(float(row["ape"]))
    return summary, per_rec, node_ape, n_rows


def cmd_report() -> int:
    before_dir = os.path.join(OUT_DIR, "before")
    after_dir = os.path.join(OUT_DIR, "after")
    runs = {}
    for name, d in (("before", before_dir), ("after", after_dir)):
        summary, per_rec, node_ape, n_rows = load_run(d)
        med = [float(r["node_med_ape"]) for r in per_rec]
        runs[name] = {
            "dir": os.path.relpath(d, REPO),
            "summary_generated_at": summary["generated_at"],
            "model": summary.get("model"),
            "n_records": summary["n_scored"],
            "per_record_node_med_ape": quantiles(med),
            "all_node_ape": quantiles(node_ape),
            "all_node_ape_frac_le_0_10": round(sum(1 for x in node_ape if x <= 0.10)
                                               / max(len(node_ape), 1), 6),
            "node_rows_compared": n_rows,
            "king_exact_rate": summary["overall"]["king_exact_rate"],
            "king_within_tol_rate": summary["overall"]["king_within_tol_rate"],
            "top6_overlap_mean": summary["overall"]["top6_overlap_mean"],
            "per_day": {day: {"n_records": a["n_records"],
                              "node_med_ape_median": a["node_med_ape_median"],
                              "king_exact_rate": a["king_exact_rate"]}
                        for day, a in summary["per_day"].items()},
            "sha256": {p: sha256(os.path.join(d, p))
                       for p in ("summary.json", "per_record.csv", "node_comparison.csv.gz")},
        }
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "script": "scripts/e05a_state_fit.py report",
        "spec": "docs/build/cross-expiry-layer-spec.md §10",
        "commands": COMMANDS,
        "before": runs["before"],
        "after": runs["after"],
        "delta": {
            "per_record_node_med_ape_p50": (
                runs["after"]["per_record_node_med_ape"].get("p50")
                - runs["before"]["per_record_node_med_ape"].get("p50")),
            "all_node_ape_frac_le_0_10": (
                runs["after"]["all_node_ape_frac_le_0_10"]
                - runs["before"]["all_node_ape_frac_le_0_10"]),
        },
        "honest_note": (
            "Pilot-grade on 3 Tier-A days (spec §10.4.4); before = E0.3 model, "
            "after = §10 state-augmented model with constants from "
            "data/e05a/state_fit.json. The <=10% gate bar is enforced by gate "
            "card t_b157a485 at re-measure (~2026-10-28)."),
    }
    json_path = os.path.join(OUT_DIR, "before_after_report.json")
    with open(json_path, "w") as f:
        json.dump(out, f, indent=1)
    md = ["# E0.5a before/after node-error report", "",
          f"Generated: {out['generated_at']} · script `scripts/e05a_state_fit.py report`",
          "", "| metric | before (E0.3) | after (§10 state) |", "|---|---|---|"]
    b, a = runs["before"], runs["after"]
    def row(label, x, y):
        md.append(f"| {label} | {x} | {y} |")
    row("per-record node med APE p50", b["per_record_node_med_ape"].get("p50"),
        a["per_record_node_med_ape"].get("p50"))
    row("per-record node med APE p90", b["per_record_node_med_ape"].get("p90"),
        a["per_record_node_med_ape"].get("p90"))
    row("all-node APE p50", b["all_node_ape"].get("p50"), a["all_node_ape"].get("p50"))
    row("all-node frac APE ≤ 0.10", b["all_node_ape_frac_le_0_10"],
        a["all_node_ape_frac_le_0_10"])
    row("king exact rate", b["king_exact_rate"], a["king_exact_rate"])
    row("king ±tol rate", b["king_within_tol_rate"], a["king_within_tol_rate"])
    row("top6 overlap mean", b["top6_overlap_mean"], a["top6_overlap_mean"])
    row("records", b["n_records"], a["n_records"])
    md += ["", "Per-day node med APE p50:", "",
           "| day | before | after | n |", "|---|---|---|---|"]
    for day in sorted(set(b["per_day"]) | set(a["per_day"])):
        pb, pa = b["per_day"].get(day, {}), a["per_day"].get(day, {})
        md.append(f"| {day} | {pb.get('node_med_ape_median')} | "
                  f"{pa.get('node_med_ape_median')} | {pa.get('n_records', pb.get('n_records'))} |")
    md += ["", "Run commands (all numbers traceable to these runs):", ""]
    md += [f"- `{c}`" for c in COMMANDS]
    md += ["", f"Honest note: {out['honest_note']}", ""]
    md_path = os.path.join(OUT_DIR, "before_after_report.md")
    with open(md_path, "w") as f:
        f.write("\n".join(md))
    print("wrote", json_path)
    print("wrote", md_path)
    for line in md:
        print(line)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_fit = sub.add_parser("fit")
    p_fit.add_argument("--apply", action="store_true",
                       help="patch fitted constants into backend/core/exposure.py")
    sub.add_parser("report")
    args = ap.parse_args()
    if args.cmd == "fit":
        return cmd_fit(args.apply)
    return cmd_report()


if __name__ == "__main__":
    sys.exit(main())
