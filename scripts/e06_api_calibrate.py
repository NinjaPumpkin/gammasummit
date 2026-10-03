#!/usr/bin/env python3
"""E0.6 Skylit API calibration harness (clean-room) — card t_3a0b0ae0.

Owner directive 2026-10-01 (docs/build/heatmap-formula-handoff.md):
$-label constant-fitting is CLOSED (proven impossible). The winning path is
CALIBRATION against the live Skylit API (temporary RE tool, sub ends ~Nov 2026;
production runs UW-only):

  (a) nodeType tiers are RANK-based per symbol -- king = single top |value|,
      gatekeeper = next band (3-10), pika = exactly 3, barney = exactly 3,
      order by |value|: normal < barney < pika < gatekeeper < king.
      Replicate the ranking, not absolute thresholds.
  (b) per-symbol sign/scale constants: their `value` vs our net GEX node
      aggregates (Spearman SPY +0.26 / SPX -0.46 / QQQ -0.51 reported on the
      first side-by-side; test sign families: call-put, put-call, abs, gross,
      call, put, gex_value, net_dex) + per-symbol scale residual.
  (c) velocityPct per strike -> calibrate our velocity channel
      r = Delta(cell_$) / max|Delta(cell_$)| (two-channel spec, handoff).

Metrics saved per run + aggregated (data/e06/calibration/):
  per-symbol Spearman per sign family, scale ratio + scale residual,
  nodeType rank-match (king exact, top6 overlap, tier-set overlap),
  velocity Spearman (their velocityPct vs our r / raw Delta).

Usage (pulls cost credits: /v1/heatmap = 1 credit per run -- keep cheap):

  python3 scripts/e06_api_calibrate.py pull    [--execute] [--symbols SPY,SPX,QQQ,IWM]
  python3 scripts/e06_api_calibrate.py analyze [--execute]

Secrets: SKYLIT_API_KEY from .env; UW PostgREST creds from the runtime
env-file (default: SignalForge/.env, read-only) -- values never printed,
never written to artifacts. Clean-room: own client code, no reference-system
code read or copied.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import numpy as np
from scipy.stats import spearmanr

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "data", "e06", "calibration")
RUN_DIR = os.path.join(OUT_DIR, "runs")
DEFAULT_UW_ENV = "/Users/admin/Desktop/Github Projects/SignalForge/.env"

UW_COLS = ("ticker,strike,expiry_date,timestamp,gex_value,call_gex,put_gex,"
           "dex_value,call_dex,put_dex,call_oi,put_oi,call_volume,put_volume,"
           "call_ask_vol,call_bid_vol,put_ask_vol,put_bid_vol,"
           "call_prev_oi,put_prev_oi,iv,spot_price,abs_gex,abs_oi,net_volume")


def _load_env(path):
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k in ("GAMMASUMMIT_UW_URL", "SUPABASE_URL"):
            os.environ.setdefault("GAMMASUMMIT_UW_URL", v)
        elif k in ("GAMMASUMMIT_UW_SERVICE_KEY", "SUPABASE_SERVICE_KEY"):
            os.environ.setdefault("GAMMASUMMIT_UW_SERVICE_KEY", v)
        elif k in ("SKYLIT_API_KEY", "GAMMASUMMIT_SKYLIT_API_KEY"):
            os.environ.setdefault("SKYLIT_API_KEY", v)


def skylit_key():
    k = os.environ.get("SKYLIT_API_KEY", "")
    if not k and os.path.exists(os.path.join(REPO, ".env")):
        _load_env(os.path.join(REPO, ".env"))
        k = os.environ.get("SKYLIT_API_KEY", "")
    return k


class UW:
    """Read-only PostgREST client for gamma_data_v2 (SELECT / HEAD only)."""

    def __init__(self, env_file=DEFAULT_UW_ENV):
        if env_file and os.path.exists(env_file):
            _load_env(env_file)
        self.url = os.environ.get("GAMMASUMMIT_UW_URL", "").rstrip("/") + "/rest/v1"
        self.key = os.environ.get("GAMMASUMMIT_UW_SERVICE_KEY", "")
        if not self.key or self.url == "/rest/v1":
            raise SystemExit("UW creds not found (env-file: %s)" % env_file)

    def q(self, table, *, select="*", params=None, limit=None, order=None):
        p = {"select": select}
        p["order"] = order or "strike,expiry_date"
        if params:
            p.update(params)
        out = []
        while True:
            want = 1000 if limit is None else min(1000, limit - len(out))
            pp = dict(p)
            pp["limit"] = str(want)
            if out:
                pp["offset"] = str(len(out))
            req = urllib.request.Request(
                f"{self.url}/{table}?{urllib.parse.urlencode(pp)}")
            req.add_header("apikey", self.key)
            req.add_header("Authorization", f"Bearer {self.key}")
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=120) as r:
                        rows = json.loads(r.read() or "[]")
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(2 * (attempt + 1))
            out.extend(rows)
            if limit is not None and len(out) >= limit:
                return out[:limit]
            if len(rows) < want:
                return out


def pull_heatmap(symbols):
    key = skylit_key()
    if not key:
        raise SystemExit("SKYLIT_API_KEY missing (.env)")
    url = ("https://api.skylit.ai/v1/heatmap?"
           + urllib.parse.urlencode({"symbols": ",".join(symbols)}))
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def cmd_pull(execute, symbols):
    hm = pull_heatmap(symbols)
    syms = hm["data"]["symbols"]
    asof = {s["symbol"]: s["asOf"] for s in syms}
    print("pulled:", {k: v for k, v in asof.items()})
    uw_snap = {}
    if execute:
        uw = UW()
        for s in syms:
            sym, ts = s["symbol"], s["asOf"]
            rows = uw.q("gamma_data_v2", select=UW_COLS, params={
                "ticker": f"eq.{sym}",
                "and": f"(timestamp.lte.{ts})",
            }, order="timestamp.desc", limit=1)
            if not rows:
                print(f"  UW: no rows <= {ts} for {sym}")
                continue
            best_ts = rows[0]["timestamp"]
            snap = uw.q("gamma_data_v2", select=UW_COLS, params={
                "ticker": f"eq.{sym}", "timestamp": f"eq.{best_ts}"}, limit=20000)
            # previous batch for the velocity channel
            prev = uw.q("gamma_data_v2", select=UW_COLS, params={
                "ticker": f"eq.{sym}",
                "and": f"(timestamp.lt.{best_ts})",
            }, order="timestamp.desc", limit=1)
            prev_rows = []
            if prev:
                prev_rows = uw.q("gamma_data_v2", select=UW_COLS, params={
                    "ticker": f"eq.{sym}",
                    "timestamp": f"eq.{prev[0]['timestamp']}"}, limit=20000)
            uw_snap[sym] = {"ts": best_ts,
                            "prev_ts": prev[0]["timestamp"] if prev else None,
                            "rows": snap, "prev_rows": prev_rows}
            print(f"  UW {sym}: ts={best_ts} rows={len(snap)} "
                  f"prev_rows={len(prev_rows)}")
        os.makedirs(RUN_DIR, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = os.path.join(RUN_DIR, f"pull_{run_id}.json")
        with open(path, "w") as f:
            json.dump({"heatmap": hm, "uw": uw_snap}, f, default=str)
        with open(os.path.join(RUN_DIR, "index.jsonl"), "a") as f:
            f.write(json.dumps({
                "run_id": run_id, "path": path, "symbols": symbols,
                "asOf": asof, "n_uw_rows": {k: len(v["rows"])
                                            for k, v in uw_snap.items()},
            }) + "\n")
        print("written:", path)
    else:
        print("(dry-run; pass --execute to save pull + UW snapshot)")
    return 0


# ---------------------------------------------------------------- analyze

def _rank_corr(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 5 or np.all(a[m] == a[m][0]) or np.all(b[m] == b[m][0]):
        return None
    return round(float(spearmanr(a[m], b[m]).statistic), 4)


def _node_aggregates(uw_rows):
    """Per-strike aggregates from UW rows (one batch): sign families."""
    agg = {}
    for r in uw_rows:
        s = float(r["strike"])
        a = agg.setdefault(s, {k: 0.0 for k in (
            "net_gex", "put_minus_call", "abs_gex", "gross", "call_gex",
            "put_gex", "gex_value", "net_dex", "abs_oi", "net_volume")})
        cg = float(r["call_gex"] or 0)
        pg = float(r["put_gex"] or 0)
        a["net_gex"] += cg - pg
        a["put_minus_call"] += pg - cg
        a["abs_gex"] += float(r["abs_gex"] or 0)
        a["gross"] += abs(cg) + abs(pg)
        a["call_gex"] += cg
        a["put_gex"] += pg
        a["gex_value"] += float(r["gex_value"] or 0)
        a["net_dex"] += float(r["call_dex"] or 0) - float(r["put_dex"] or 0)
        a["abs_oi"] += float(r["abs_oi"] or 0)
        a["net_volume"] += float(r["net_volume"] or 0)
    return agg


def analyze_run(path):
    run = json.load(open(path))
    hm = run["heatmap"]
    uw_snap = run["uw"]
    out = {"path": path, "symbols": {}}
    for s in hm["data"]["symbols"]:
        sym = s["symbol"]
        their = s["strikes"]
        snap = uw_snap.get(sym)
        if not snap:
            continue
        agg = _node_aggregates(snap["rows"])
        prev_agg = _node_aggregates(snap["prev_rows"]) if snap["prev_rows"] else {}
        # their heatmap aggregates only the listed expiries (5 near ones);
        # restriction measured to lift Spearman (E0.6, 2026-10-01)
        exps5 = set(s.get("expirations") or [])
        agg5 = _node_aggregates([r for r in snap["rows"]
                                 if r["expiry_date"] in exps5])
        their_val = [float(t["value"]) for t in their]
        their_abs = [abs(v) for v in their_val]
        their_vel = [float(t.get("velocityPct") or 0) for t in their]
        types = [t.get("nodeType") or "normal" for t in their]
        strikes = [float(t["strike"]) for t in their]

        fams = {}
        fam_sources = {}
        for fam in ("net_gex", "put_minus_call", "abs_gex", "gross",
                    "call_gex", "put_gex", "gex_value", "net_dex"):
            fam_sources[fam] = (fam, agg)
        fam_sources["net_gex_5exp"] = ("net_gex", agg5)
        fam_sources["put_minus_call_5exp"] = ("put_minus_call", agg5)
        fam_sources["abs_gex_5exp"] = ("abs_gex", agg5)
        fam_sources["gross_5exp"] = ("gross", agg5)
        for fam, (key, src) in fam_sources.items():
            ours = [src.get(k, {}).get(key, 0.0) for k in strikes]
            rho = _rank_corr(their_val, ours)
            # scale ratio on same-sign material rows
            ratios = []
            sign_ok = n_sign = 0
            for tv, ov in zip(their_val, ours):
                if ov != 0:
                    n_sign += 1
                    sign_ok += (tv >= 0) == (ov >= 0)
                if tv != 0 and ov != 0 and (tv >= 0) == (ov >= 0):
                    ratios.append(tv / ov)
            fams[fam] = {
                "spearman": rho,
                "scale_ratio_median": (round(float(np.median(ratios)), 6)
                                       if ratios else None),
                "scale_ratio_p25": (round(float(np.percentile(ratios, 25)), 6)
                                    if ratios else None),
                "scale_ratio_p75": (round(float(np.percentile(ratios, 75)), 6)
                                    if ratios else None),
                "sign_agreement": (round(sign_ok / n_sign, 4)
                                   if n_sign else None),
                "n_rows": len(strikes),
            }

        # nodeType structure: counts + rank monotonicity + rank-match
        counts = {}
        for t in types:
            counts[t] = counts.get(t, 0) + 1
        tier_med = {}
        for tier in set(types):
            vals = [a for a, t in zip(their_abs, types) if t == tier]
            tier_med[tier] = float(np.median(vals))
        order_expected = ["normal", "barney", "pika", "gatekeeper", "king"]
        rank_ok = all(
            tier_med.get(order_expected[i], -1) <= tier_med.get(order_expected[i + 1], 0) + 1e-300
            for i in range(len(order_expected) - 1)
            if order_expected[i] in tier_med and order_expected[i + 1] in tier_med)

        fam_best = max(fams.items(),
                       key=lambda kv: abs(kv[1]["spearman"] or 0))
        best_fam = fam_best[0]
        best_key, best_src = fam_sources[best_fam]
        ours_best = [best_src.get(k, {}).get(best_key, 0.0) for k in strikes]
        order_ours = sorted(range(len(strikes)),
                            key=lambda i: -abs(ours_best[i]))
        king_i = next((i for i, t in enumerate(types) if t == "king"), None)
        king_pred = strikes[order_ours[0]] if order_ours else None
        top6 = set(strikes[i] for i in order_ours[:6])
        their_non_normal = {strikes[i] for i, t in enumerate(types)
                            if t != "normal"}
        their_top6 = set(sorted(strikes, key=lambda k: -their_abs[strikes.index(k)])[:6])

        # velocity channel: their velocityPct vs our r / raw delta
        vel = {}
        if prev_agg:
            d_now = {k: agg[k]["net_gex"] - prev_agg.get(k, {}).get("net_gex", 0.0)
                     for k in agg}
            maxd = max((abs(v) for v in d_now.values()), default=0.0)
            r_chan = {k: (v / maxd if maxd > 0 else 0.0)
                      for k, v in d_now.items()}
            vel = {
                "spearman_vel_vs_delta": _rank_corr(
                    their_vel, [d_now.get(k, 0.0) for k in strikes]),
                "spearman_vel_vs_r": _rank_corr(
                    their_vel, [r_chan.get(k, 0.0) for k in strikes]),
                "prev_ts": snap.get("prev_ts"),
            }

        out["symbols"][sym] = {
            "asOf": s["asOf"], "spot": s["spot"],
            "n_strikes": len(strikes),
            "sign_families": fams,
            "best_family": best_fam,
            "nodeType_counts": counts,
            "nodeType_median_abs_value": {k: round(v, 3)
                                          for k, v in tier_med.items()},
            "nodeType_rank_monotonic": rank_ok,
            "rank_match": {
                "king_pred": king_pred,
                "king_true": (strikes[king_i] if king_i is not None else None),
                "king_exact": (king_i is not None
                               and king_pred == strikes[king_i]),
                "top6_overlap": len(top6 & their_top6),
                "their_non_normal_in_our_top6": len(top6 & their_non_normal),
                "n_their_non_normal": len(their_non_normal),
            },
            "velocity": vel,
        }
    return out


def cmd_analyze(execute):
    idx_path = os.path.join(RUN_DIR, "index.jsonl")
    if not os.path.exists(idx_path):
        raise SystemExit("no pulls yet -- run `pull --execute` first")
    runs = [json.loads(l) for l in open(idx_path) if l.strip()]
    analyses = [analyze_run(r["path"]) for r in runs]
    agg = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "script": "scripts/e06_api_calibrate.py analyze",
           "n_runs": len(analyses),
           "per_symbol": {}, "runs": analyses}
    syms = sorted({s for a in analyses for s in a["symbols"]})
    for sym in syms:
        fam_rows = {}
        for fam in ("net_gex", "put_minus_call", "abs_gex", "gross",
                    "call_gex", "put_gex", "gex_value", "net_dex",
                    "net_gex_5exp", "put_minus_call_5exp", "abs_gex_5exp",
                    "gross_5exp"):
            vals = [a["symbols"][sym]["sign_families"][fam]["spearman"]
                    for a in analyses if sym in a["symbols"]
                    and a["symbols"][sym]["sign_families"][fam]["spearman"]
                    is not None]
            scales = [a["symbols"][sym]["sign_families"][fam]["scale_ratio_median"]
                      for a in analyses if sym in a["symbols"]
                      and a["symbols"][sym]["sign_families"][fam]["scale_ratio_median"]
                      is not None]
            fam_rows[fam] = {
                "spearman_per_run": vals,
                "spearman_median": (round(float(np.median(vals)), 4)
                                    if vals else None),
                "scale_ratio_median": (round(float(np.median(scales)), 6)
                                       if scales else None),
            }
        vel_vals = [a["symbols"][sym]["velocity"].get("spearman_vel_vs_r")
                    for a in analyses if sym in a["symbols"]
                    and a["symbols"][sym]["velocity"].get("spearman_vel_vs_r")
                    is not None]
        king_hits = [a["symbols"][sym]["rank_match"]["king_exact"]
                     for a in analyses if sym in a["symbols"]]
        agg["per_symbol"][sym] = {
            "sign_families": fam_rows,
            "velocity_spearman_r_per_run": vel_vals,
            "velocity_spearman_r_median": (round(float(np.median(vel_vals)), 4)
                                           if vel_vals else None),
            "king_exact_rate": (round(sum(king_hits) / len(king_hits), 4)
                                if king_hits else None),
        }
    print(json.dumps({s: {k: v for k, v in d.items() if k != "sign_families"}
                      for s, d in agg["per_symbol"].items()}, indent=1))
    for sym, d in agg["per_symbol"].items():
        best = max(d["sign_families"].items(),
                   key=lambda kv: abs(kv[1]["spearman_median"] or 0))
        print(f"{sym}: best family {best[0]} spearman "
              f"{best[1]['spearman_median']} scale {best[1]['scale_ratio_median']}")
    if execute:
        path = os.path.join(OUT_DIR, "analysis.json")
        os.makedirs(OUT_DIR, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(agg, f, indent=1, default=str)
        os.replace(tmp, path)
        print("written:", path)
    else:
        print("(dry-run; pass --execute to write)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["pull", "analyze"])
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--symbols", default="SPY,SPX,QQQ,IWM")
    args = ap.parse_args()
    if args.command == "pull":
        return cmd_pull(args.execute, args.symbols.split(","))
    return cmd_analyze(args.execute)


if __name__ == "__main__":
    sys.exit(main())
