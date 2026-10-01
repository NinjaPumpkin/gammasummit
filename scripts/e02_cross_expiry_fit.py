#!/usr/bin/env python3
"""E0.2 — cross-expiry dynamic weighting layer: fit harness (clean-room).

Derives the missing cross-expiry dynamic weighting layer of the Skylit value
model (docs/build/skylit-value-model.md verdicts 1-4) by fitting against REAL
1s range frames + matrix grids from the X10 captures, with UW gamma_data_v2
inputs at aligned instants (card E0.1 parity dataset).

Established math (re-derived + verified here, never assumed):
  - per-strike node value  V(s,t) = SUM_e C(s,e,t)      (exact, probe: 501/501)
  - king = argmax_s |V(s,t)|  == argmax |cell| strike    (8/8 captures)
  - within-expiry strike ranking = net_gex = call_gex - put_gex
  - MISSING LAYER = cross-expiry dynamic weighting: C(s,e,t) ~ a_e(t) * g(s,e,t)

READ-ONLY against every external system (X10 exFAT, SignalForge Supabase via
PostgREST SELECT/HEAD only, SignalForge data dirs). Writes ONLY under
data/e02/ inside the gammasummit repo.

Credentials: GAMMASUMMIT_UW_URL + GAMMASUMMIT_UW_SERVICE_KEY env vars only
(--env-file loads them from a local untracked dotenv file at runtime; values
are never printed, never written to any artifact).

Subcommands:
  hypotheses   working hypothesis set -> data/e02/hypotheses.json
  uw-walk      UW cadence re-derivation (PM note 2): full-day distinct
               timestamp walk on one liquid strike x expiry + ticker-level
               walk -> data/e02/uw_cadence_walk.json
  pairs-check  per-PAIR UW freshness verdicts (stale-phx check)
               -> data/e02/pairs_freshness.json
  prepare      aligned fit dataset cache (incremental) -> data/e02/fit_dataset/
  fit          per-instant column fit + 1s dynamic fit -> data/e02/fit_results.json
  report       per-session-day residual table -> data/e02/residual_report.{json,csv}
  verify       artifact consistency checks (exit != 0 on failure)

Usage:
  python3 scripts/e02_cross_expiry_fit.py --env-file <dotenv> uw-walk
  python3 scripts/e02_cross_expiry_fit.py prepare
  python3 scripts/e02_cross_expiry_fit.py fit
  python3 scripts/e02_cross_expiry_fit.py report
  python3 scripts/e02_cross_expiry_fit.py verify
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

try:
    import numpy as np
except ImportError:  # pragma: no cover
    print("numpy is required for the fit (pip install numpy)", file=sys.stderr)
    raise SystemExit(2)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_ROOT = "/Volumes/X10 Pro/gammasummit/t3/re/raw"
SF_DATA = "/Users/admin/Desktop/Github Projects/SignalForge/data"
OUT_DIR = os.path.join(REPO, "data", "e02")
FITSET_DIR = os.path.join(OUT_DIR, "fit_dataset")
UWCACHE_DIR = os.path.join(OUT_DIR, "uw_cache")
P0_DIR = os.path.join(REPO, "data", "p0")

sys.path.insert(0, os.path.join(REPO, "scripts"))
from p0_parity_dataset import load_manifest, manifest_kind, load_matrix_file  # noqa: E402

TOL_S = float(os.environ.get("GAMMASUMMIT_ALIGN_TOL_S", "150"))
TICKERS = ("SPX", "SPY", "QQQ", "IWM")

# UW columns needed for the layer fit + feature models (subset SELECT).
UW_COLS = ("ticker,strike,expiry_date,timestamp,gex_value,call_gex,put_gex,"
           "dex_value,call_dex,put_dex,call_oi,put_oi,call_volume,put_volume,"
           "call_ask_vol,call_bid_vol,put_ask_vol,put_bid_vol,"
           "call_prev_oi,put_prev_oi,iv,spot_price,abs_gex,abs_oi,net_volume")

# Feature order stored per (strike, expiry) in the fit dataset.
FEAT_KEYS = ("net_gex", "call_gex", "put_gex", "call_oi", "put_oi",
             "call_volume", "put_volume", "call_ask_vol", "call_bid_vol",
             "put_ask_vol", "put_bid_vol", "call_prev_oi", "put_prev_oi", "iv")


# ---------------------------------------------------------------- utilities

def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _jdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)
    os.replace(tmp, path)


def _jload(path):
    with open(path) as f:
        return json.load(f)


def _jgzdump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f, separators=(",", ":"), default=str)
    os.replace(tmp, path)


def _jgzload(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def spearman(a, b) -> float:
    """Rank correlation on paired samples (ties get average ranks)."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    if len(a) < 3:
        return 0.0
    ra, rb = ranks(list(a)), ranks(list(b))
    return _pearson(ra, rb)


def _pearson(a, b) -> float:
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0


