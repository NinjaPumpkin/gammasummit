#!/usr/bin/env python3
"""E0.7 UW-PHX ticker tradability features + candidate score (clean-room).

Computes, per target date, a per-ticker feature vector from UW PHX Supabase
tables ONLY (production source of truth):

  top_chains          per-day per-ticker top contracts (volume + OI sorts)
  flow_scores         per-print flow score / bonus / sweep flag (alert subset)
  iv_history          ATM IV snapshots per ticker
  uw_earnings_upcoming event proximity fields
  ticker_universe     optionable/universe tier metadata

Feature set (see docs/build/skylit-ticker-selection-model.md):
  f1 day premium (dedup contract rows; premium = avg_price * volume * 100)
  f2 premium percentile vs ticker's own trailing baseline
  f3 RVOL = day volume / trailing avg volume
  f4 OI change (sum oi - sum prev_oi, and pct)
  f5 Vol/OI ratio (accumulation proxy)
  f6 ask-side share (aggression proxy)
  f7 chain breadth (n contracts, n strikes proxy)
  f8 IV context (latest iv_atm) + event proximity (days to earnings)

Score v0: mean of available per-feature cross-sectional percentiles (equal
weights — NOT fitted; candidate for the validation replay). All inputs are UW
PHX; leandata is never read here.

Usage:
  python3 scripts/e07_uw_features.py --dates 2026-09-29 2026-09-30 2026-10-01
  python3 scripts/e07_uw_features.py --dates ... --lookback-days 20
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import statistics
import sys
import time
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "e07")


def load_env():
    env = {}
    for p in (os.path.join(ROOT, ".env"), "/Users/admin/Desktop/Github Projects/SignalForge/.env"):
        if not os.path.isfile(p):
            continue
        for line in open(p):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


ENV = load_env()
URL = (ENV.get("GAMMASUMMIT_UW_URL") or ENV.get("SUPABASE_URL") or "").rstrip("/") + "/rest/v1/"
KEY = ENV.get("GAMMASUMMIT_UW_SERVICE_KEY") or ENV.get("SUPABASE_SERVICE_KEY") or ""


def get(table: str, params: str) -> list[dict]:
    req = urllib.request.Request(URL + table + "?" + params,
                                 headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def paged(table: str, params: str, max_rows: int = 30000) -> list[dict]:
    out, off = [], 0
    while off < max_rows:
        batch = get(table, f"{params}&limit=1000&offset={off}")
        out += batch
        if len(batch) < 1000:
            break
        off += 1000
        time.sleep(0.05)
    return out


_DAY_CACHE: dict[str, dict] = {}


def day_topchains(day: str) -> dict[str, dict]:
    """Per-ticker aggregates from top_chains for one trade date (rows deduped
    by option_symbol: a contract can appear under both sort types)."""
    if day in _DAY_CACHE:
        return _DAY_CACHE[day]
    rows = paged("top_chains",
                 "select=option_symbol,ticker,volume,avg_price,open_interest,prev_oi,"
                 "ask_volume,bid_volume,mid_volume,strike,expiry"
                 f"&trade_date=eq.{day}")
    seen: dict[str, dict] = {}
    for r in rows:
        sym = r.get("option_symbol") or f"{r['ticker']}|{r.get('strike')}|{r.get('expiry')}"
        prev = seen.get(sym)
        # volume/oi sorts carry identical contract facts; keep first, but if the
        # row differs keep the max-volume variant defensively
        if prev is None or (r.get("volume") or 0) > (prev.get("volume") or 0):
            seen[sym] = r
    agg: dict[str, dict] = defaultdict(lambda: {"contracts": 0, "volume": 0, "premium": 0.0,
                                                "oi": 0, "prev_oi": 0, "ask_volume": 0,
                                                "bid_volume": 0, "mid_volume": 0, "strikes": set()})
    for r in seen.values():
        a = agg[r["ticker"]]
        vol = float(r.get("volume") or 0)
        px = float(r.get("avg_price") or 0)
        a["contracts"] += 1
        a["volume"] += vol
        a["premium"] += px * vol * 100.0
        a["oi"] += float(r.get("open_interest") or 0)
        a["prev_oi"] += float(r.get("prev_oi") or 0)
        a["ask_volume"] += float(r.get("ask_volume") or 0)
        a["bid_volume"] += float(r.get("bid_volume") or 0)
        a["mid_volume"] += float(r.get("mid_volume") or 0)
        a["strikes"].add(r.get("strike"))
    for t, a in agg.items():
        a["n_strikes"] = len(a["strikes"])
        del a["strikes"]
    _DAY_CACHE[day] = dict(agg)
    return _DAY_CACHE[day]


def trailing_baselines(days: list[str]) -> dict[str, dict]:
    """per ticker: mean/std of daily volume+premium over lookback days that have
    data (top_chains history)."""
    series: dict[str, dict] = defaultdict(lambda: {"volume": [], "premium": []})
    for day in days:
        agg = day_topchains(day)
        for t, a in agg.items():
            series[t]["volume"].append(a["volume"])
            series[t]["premium"].append(a["premium"])
        print(f"  baseline day {day}: {len(agg)} tickers", file=sys.stderr)
    out = {}
    for t, s in series.items():
        out[t] = {
            "n_days": len(s["volume"]),
            "vol_mean": statistics.fmean(s["volume"]),
            "vol_std": statistics.pstdev(s["volume"]) if len(s["volume"]) > 1 else 0.0,
            "prem_mean": statistics.fmean(s["premium"]),
            "prem_std": statistics.pstdev(s["premium"]) if len(s["premium"]) > 1 else 0.0,
        }
    return out


def flow_scores_for(day: str) -> dict[str, dict]:
    rows = paged("flow_scores",
                 "select=ticker,premium,flow_score,flow_bonus,is_sweep,direction,size"
                 f"&ts=gte.{day}T00:00:00Z&ts=lt.{day}T23:59:59Z", max_rows=8000)
    agg: dict[str, dict] = defaultdict(lambda: {"n": 0, "premium": 0.0, "sweeps": 0,
                                                "fs_sum": 0.0, "fb_sum": 0.0})
    for r in rows:
        a = agg[r["ticker"]]
        a["n"] += 1
        a["premium"] += float(r.get("premium") or 0)
        a["sweeps"] += 1 if r.get("is_sweep") else 0
        a["fs_sum"] += float(r.get("flow_score") or 0)
        a["fb_sum"] += float(r.get("flow_bonus") or 0)
    for t, a in agg.items():
        a["flow_score_mean"] = a["fs_sum"] / a["n"] if a["n"] else 0.0
        a["flow_bonus_mean"] = a["fb_sum"] / a["n"] if a["n"] else 0.0
        a["sweep_share"] = a["sweeps"] / a["n"] if a["n"] else 0.0
        del a["fs_sum"], a["fb_sum"]
    return dict(agg)


def iv_latest() -> dict[str, float]:
    out: dict[str, tuple] = {}
    rows = paged("iv_history", "select=ticker,ts,iv_atm&order=ts.desc", max_rows=30000)
    for r in rows:
        t = r["ticker"]
        if t not in out:
            out[t] = (r["ts"], float(r.get("iv_atm") or 0))
    return {t: v[1] for t, v in out.items()}


def earnings_map() -> dict[str, dict]:
    rows = paged("uw_earnings_upcoming", "select=symbol,report_date,market_cap_size,sector,is_s_p_500,expected_move", max_rows=500)
    return {r["symbol"]: r for r in rows}


def pct_rank(values: dict[str, float]) -> dict[str, float]:
    """Cross-sectional percentile rank in [0,1] (average ties not handled — fine
    for scoring candidates)."""
    items = sorted((v, t) for t, v in values.items() if v is not None)
    n = len(items)
    return {t: (i / (n - 1)) if n > 1 else 0.5 for i, (_, t) in enumerate(items)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--lookback-days", type=int, default=20)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    all_days = sorted({d for d in args.dates})
    print("loading baselines (top_chains history)...", file=sys.stderr)

    for D in args.dates:
        # baseline = last N lookback calendar days that HAVE top_chains rows
        # (found via cheap HEAD count=exact per day, walking backwards from D)
        d_end = datetime.date.fromisoformat(D)
        days: list[str] = []
        probe_day = d_end - datetime.timedelta(days=1)
        floor = d_end - datetime.timedelta(days=int(args.lookback_days * 1.7))
        while probe_day >= floor and len(days) < args.lookback_days:
            ds = probe_day.isoformat()
            req = urllib.request.Request(URL + "top_chains?select=trade_date&trade_date=eq." + ds,
                                         headers={"apikey": KEY, "Authorization": "Bearer " + KEY,
                                                  "Prefer": "count=exact"}, method="HEAD")
            try:
                cr = urllib.request.urlopen(req, timeout=60).headers.get("Content-Range", "*/0")
                n = int(cr.split("/")[-1])
            except Exception:
                n = 0
            if n > 0:
                days.append(ds)
            probe_day -= datetime.timedelta(days=1)
        days = sorted(days)
        print(f"{D}: baseline days = {days}", file=sys.stderr)
        base = trailing_baselines(days)

        agg = day_topchains(D)
        flow = flow_scores_for(D)
        ivm = iv_latest()
        earn = earnings_map()

        feats: dict[str, dict] = {}
        for t, a in agg.items():
            b = base.get(t)
            vol_mean = b["vol_mean"] if b and b["n_days"] >= 3 else None
            prem_mean = b["prem_mean"] if b and b["n_days"] >= 3 else None
            f = {
                "premium": a["premium"],
                "volume": a["volume"],
                "contracts": a["contracts"],
                "n_strikes": a["n_strikes"],
                "oi": a["oi"],
                "oi_change": a["oi"] - a["prev_oi"],
                "oi_change_pct": (a["oi"] - a["prev_oi"]) / a["prev_oi"] * 100.0 if a["prev_oi"] else None,
                "vol_oi": a["volume"] / a["oi"] if a["oi"] else None,
                "ask_share": a["ask_volume"] / (a["ask_volume"] + a["bid_volume"]) if (a["ask_volume"] + a["bid_volume"]) else None,
                "prem_pct_vs_base": (a["premium"] / prem_mean) if prem_mean else None,
                "rvol": (a["volume"] / vol_mean) if vol_mean else None,
                "baseline_days": b["n_days"] if b else 0,
                "iv_atm": ivm.get(t),
            }
            e = earn.get(t)
            if e and e.get("report_date"):
                try:
                    f["days_to_earnings"] = (datetime.date.fromisoformat(e["report_date"]) -
                                             datetime.date.fromisoformat(D)).days
                except ValueError:
                    f["days_to_earnings"] = None
                f["market_cap_size"] = e.get("market_cap_size")
                f["sector"] = e.get("sector")
            else:
                f["days_to_earnings"] = None
            fs = flow.get(t)
            if fs:
                f["flow_score_mean"] = fs["flow_score_mean"]
                f["flow_bonus_mean"] = fs["flow_bonus_mean"]
                f["sweep_share"] = fs["sweep_share"]
            feats[t] = f

        # score v0 = mean of available cross-sectional percentiles
        keys = ["premium", "volume", "vol_oi", "oi_change_pct", "ask_share",
                "prem_pct_vs_base", "rvol", "n_strikes"]
        pct_maps = {}
        for k in keys:
            vals = {t: f[k] for t, f in feats.items() if f.get(k) is not None}
            pct_maps[k] = pct_rank(vals)
        for t, f in feats.items():
            ps = [pct_maps[k][t] for k in keys if t in pct_maps[k]]
            f["score_v0"] = sum(ps) / len(ps) if ps else None
            f["score_v0_n_feats"] = len(ps)

        ranked = sorted(feats.items(), key=lambda kv: -(kv[1]["score_v0"] or -1))
        out = {
            "date": D,
            "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": "UW PHX Supabase (top_chains, flow_scores, iv_history, uw_earnings_upcoming)",
            "baseline_days": days,
            "n_tickers": len(feats),
            "score_v0_definition": "mean of per-feature cross-sectional percentiles over "
                                   "[premium, volume, vol_oi, oi_change_pct, ask_share, "
                                   "prem_pct_vs_base, rvol, n_strikes]; equal weights, unfitted",
            "ranked": [{"ticker": t, **f} for t, f in ranked],
        }
        fn = os.path.join(OUT_DIR, f"uw_features_{D}.json")
        with open(fn, "w") as f:
            json.dump(out, f, indent=1)
        print(f"wrote {fn} ({len(feats)} tickers)")


if __name__ == "__main__":
    main()