def load_env_file(path: str):
    """Load GAMMASUMMIT_UW_* from a local dotenv file (values never printed).

    Recognized keys: GAMMASUMMIT_UW_URL / GAMMASUMMIT_UW_SERVICE_KEY directly,
    or SUPABASE_URL / SUPABASE_SERVICE_KEY as aliases."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "GAMMASUMMIT_UW_URL" or k == "SUPABASE_URL":
                os.environ.setdefault("GAMMASUMMIT_UW_URL", v)
            elif k == "GAMMASUMMIT_UW_SERVICE_KEY" or k == "SUPABASE_SERVICE_KEY":
                os.environ.setdefault("GAMMASUMMIT_UW_SERVICE_KEY", v)


class UWClient:
    """Read-only PostgREST client for gamma_data_v2 (SELECT / HEAD only)."""

    def __init__(self):
        self.url = os.environ.get("GAMMASUMMIT_UW_URL", "").rstrip("/") + "/rest/v1"
        self.key = os.environ.get("GAMMASUMMIT_UW_SERVICE_KEY", "")
        if not self.key or self.url == "/rest/v1":
            raise SystemExit("set GAMMASUMMIT_UW_URL and GAMMASUMMIT_UW_SERVICE_KEY "
                             "(or pass --env-file)")

    def q(self, table, *, select="*", head=False, params=None, limit=None,
          order=None, retries=3):
        # E0.5a fix: PostgREST (Supabase) truncates every row response at the
        # server-side db-max-rows cap (measured 1000) regardless of the
        # requested limit — batch snapshots of 4,397 rows were silently cut to
        # 1,000 rows (E0.5a data bug). Row fetches now paginate via limit/offset
        # until exhausted or the requested limit is reached; HEAD unchanged.
        p = {"select": select}
        if order:
            p["order"] = order
        elif not head:
            p["order"] = "strike,expiry_date"  # stable order for offset pages
        if params:
            p.update(params)
        if head and limit is not None:
            p["limit"] = str(limit)

        def fetch(pp):
            req = urllib.request.Request(f"{self.url}/{table}?{urllib.parse.urlencode(pp)}")
            req.add_header("apikey", self.key)
            req.add_header("Authorization", f"Bearer {self.key}")
            if head:
                req.add_header("Prefer", "count=exact")
                req.method = "HEAD"
            for attempt in range(retries):
                try:
                    with urllib.request.urlopen(req, timeout=120) as r:
                        body = r.read()
                        if head:
                            return int(r.headers.get("Content-Range", "*/0").split("/")[1])
                        return json.loads(body) if body else []
                except Exception:
                    if attempt == retries - 1:
                        raise
                    time.sleep(2 * (attempt + 1))

        if head:
            return fetch(p)
        out = []
        while True:
            want = 1000 if limit is None else min(1000, limit - len(out))
            pp = dict(p)
            pp["limit"] = str(want)
            if out:
                pp["offset"] = str(len(out))
            rows = fetch(pp) or []
            out.extend(rows)
            if limit is not None and len(out) >= limit:
                return out[:limit]
            if len(rows) < want:
                return out


def _day_bounds(day: str):
    lo = f"{day}T00:00:00+00:00"
    hi = f"{(date.fromisoformat(day) + timedelta(days=1)).isoformat()}T00:00:00+00:00"
    return lo, hi


def distinct_ts_walk(uw: UWClient, day: str, ticker: str = "SPX",
                     strike: float | None = None, expiry: str | None = None) -> list[str]:
    """Full-day DISTINCT timestamp walk (one query per distinct ts)."""
    lo, hi = _day_bounds(day)
    params = {"ticker": f"eq.{ticker}"}
    if strike is not None:
        params["strike"] = f"eq.{strike:g}"
    if expiry:
        params["expiry_date"] = f"eq.{expiry}"
    out, cursor = [], lo
    while True:
        params["and"] = f"(timestamp.gte.{cursor},timestamp.lt.{hi})"
        rows = uw.q("gamma_data_v2", select="timestamp", params=params,
                    order="timestamp.asc", limit=1)
        if not rows:
            break
        ts = rows[0]["timestamp"]
        if out and ts == out[-1]:
            break
        out.append(ts)
        cursor = ts.replace("+00:00", "+00:00.000001") if ts.endswith("+00:00") else ts + "+00:00.000001"
        if len(out) > 4000:
            break
    return out


def uw_rows_cached(uw: UWClient, ts: str, ticker: str) -> list[dict]:
    """Rows of one (batch ts, ticker) snapshot, cached under data/e02/uw_cache/."""
    os.makedirs(UWCACHE_DIR, exist_ok=True)
    fn = re.sub(r"[^0-9A-Za-z]", "_", f"{ts}_{ticker}") + ".json.gz"
    path = os.path.join(UWCACHE_DIR, fn)
    if os.path.exists(path):
        return _jgzload(path)
    rows = []
    for tk in [ticker]:
        rows += uw.q("gamma_data_v2", select=UW_COLS,
                     params={"ticker": f"eq.{tk}", "timestamp": f"eq.{ts}"},
                     limit=20000)
    _jgzdump(rows, path)
    return rows


def walk_cache_path() -> str:
    return os.path.join(OUT_DIR, "uw_cadence_walk.json")


def day_walk_ts(day: str, uw: UWClient | None = None) -> list[str]:
    """Canonical UW snapshot timestamps for one day.

    Ticker-level distinct walk is the superset (PM note 2 experiment 2026-09-30:
    strike-level walk finds FEWER timestamps — a strike x expiry row is only
    written on some batches — so the ticker walk is canonical)."""
    w = _jload(walk_cache_path()) if os.path.exists(walk_cache_path()) else {}
    rec = w.get("days", {}).get(day)
    if rec and rec.get("ticker_walk"):
        return rec["ticker_walk"]
    if uw is None:
        uw = UWClient()
    return distinct_ts_walk(uw, day, "SPX")


# ---------------------------------------------------------------- hypotheses

HYPOTHESES = {
    "context": (
        "Skylit value model verdicts 1-4 (docs/build/skylit-value-model.md): "
        "static chain formulas fail (rho<=0.15); flow-augmented fails (top-q 0.092); "
        "star = argmax|value| cell solved 21/21; within-expiry net_gex ranks their "
        "star top-3 75% in own column; cross-expiry column-magnitude ratios swing "
        "1.2->13.3 intraday and match no static gex/oi/vol/flow factor; DTE power "
        "laws alone fail; whole-grid scale swings 55M->231M in one day."),
    "established": {
        "V_node": "V(s,t) = SUM_e C(s,e,t)   [exact: 501/501 strikes, X10 matrix 09-30 13:30 SPX]",
        "king": "king = argmax_s |V(s,t)| = strike of argmax|cell|  [8/8 sampled captures]",
        "within_expiry": "cell strike ranking ~ net_gex = call_gex - put_gex (verdict 4: top-3 75%)",
    },
    "model_class": (
        "C(s,e,t) = a_e(t) * g(s,e,t),  g = net_gex(UW),  a_e(t) = cross-expiry "
        "dynamic weight x per-unit scale (their private $ scale lives in a_e). "
        "V(s,t) = SUM_e a_e(t) * g(s,e,t). The layer to fit is t -> a_e(t)."),
    "hypotheses": [
        {"id": "H0-uniform", "formula": "a_e(t) = kappa(t)",
         "note": "single common scale; no cross-expiry structure. Baseline."},
        {"id": "H1-dte-power", "formula": "a_e(t) = kappa(t) * d_e^(-beta), d_e = DTE_e",
         "note": "static DTE power law + common intraday scale. Verdict 4: DTE power "
                 "laws fail alone; kept as mandatory baseline."},
        {"id": "H2-colmag", "formula": "a_e(t) = kappa(t) * |G_e(t)|^gamma, G_e = SUM_s |g(s,e,t)|",
         "note": "column self-scaling by gross gex magnitude."},
        {"id": "H3-dte-colmag", "formula": "a_e(t) = kappa(t) * d_e^(-beta) * |G_e(t)|^gamma",
         "note": "static two-factor."},
        {"id": "H4-ewma-state", "formula": "a_e(t) = lam*a_e(t-dt) + (1-lam)*psi_e(t), "
                "psi_e(t) = exp(theta0 + theta'x_e(t)) with x = [log d_e, log|G_e|, "
                "net-gex sign, ask/bid imbalance, dOI migration, dGEX rate 5m/30m]",
         "note": "dynamic accumulation/unwinding state (their doctrine: rate of "
                 "change, node growth/decay, rolling ceilings/floors)."},
        {"id": "H5-flow-augmented-ewma", "formula": "H4 + flow features "
                "(signed ask-bid volume imbalance per column, prev_oi migration)",
         "note": "verdict 2 says RECENT flow premium does not drive cells; flow enters "
                 "only as slow state (migration), not as recent-premium weight."},
    ],
    "fit_target": {
        "primary": "X10 range/gamma 1s frames: V(s,t) at 1s resolution "
                   "(26 x 15-min windows x 900 frames/day/symbol)",
        "secondary": "X10 matrix/gamma cells C(s,e,t) at 1-min cadence (Tier A days)",
        "inputs": "UW gamma_data_v2 rows at aligned batch snapshots (dt <= TOL_S)",
    },
    "acceptance": "<=10% median error on node values per session-day; king exact "
                  ">=90% over >=20 session-days (gate wording unchanged; days accrue "
                  "live per E0.1 Option 1 forward-fill)",
}


def cmd_hypotheses(_args):
    out = os.path.join(OUT_DIR, "hypotheses.json")
    _jdump(HYPOTHESES, out)
    print("wrote", out)
    for h in HYPOTHESES["hypotheses"]:
        print(f"  {h['id']}: {h['formula']}")
    return 0


# ---------------------------------------------------------------- uw-walk

def cmd_uw_walk(args):
    os.makedirs(OUT_DIR, exist_ok=True)
    uw = UWClient()
    days = args.days.split(",") if args.days else tier_a_days()
    out = {"probed_at": datetime.now(timezone.utc).isoformat(),
           "tol_note": "PM note 2: probes ~1/min (231-438/day) vs manifest walk "
                       "185-318/day -> aligned yields conservative; re-derived here.",
           "days": {}}
    for day in days:
        # ticker-level walk (the E0.1 manifest method)
        tlv = distinct_ts_walk(uw, day, "SPX")
        # strike-level walk on one liquid strike x expiry (PM note 2)
        lo, hi = _day_bounds(day)
        sample = uw.q("gamma_data_v2", select="strike,expiry_date",
                      params={"ticker": "eq.SPX",
                              "and": f"(timestamp.gte.{lo},timestamp.lt.{hi})"},
                      limit=2000)
        cnt = Counter((r["strike"], r["expiry_date"]) for r in sample)
        (st, ex), n = cnt.most_common(1)[0] if cnt else ((None, None), 0)
        slw = distinct_ts_walk(uw, day, "SPX", strike=float(st), expiry=ex) if st else []
        rec = {
            "ticker_walk": tlv, "n_ticker_walk": len(tlv),
            "walk_target": {"ticker": "SPX", "strike": st, "expiry": ex,
                            "sample_rows": len(sample), "sample_hits": n},
            "strike_walk": slw, "n_strike_walk": len(slw),
        }
        if slw:
            dts = [(_ts(b) - _ts(a)).total_seconds() for a, b in zip(slw, slw[1:])]
            dts.sort()
            rec["strike_walk_cadence_s"] = {
                "min": dts[0], "median": dts[len(dts) // 2], "max": dts[-1]}
        out["days"][day] = rec
        print(day, "ticker_walk:", rec["n_ticker_walk"], "strike_walk:", rec["n_strike_walk"],
              rec.get("strike_walk_cadence_s", ""), flush=True)
    _jdump(out, walk_cache_path())
    print("wrote", walk_cache_path())
    return 0


# ---------------------------------------------------------------- pairs-check

def cmd_pairs_check(_args):
    pairs_dir = os.path.join(SF_DATA, "skylit_pairs")
    same = _jload(os.path.join(SF_DATA, "skylit_sameinstant_v2.json"))
    need = same.get("need", {})
    uw_by_ts = defaultdict(list)
    for r in same.get("rows", []):
        uw_by_ts[r["timestamp"]].append(r)
    out = {"checked_at": datetime.now(timezone.utc).isoformat(),
           "rule": "chain_verdict: stale if PAIR chains contain contracts expiring "
                   "BEFORE the PAIR capture date (free phx endpoint served "
                   "~4-day-stale chains). usable_for_gate: fresh UW rows "
                   "(gamma_data_v2 via sameinstant_v2) exist within 90s of the "
                   "GRID's own timestamp (grid instant retargets the pairing — "
                   "grid scrape lag does not invalidate the PAIR).",
           "pairs": []}
    for fn in sorted(os.listdir(pairs_dir)):
        if fn.startswith("._") or not fn.endswith(".json"):
            continue
        p = _jload(os.path.join(pairs_dir, fn))
        cap = _ts(p["captured_utc"])
        grid = p.get("grid") or {}
        grid_cap_s = grid.get("captured_utc")
        grid_cap = _ts(grid_cap_s.replace("Z", "+00:00")) if grid_cap_s else cap
        chains = p.get("chains", [])
        n_chain = len(chains)
        exps = sorted({c["expires"] for c in chains})
        expired = [e for e in exps if e < cap.date().isoformat()]
        sum_oi = sum(float(c.get("open_interest") or 0) for c in chains)
        sum_vol = sum(float(c.get("volume") or 0) for c in chains)
        rec = {
            "pair": fn, "captured_utc": p["captured_utc"],
            "grid_captured_utc": grid_cap_s,
            "grid_lag_s": round((cap - grid_cap).total_seconds(), 1),
            "ticker": p.get("ticker"), "uw_spot": p.get("uw_spot"),
            "n_chains": n_chain, "n_expiries": len(exps),
            "expired_expiries_in_chain": expired[:6],
            "sum_oi": sum_oi, "sum_volume": sum_vol,
            "star_cell": next((c for c in grid.get("cells", []) if c.get("star")), None),
        }
        verdict, evidence = "fresh", []
        if expired:
            verdict = "stale"
            evidence.append(f"chains carry {len(expired)} already-expired expiries")
        # same-instant cross-check where gamma_data_v2 rows exist
        usable = False
        if fn in need:
            uw_ts, dt_s = need[fn][0], need[fn][1]
            rows = uw_by_ts.get(uw_ts.replace("+00:00", "+00:00"), [])
            if not rows:
                for k in uw_by_ts:
                    if k.startswith(uw_ts[:19]):
                        rows = uw_by_ts[k]
                        break
            rec["sameinstant_uw_ts"] = uw_ts
            rec["sameinstant_dt_s"] = dt_s
            if rows:
                uw_oi = sum(float(r.get("call_oi") or 0) + float(r.get("put_oi") or 0)
                            for r in rows)
                rec["sameinstant_sum_oi"] = uw_oi
                if uw_oi > 0:
                    ratio = sum_oi / uw_oi
                    rec["oi_ratio_chain_vs_uw"] = round(ratio, 3)
                    if abs(ratio - 1) > 0.20:
                        evidence.append(f"chain total OI deviates from UW: ratio {ratio:.2f}")
                usable = abs(float(dt_s)) <= 90
                if not usable:
                    evidence.append(f"UW rows {dt_s}s off grid instant (>90s)")
            else:
                evidence.append("no same-instant UW rows found in cache")
        else:
            evidence.append("not in sameinstant_v2 need set (no UW cross-check available)")
        rec["chain_verdict"] = verdict
        rec["usable_for_gate"] = usable
        rec["evidence"] = evidence
        out["pairs"].append(rec)
        print(fn, "chains:", verdict, "| gate-usable:", usable, flush=True)
    n_stale = sum(1 for r in out["pairs"] if r["chain_verdict"] == "stale")
    n_usable = sum(1 for r in out["pairs"] if r["usable_for_gate"])
    out["summary"] = {"n_pairs": len(out["pairs"]), "n_chains_stale": n_stale,
                      "n_chains_fresh": len(out["pairs"]) - n_stale,
                      "n_usable_for_gate": n_usable}
    path = os.path.join(OUT_DIR, "pairs_freshness.json")
    _jdump(out, path)
    print("wrote", path, out["summary"])
    return 0


# ---------------------------------------------------------------- prepare

def tier_a_days() -> list[str]:
    fr = os.path.join(P0_DIR, "session_day_frames.json")
    if os.path.exists(fr):
        d = _jload(fr)
        return [f["session_day"] for f in d["frames"]
                if f.get("status", "").startswith("aligned")]
    return ["2026-09-28", "2026-09-29", "2026-09-30"]


def stale_symbol_days() -> set:
    p = os.path.join(P0_DIR, "re_inventory.json")
    if not os.path.exists(p):
        return set()
    inv = _jload(p)
    return {k for k, n in inv.get("asof_stale_by_symbol_day", {}).items() if n}


def cmd_prepare(args):
    os.makedirs(FITSET_DIR, exist_ok=True)
    uw = UWClient()
    days = args.days.split(",") if args.days else tier_a_days()
    tol = float(args.tol) if args.tol else TOL_S
    manifest = [r for r in load_manifest()
                if manifest_kind(r) == "matrix/gamma" and r["t"][:10] in days]
    stale = stale_symbol_days()
    idx_path = os.path.join(FITSET_DIR, "index.json")
    index = _jload(idx_path) if os.path.exists(idx_path) else {"instants": []}
    have = {e["key"] for e in index["instants"]}
    t0 = time.time()
    n_new = n_skip = n_nomatch = 0
    for rec in sorted(manifest, key=lambda r: r["t"]):
        day = rec["t"][:10]
        path = rec["file"]
        win = os.path.basename(path).replace(".json.gz", "")
        m = load_matrix_file(path)
        walk = day_walk_ts(day, uw)
        for sym in TICKERS:
            key = f"{day}/{win}_{sym}"
            if key in have:
                n_skip += 1
                continue
            s = m["symbols"].get(sym)
            if not s or not s.get("asOf"):
                continue
            asof = s["asOf"]
            t = _ts(asof)
            best, best_dt = None, None
            for wts in walk:
                dt = abs((_ts(wts) - t).total_seconds())
                if best_dt is None or dt < best_dt:
                    best, best_dt = wts, dt
            if best is None or best_dt is None or best_dt > tol:
                n_nomatch += 1
                continue
            rows = uw_rows_cached(uw, best, sym)
            if not rows:
                n_nomatch += 1
                continue
            exps = s["expirations"]
            eidx = {e: j for j, e in enumerate(exps)}
            strikes = [x["strike"] for x in s["strikes"]]
            dense = [[0.0] * len(exps) for _ in strikes]
            # cells keys carry float(strike); map back to grid index
            sidx = {}
            for i, x in enumerate(s["strikes"]):
                sidx[float(x["strike"])] = i
            for (st, e), v in s["cells"].items():
                i, j = sidx.get(float(st)), eidx.get(e)
                if i is not None and j is not None:
                    dense[i][j] = float(v)
            uwmap = defaultdict(dict)  # (strike) -> {expiry: [feats]}
            for r in rows:
                e = r["expiry_date"]
                if e not in eidx:
                    continue
                st = float(r["strike"])
                net = float(r.get("call_gex") or 0) - float(r.get("put_gex") or 0)
                feats = [net]
                for k in FEAT_KEYS[1:]:
                    v = r.get(k)
                    feats.append(float(v) if v is not None else 0.0)
                uwmap[st][e] = feats
            rec_out = {
                "day": day, "window": win, "symbol": sym, "asOf": asof,
                "uw_ts": best, "dt_s": round(best_dt, 2),
                "spot": s.get("spot"),
                "stale_symbol": f"{sym}|{day}" in stale,
                "expiries": exps,
                "strikes": strikes,
                "node_values": [x["value"] for x in s["strikes"]],
                "node_types": [x.get("nodeType") for x in s["strikes"]],
                "cells": dense,
                "uw": {f"{st:g}": exp for st, exp in uwmap.items()},
                "feat_keys": ["net_gex"] + list(FEAT_KEYS[1:]),
            }
            _jgzdump(rec_out, os.path.join(FITSET_DIR, f"{key.replace('/', '_')}.json.gz"))
            index["instants"].append({"key": key, "day": day, "window": win,
                                      "symbol": sym, "asOf": asof, "uw_ts": best,
                                      "dt_s": round(best_dt, 2)})
            have.add(key)
            n_new += 1
            if n_new % 20 == 0:
                index["built_at"] = datetime.now(timezone.utc).isoformat()
                index["tol_s"] = tol
                index["days"] = sorted({e["day"] for e in index["instants"]})
                _jdump(index, idx_path)
        if (n_new + n_skip) % 40 == 0:
            print(f"  ... {n_new} new, {n_skip} cached, elapsed {time.time()-t0:.0f}s",
                  flush=True)
    index["built_at"] = datetime.now(timezone.utc).isoformat()
    index["tol_s"] = tol
    index["days"] = sorted({e["day"] for e in index["instants"]})
    _jdump(index, idx_path)
    print(f"prepare done: {n_new} new instants, {n_skip} cached, {n_nomatch} without "
          f"UW match within {tol}s")
    print("index:", idx_path, "total instants:", len(index["instants"]))
    return 0


# ---------------------------------------------------------------- fit

def _iter_fitset(index):
    for e in index["instants"]:
        p = os.path.join(FITSET_DIR, f"{e['key'].replace('/', '_')}.json.gz")
        if os.path.exists(p):
            yield _jgzload(p)


def is_stale_record(rec) -> bool:
    """Per-record staleness: |asOf - window_start| > 2s (E0.1 fidelity note 2).
    More precise than the symbol-day map (which flags whole days when ANY
    record is stale)."""
    try:
        win_start = datetime.fromisoformat(
            f"{rec['day']}T{rec['window'][:2]}:{rec['window'][2:4]}:{rec['window'][4:6]}+00:00")
        asof = _ts(rec["asOf"].replace("Z", "+00:00"))
        return abs((asof - win_start).total_seconds()) > 2
    except Exception:
        return bool(rec.get("stale_symbol"))


def _feat_matrices(rec):
    """Dense C (S x E) and G (S x E, net_gex) + secondary feature tensors."""
    exps = rec["expiries"]
    eidx = {e: j for j, e in enumerate(exps)}
    strikes = rec["strikes"]
    C = np.array(rec["cells"], dtype=float)
    G = np.zeros_like(C)
    for st_str, emap in rec["uw"].items():
        st = float(st_str)
        # map to nearest grid strike (exact match expected)
        try:
            i = next(i for i, x in enumerate(strikes) if float(x) == st)
        except StopIteration:
            continue
        for e, feats in emap.items():
            j = eidx.get(e)
            if j is not None:
                G[i, j] = float(feats[0])
    return strikes, exps, C, G


def fit_instant(rec):
    """Per-expiry column fit + aggregate node/king scoring for one instant."""
    strikes, exps, C, G = _feat_matrices(rec)
    V = np.array(rec["node_values"], dtype=float)
    S, E = C.shape
    a = np.zeros(E)
    col_stats = []
    for j in range(E):
        g = G[:, j]
        c = C[:, j]
        mask = g != 0
        n = int(mask.sum())
        if n < 5 or float((g[mask] ** 2).sum()) == 0:
            col_stats.append({"expiry": exps[j], "n": n, "a": None})
            continue
        aj = float((c[mask] * g[mask]).sum() / (g[mask] ** 2).sum())
        a[j] = aj
        rho = spearman(c[mask].tolist(), g[mask].tolist())
        capp = float((c[mask] ** 2).sum())
        resid = float(((c[mask] - aj * g[mask]) ** 2).sum())
        col_stats.append({"expiry": exps[j], "n": n, "a": aj, "rho": round(rho, 4),
                          "col_r2": round(1 - resid / capp, 4) if capp > 0 else None})
    Vhat = G @ a
    return a, Vhat, V, col_stats


def _agg_metrics(Vhat, V, strikes, king_actual, topn=6):
    """Node-value + king metrics for one instant (their $ scale, direct fit)."""
    vmax = float(np.abs(V).max()) if len(V) else 0.0
    if vmax == 0:
        return None
    mat = np.abs(V) >= 0.05 * vmax
    err = np.abs(Vhat - V)[mat] / np.maximum(np.abs(V[mat]), 1e-12)
    med = float(np.median(err)) if len(err) else None
    p90 = float(np.percentile(err, 90)) if len(err) else None
    king_pred = int(strikes[int(np.argmax(np.abs(Vhat)))])
    king_true = int(king_actual) if king_actual is not None else int(strikes[int(np.argmax(np.abs(V)))])
    top_pred = np.argsort(-np.abs(Vhat))[:topn]
    top_true = np.argsort(-np.abs(V))[:topn]
    overlap = len(set(top_pred.tolist()) & set(top_true.tolist()))
    return {"node_med_ape": med, "node_p90_ape": p90,
            "king_pred": king_pred, "king_true": king_true,
            "king_exact": king_pred == king_true,
            "top6_overlap": overlap}


def king_tol(symbol: str) -> int:
    return 25 if symbol == "SPX" else 5


FEATURE_NAMES = ["log_dte", "log_gmag", "net_col_sign_log", "askbid_imbalance",
                 "doi_migration", "com_dist_rel", "tod_frac"]


def expiry_features(rec, G, j, FEAT):
    """Production-legal feature row for expiry column j (UW-only inputs)."""
    e = rec["expiries"][j]
    dte = max((date.fromisoformat(e) - date.fromisoformat(rec["day"])).days, 0.25)
    g = G[:, j]
    gmag = float(np.abs(g).sum())
    net_col = float(g.sum())
    i_ = FEAT  # per-strike feature rows: dict strike_str -> {expiry: feats}
    ask = bid = 0.0
    doi = 0.0
    for st_str, emap in i_.items():
        feats = emap.get(e)
        if not feats:
            continue
        ask += feats[7] + feats[9]
        bid += feats[8] + feats[10]
        doi += (feats[3] - feats[11]) + (feats[4] - feats[12])
    imb = (ask - bid) / (ask + bid + 1.0)
    spot = float(rec.get("spot") or 0.0)
    strikes = np.array([float(x) for x in rec["strikes"]])
    if gmag > 0 and spot > 0:
        com = float((np.abs(g) * strikes).sum() / gmag)
        com_dist = abs(com - spot) / spot
    else:
        com_dist = 0.0
    t = _ts(rec["asOf"].replace("Z", "+00:00"))
    tod = (t.hour * 60 + t.minute) / (24 * 60)
    return [math.log(dte), math.log(gmag + 1.0),
            math.copysign(math.log1p(abs(net_col)), net_col),
            imb, math.copysign(math.log1p(abs(doi)), doi),
            com_dist, tod]


def fit_feature_model(index, samples):
    """H4/H5 psi model: log|a_e| ~ linear production-legal features (UW-only),
    sign(a_e) = sign(column net gex), plus leave-one-day-out end-to-end scoring."""
    out = {"n_samples": len(samples),
           "feature_names": ["intercept"] + FEATURE_NAMES,
           "model": "a_hat_e(t) = sgn(net_col_e) * exp(theta'x_e(t)); "
                    "per-instant scale kappa(t) = LS scalar vs free-fit a"}
    if len(samples) < 30:
        out["status"] = "insufficient samples"
        return out
    X = np.array([s["x"] for s in samples], dtype=float)
    y = np.log(np.abs(np.array([s["a"] for s in samples])))
    Xd = np.column_stack([np.ones(len(samples)), X])
    theta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    pred = Xd @ theta
    ss_tot = float(((y - y.mean()) ** 2).sum())
    out["theta"] = [round(float(v), 6) for v in theta]
    out["r2_log_abs_a"] = (round(1 - float(((y - pred) ** 2).sum()) / ss_tot, 4)
                           if ss_tot > 0 else None)
    sgn_a = np.sign([s["a"] for s in samples])
    sgn_net = np.sign(X[:, 2])
    out["sign_agreement_vs_netcol"] = round(float((sgn_a == sgn_net).mean()), 4)
    out["a_positive_share"] = round(float((sgn_a > 0).mean()), 4)

    # leave-one-day-out: fit theta on N-1 days, score held-out day end-to-end
    days = sorted({s["day"] for s in samples})
    inst_by_key = {e["key"]: e for e in index["instants"]}
    loo = {}
    for day in days:
        train = [s for s in samples if s["day"] != day]
        test = [s for s in samples if s["day"] == day]
        if not train or not test:
            continue
        Xt = np.column_stack([np.ones(len(train)),
                              np.array([s["x"] for s in train], dtype=float)])
        yt = np.log(np.abs(np.array([s["a"] for s in train])))
        th, *_ = np.linalg.lstsq(Xt, yt, rcond=None)
        werrs, sign_ok, n_s = [], 0, 0
        for s in test:
            x = np.array([1.0] + s["x"], dtype=float)
            ahat = math.exp(float(th @ x))
            sign_hat = 1.0 if s["x"][2] >= 0 else -1.0
            sign_ok += 1 if sign_hat == (1.0 if s["a"] > 0 else -1.0) else 0
            n_s += 1
            werrs.append(abs(ahat - abs(s["a"])) / max(abs(s["a"]), 1e-12))
        # end-to-node: all instants of the held-out day
        meds, ke, kt, n_i = [], 0, 0, 0
        for e in inst_by_key.values():
            if e["day"] != day:
                continue
            p = os.path.join(FITSET_DIR, f"{e['key'].replace('/', '_')}.json.gz")
            if not os.path.exists(p):
                continue
            rec = _jgzload(p)
            if is_stale_record(rec):
                continue
            strikes, exps, C, G = _feat_matrices(rec)
            ahat = np.zeros(len(exps))
            for j in range(len(exps)):
                x = np.array([1.0] + expiry_features(rec, G, j, rec["uw"]), dtype=float)
                sgn = 1.0 if x[3] >= 0 else -1.0   # x[3] == net_col_sign_log
                ahat[j] = sgn * math.exp(float(th @ x))
            free = {s["expiry"]: s["a"] for s in samples if s["key"] == e["key"]}
            if not free:
                continue
            num = sum(free[ex] * ahat[exps.index(ex)] for ex in free if ex in exps)
            den = sum(ahat[exps.index(ex)] ** 2 for ex in free if ex in exps)
            kap = num / den if den else 0.0
            Vhat = G @ (kap * ahat)
            V = np.array(rec["node_values"], dtype=float)
            king_actual = next((rec["strikes"][i] for i, nt in enumerate(rec["node_types"])
                                if nt == "king"), None)
            met = _agg_metrics(Vhat, V, rec["strikes"], king_actual)
            if met is None:
                continue
            tol = king_tol(rec["symbol"])
            meds.append(met["node_med_ape"])
            ke += 1 if met["king_exact"] else 0
            kt += 1 if abs(met["king_pred"] - met["king_true"]) <= tol else 0
            n_i += 1
        loo[day] = {
            "n_weight_samples": n_s,
            "weight_sign_acc": round(sign_ok / n_s, 3) if n_s else None,
            "weight_med_rel_err": round(float(np.median(werrs)), 3) if werrs else None,
            "n_instants_scored": n_i,
            "node_med_ape_median": round(float(np.median(meds)), 4) if meds else None,
            "king_exact_pct": round(100 * ke / n_i, 1) if n_i else None,
            "king_within_tol_pct": round(100 * kt / n_i, 1) if n_i else None,
        }
        print(f"  LOTO {day}: node_med_ape={loo[day]['node_med_ape_median']} "
              f"king%={loo[day]['king_exact_pct']} sign_acc={loo[day]['weight_sign_acc']}",
              flush=True)
    out["leave_one_day_out"] = loo
    return out


def cmd_fit(args):
    idx = os.path.join(FITSET_DIR, "index.json")
    if not os.path.exists(idx):
        raise SystemExit("run prepare first")
    index = _jload(idx)
    results = {
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "tol_s": index.get("tol_s"),
        "n_instants": 0,
        "per_instant": [],
        "per_day": {},
        "sign_stats": {},
        "dynamic": {},
    }
    sign_pos = sign_neg = 0
    by_day = defaultdict(lambda: {"inst": [], "cols": []})
    samples: list = []
    t0 = time.time()
    for rec in _iter_fitset(index):
        if is_stale_record(rec):
            continue
        a, Vhat, V, col_stats = fit_instant(rec)
        king_actual = None
        for i, nt in enumerate(rec["node_types"]):
            if nt == "king":
                king_actual = rec["strikes"][i]
        met = _agg_metrics(Vhat, V, rec["strikes"], king_actual)
        if met is None:
            continue
        tol = king_tol(rec["symbol"])
        met["king_within_tol"] = abs(met["king_pred"] - met["king_true"]) <= tol
        strikes, exps, C, G = _feat_matrices(rec)
        # joint aggregate fit: a_tilde = argmin ||V - G a||^2 (ridge) — the
        # right estimator for node/king placement of the cross-expiry layer
        GtG = G.T @ G
        lam = 1e-3 * float(np.trace(GtG)) / max(1, G.shape[1])
        try:
            at = np.linalg.solve(GtG + lam * np.eye(G.shape[1]), G.T @ V)
        except np.linalg.LinAlgError:
            at = a
        met_j = _agg_metrics(G @ at, V, rec["strikes"], king_actual) or {}
        met_j["king_within_tol"] = abs(met_j.get("king_pred", 0) - met_j.get("king_true", 0)) <= tol
        # baselines on the same instant
        base = {}
        dte = np.array([(date.fromisoformat(e) - date.fromisoformat(rec["day"])).days
                        for e in exps], dtype=float)
        dte = np.maximum(dte, 0.25)

        def sse(av):
            R = C - G * av[None, :]
            m = G != 0
            return float((R[m] ** 2).sum())
        sse_free = sse(a)
        # H0 uniform
        if float((G ** 2).sum()) > 0:
            a0 = float((C * G).sum() / (G ** 2).sum())
            base["H0-uniform"] = {"sse_ratio": sse(np.full(len(exps), a0)) / sse_free if sse_free else None}
        # H1 DTE power: grid beta
        best = (None, math.inf)
        for beta in np.arange(0.0, 3.01, 0.05):
            shape = dte ** (-beta)
            if float((shape ** 2).sum()) == 0:
                continue
            num = float((C * G * shape[None, :]).sum())
            den = float(((G ** 2) * (shape[None, :] ** 2)).sum())
            if den == 0:
                continue
            kap = num / den
            s = sse(kap * shape)
            if s < best[1]:
                best = (float(beta), s, float(kap))
        if best[0] is not None:
            base["H1-dte-power"] = {"beta": best[0], "kappa": best[2],
                                    "sse_ratio": best[1] / sse_free if sse_free else None}
        # H2 column magnitude (shape normalized by max -> scale absorbed by kappa)
        Gmag = np.abs(G).sum(axis=0)
        gmax = float(Gmag.max()) if float(Gmag.max()) > 0 else 1.0
        best2 = (None, math.inf)
        for gamma in np.arange(-2.0, 2.01, 0.1):
            shape = np.where(Gmag > 0, (Gmag / gmax) ** gamma, 0.0)
            num = float((C * G * shape[None, :]).sum())
            den = float(((G ** 2) * (shape[None, :] ** 2)).sum())
            if den == 0:
                continue
            kap = num / den
            s = sse(kap * shape)
            if s < best2[1]:
                best2 = (float(gamma), s, float(kap))
        if best2[0] is not None:
            base["H2-colmag"] = {"gamma": best2[0], "kappa": best2[2],
                                 "sse_ratio": best2[1] / sse_free if sse_free else None}
        for j in range(len(exps)):
            if a[j] != 0:
                sign_pos += 1 if a[j] > 0 else 0
                sign_neg += 1 if a[j] < 0 else 0
        entry = {
            "key": f"{rec['day']}/{rec['window']}_{rec['symbol']}",
            "day": rec["day"], "symbol": rec["symbol"], "asOf": rec["asOf"],
            "uw_ts": rec["uw_ts"], "dt_s": rec["dt_s"],
            "metrics": met, "metrics_joint": met_j, "baselines": base,
            "col_quality": {
                "n_cols_fit": sum(1 for c in col_stats if c["a"] is not None),
                "median_rho": statistics.median(
                    [c["rho"] for c in col_stats if c["a"] is not None] or [0]),
                "median_col_r2": statistics.median(
                    [c["col_r2"] for c in col_stats if c["a"] is not None and c["col_r2"] is not None] or [0]),
            },
            "a": [round(float(x), 6) for x in a],
        }
        # feature samples for the psi model (H4/H5)
        for j in range(len(rec["expiries"])):
            if col_stats[j]["a"] is not None and a[j] != 0:
                samples.append({
                    "key": entry["key"], "day": rec["day"], "symbol": rec["symbol"],
                    "expiry": rec["expiries"][j], "a": float(a[j]),
                    "x": expiry_features(rec, G, j, rec["uw"]),
                })
        results["per_instant"].append(entry)
        by_day[rec["day"]]["inst"].append(entry)
        results["n_instants"] += 1
        if results["n_instants"] % 50 == 0:
            print(f"  fitted {results['n_instants']} instants ({time.time()-t0:.0f}s)",
                  flush=True)
    # per-day summary
    for day, dd in sorted(by_day.items()):
        inst = dd["inst"]
        meds = [i["metrics"]["node_med_ape"] for i in inst if i["metrics"]["node_med_ape"] is not None]
        p90s = [i["metrics"]["node_p90_ape"] for i in inst if i["metrics"]["node_p90_ape"] is not None]
        ke = sum(1 for i in inst if i["metrics"]["king_exact"])
        kt = sum(1 for i in inst if i["metrics"]["king_within_tol"])
        t6 = [i["metrics"]["top6_overlap"] for i in inst]
        jm = [i["metrics_joint"]["node_med_ape"] for i in inst
              if i.get("metrics_joint", {}).get("node_med_ape") is not None]
        jke = sum(1 for i in inst if i.get("metrics_joint", {}).get("king_exact"))
        jkt = sum(1 for i in inst if i.get("metrics_joint", {}).get("king_within_tol"))
        jt6 = [i["metrics_joint"].get("top6_overlap", 0) for i in inst]
        results["per_day"][day] = {
            "n_instants": len(inst),
            "node_med_ape_median": statistics.median(meds) if meds else None,
            "node_p90_ape_median": statistics.median(p90s) if p90s else None,
            "king_exact_pct": round(100 * ke / len(inst), 1),
            "king_within_tol_pct": round(100 * kt / len(inst), 1),
            "top6_overlap_mean": round(sum(t6) / len(t6), 2) if t6 else None,
            "joint_node_med_ape_median": statistics.median(jm) if jm else None,
            "joint_king_exact_pct": round(100 * jke / len(inst), 1),
            "joint_king_within_tol_pct": round(100 * jkt / len(inst), 1),
            "joint_top6_overlap_mean": round(sum(jt6) / len(jt6), 2) if jt6 else None,
        }
    results["sign_stats"] = {"a_positive": sign_pos, "a_negative": sign_neg}
    results["feature_model"] = fit_feature_model(index, samples)
    path = os.path.join(OUT_DIR, "fit_results.json")
    _jdump(results, path)   # flush before the long dynamic stage
    try:
        results["dynamic"] = fit_dynamic(index)
    except Exception as ex:  # dynamic stage must never lose the static results
        results["dynamic"] = {"error": repr(ex)}
    _jdump(results, path)
    print("wrote", path, "| instants:", results["n_instants"])
    for day, s in results["per_day"].items():
        print(f"  {day}: n={s['n_instants']} medAPE={s['node_med_ape_median']} "
              f"p90={s['node_p90_ape_median']} king%={s['king_exact_pct']} "
              f"king±tol%={s['king_within_tol_pct']} top6={s['top6_overlap_mean']}")
    return 0


def fit_dynamic(index):
    """1s dynamic layer fit on range frames.

    Range files carry the LIVE strike window as `axes[]` (the grid grows and
    shrinks with spot — probe 9); each frame pins its `axis` id and its
    `values` follow THAT axis's strike list. g is frozen at the nearest UW
    snapshot per window; residual includes UW-feature staleness (documented
    as validity bound in the spec).
    """
    days = sorted({e["day"] for e in index["instants"]})
    dyn = {"windows_processed": 0, "frames_processed": 0, "per_day": {},
           "model": {}, "notes": [
               "g frozen at nearest UW snapshot per window; residual includes "
               "UW-feature staleness (validity bound documented in spec)",
               "range axes = live strike windows (grid grows/shrinks with spot); "
               "frames map through their pinned axis id"]}
    inst_by = defaultdict(list)
    for e in index["instants"]:
        inst_by[(e["day"], e["symbol"])].append(e)
    for day in days:
        dsum = {"windows": 0, "frames": 0, "emp_r2_median": None, "ewma": {}}
        emp_all = []
        r2s_all = []
        for sym in TICKERS:
            win_dir = os.path.join(RAW_ROOT, "range", "gamma", day)
            if not os.path.isdir(win_dir):
                continue
            for fn in sorted(os.listdir(win_dir)):
                if fn.startswith("._") or not fn.endswith(".json.gz"):
                    continue
                recs = inst_by.get((day, sym))
                if not recs:
                    continue
                rng = load_range_file_path(os.path.join(win_dir, fn))
                if sym not in rng["symbols"]:
                    continue
                sd = rng["symbols"][sym]
                frames = sd["frames"]
                if not frames:
                    continue
                wstart = _ts(rng["from"].replace("Z", "+00:00"))
                near = min(recs, key=lambda e: abs((_ts(e["asOf"].replace("Z", "+00:00"))
                                                    - wstart).total_seconds()))
                rec = _jgzload(os.path.join(
                    FITSET_DIR, f"{near['key'].replace('/', '_')}.json.gz"))
                strikes, exps, C, G = _feat_matrices(rec)
                sidx = {float(x): i for i, x in enumerate(strikes)}
                E = len(exps)
                per_axis = {}
                for ax in sd["axes"]:
                    ax_strikes = [float(x) for x in ax.get("strikes", [])]
                    pairs = [(ri, sidx[s]) for ri, s in enumerate(ax_strikes) if s in sidx]
                    if not pairs:
                        continue
                    rows_r = [p[0] for p in pairs]
                    Gr = G[[p[1] for p in pairs], :]
                    keepE = np.abs(Gr).sum(axis=0) > 0
                    if int(keepE.sum()) < 2:
                        continue
                    Grk = Gr[:, keepE]
                    GtG = Grk.T @ Grk
                    lam = 1e-3 * float(np.trace(GtG)) / max(1, Grk.shape[1])
                    A = GtG + lam * np.eye(Grk.shape[1])
                    per_axis[ax.get("id", 0)] = (rows_r, Grk, A, keepE)
                if not per_axis:
                    continue
                r2s = []
                for fi, fr in enumerate(frames):
                    if fi % 5 != 0:   # 0.2 Hz subsample for trajectory fitting
                        continue
                    pa = per_axis.get(fr.get("axis", 0))
                    if pa is None:
                        continue
                    rows_r, Grk, A, keepE = pa
                    vals_all = fr.get("values", [])
                    if len(vals_all) <= max(rows_r):
                        continue
                    vals = np.array(vals_all, dtype=float)[rows_r]
                    if float(np.abs(vals).max()) == 0:
                        continue
                    rhs = Grk.T @ vals
                    try:
                        ah = np.linalg.solve(A, rhs)
                    except np.linalg.LinAlgError:
                        continue
                    pred = Grk @ ah
                    ss = float(((vals - pred) ** 2).sum())
                    st = float(((vals - vals.mean()) ** 2).sum())
                    r2s.append(1 - ss / st if st > 0 else 0.0)
                    full = np.zeros(E)
                    full[keepE] = ah
                    emp_all.append({
                        "day": day, "symbol": sym, "window": fn, "fi": fi,
                        "asOf": fr["asOf"], "a_hat": full.tolist(),
                    })
                dsum["frames"] += len(r2s)
                r2s_all += r2s
                dsum["windows"] += 1
                dyn["windows_processed"] += 1
                dyn["frames_processed"] += len(r2s)
        dsum["emp_r2_median"] = statistics.median(r2s_all) if r2s_all else None
        # EWMA lambda on empirical trajectories (per symbol, per expiry)
        ewma = {}
        for sym in TICKERS:
            tr = sorted([e for e in emp_all if e["symbol"] == sym],
                        key=lambda e: e["asOf"])
            byexp = defaultdict(list)
            for e in tr:
                for j, av in enumerate(e["a_hat"]):
                    if av != 0:
                        byexp[j].append((_ts(e["asOf"]), av))
            best_lam, best_sse = None, math.inf
            grid = {}
            for lam in (0.0, 0.5, 0.9, 0.95, 0.98, 0.99, 0.995):
                # one-step-ahead prediction: w_{k+1} ~ lam*w_k + (1-lam)*mean_e
                sse_l, n_l = 0.0, 0
                for j, series in byexp.items():
                    if len(series) < 10:
                        continue
                    mean_e = sum(v for _, v in series) / len(series)
                    for k in range(len(series) - 1):
                        pred = lam * series[k][1] + (1 - lam) * mean_e
                        sse_l += (series[k + 1][1] - pred) ** 2
                        n_l += 1
                if n_l:
                    grid[str(lam)] = sse_l / n_l
                    if sse_l / n_l < best_sse:
                        best_sse = sse_l / n_l
                        best_lam = lam
            ewma[sym] = {"lambda": best_lam,
                         "mse": best_sse if best_sse < math.inf else None,
                         "mse_grid": grid,
                         "n_traj_points": sum(len(v) for v in byexp.values())}
        dsum["ewma"] = ewma
        dyn["per_day"][day] = dsum
        print(f"  dynamic {day}: windows={dsum['windows']} frames={dsum['frames']} "
              f"emp_r2_med={dsum['emp_r2_median']}", flush=True)
    return dyn


def load_range_file_path(path):
    with gzip.open(path, "rt") as f:
        d = json.load(f)
    data = d.get("data", {})
    out = {"meta": d.get("meta", {}), "from": data.get("from"), "to": data.get("to"),
           "symbols": {}}
    for sym in data.get("symbols", []):
        out["symbols"][sym["symbol"]] = {"axes": sym.get("axes", []),
                                         "frames": sym.get("frames", [])}
    return out


# ---------------------------------------------------------------- report

def cmd_report(_args):
    path = os.path.join(OUT_DIR, "fit_results.json")
    if not os.path.exists(path):
        raise SystemExit("run fit first")
    res = _jload(path)
    rep = {"generated_at": datetime.now(timezone.utc).isoformat(),
           "acceptance": "target <= 10% median error on node values per session-day",
           "per_day": res.get("per_day", {}),
           "sign_stats": res.get("sign_stats", {}),
           "dynamic": {d: {k: v for k, v in s.items() if k != "ewma"}
                       for d, s in res.get("dynamic", {}).get("per_day", {}).items()},
           "ewma": {d: s.get("ewma") for d, s in res.get("dynamic", {}).get("per_day", {}).items()},
           "verdicts": {}}
    for day, s in res.get("per_day", {}).items():
        med = s.get("node_med_ape_median")
        jmed = s.get("joint_node_med_ape_median")
        rep["verdicts"][day] = {
            "per_column_basis": "MET" if med is not None and med <= 0.10 else "NOT-MET",
            "joint_aggregate": "MET" if jmed is not None and jmed <= 0.10 else "NOT-MET",
        }
    csvp = os.path.join(OUT_DIR, "residual_report.csv")
    with open(csvp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session_day", "n_instants", "node_med_ape", "node_p90_ape",
                    "king_exact_pct", "king_within_tol_pct", "top6_overlap_mean",
                    "joint_node_med_ape", "joint_king_exact_pct",
                    "joint_king_within_tol_pct", "joint_top6_overlap_mean",
                    "verdict"])
        for day, s in res.get("per_day", {}).items():
            w.writerow([day, s["n_instants"], s["node_med_ape_median"],
                        s["node_p90_ape_median"], s["king_exact_pct"],
                        s["king_within_tol_pct"], s["top6_overlap_mean"],
                        s.get("joint_node_med_ape_median"),
                        s.get("joint_king_exact_pct"),
                        s.get("joint_king_within_tol_pct"),
                        s.get("joint_top6_overlap_mean"),
                        rep["verdicts"][day]["joint_aggregate"]])
    outp = os.path.join(OUT_DIR, "residual_report.json")
    _jdump(rep, outp)
    print("wrote", outp, "and", csvp)
    for day, s in res.get("per_day", {}).items():
        print(f"  {day}: medAPE={s['node_med_ape_median']} "
              f"joint_medAPE={s.get('joint_node_med_ape_median')} "
              f"verdicts={rep['verdicts'][day]}")
    return 0


# ---------------------------------------------------------------- verify

def cmd_verify(_args):
    ok = True
    need_files = ["hypotheses.json", "fit_results.json", "residual_report.json",
                  "fit_dataset/index.json"]
    for n in need_files:
        p = os.path.join(OUT_DIR, n)
        exists = os.path.exists(p)
        print(("OK  " if exists else "MISS"), p)
        ok &= exists
    if ok:
        idx = _jload(os.path.join(OUT_DIR, "fit_dataset", "index.json"))
        res = _jload(os.path.join(OUT_DIR, "fit_results.json"))
        print("instants cached:", len(idx["instants"]),
              "| instants fitted:", res["n_instants"])
        ok &= res["n_instants"] > 0
        for day, s in res.get("per_day", {}).items():
            print(f"  {day}: n={s['n_instants']} medAPE={s['node_med_ape_median']} "
                  f"king%={s['king_exact_pct']}")
            ok &= s["n_instants"] > 0
        # cross-check: every fitted instant exists in the cache index
        keys = {e["key"] for e in idx["instants"]}
        missing = [i["key"] for i in res["per_instant"] if i["key"] not in keys]
        print("fitted instants missing from cache:", len(missing))
        ok &= not missing
    print("VERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", help="local dotenv with SUPABASE_URL / "
                                       "SUPABASE_SERVICE_KEY (or GAMMASUMMIT_UW_*); "
                                       "values never printed")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hypotheses")
    p = sub.add_parser("uw-walk")
    p.add_argument("--days", help="comma-separated YYYY-MM-DD (default: Tier-A days)")
    sub.add_parser("pairs-check")
    p = sub.add_parser("prepare")
    p.add_argument("--days", help="comma-separated YYYY-MM-DD (default: Tier-A days)")
    p.add_argument("--tol", help="alignment tolerance seconds (default 150)")
    sub.add_parser("fit")
    sub.add_parser("report")
    sub.add_parser("verify")
    args = ap.parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    return {"hypotheses": cmd_hypotheses, "uw-walk": cmd_uw_walk,
            "pairs-check": cmd_pairs_check, "prepare": cmd_prepare,
            "fit": cmd_fit, "report": cmd_report, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
