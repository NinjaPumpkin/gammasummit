#!/usr/bin/env python3
"""E0.8 — H1/H2 backtest vs Skylit unusual sets (clean-room, UW + leandata only).

Hypotheses (docs/build/skylit-ticker-selection-model.md §6):
  H1  contract-level RVOL (min_rvol=2 vs 10d baseline, min_avg_volume=100) +
      OI-change (>=500 or >=25%) recovers Skylit unusual sets at P@50 >= 0.5
  H2  premium percentile vs own trailing 20d ranks "surprising" names above
      raw premium within the same day (vs truth B per day)

Tracks (honest capability envelope — every metric carries its sample sizes):
  T1  leandata options_eod (SPY/QQQ; rich uncensored SPY window 2021-11..2022-11)
      -> H1-RVOL + H2 MECHANICS only. Skylit daily rollups return 0 rows for
         2022 (probed 2022-03-15: all 7 endpoints empty), so no P/R here.
  T2  leandata options_minute (54 liquid tickers, 2026-09-15..25) -> per-contract
      daily aggregates -> H1-RVOL (no OI in source) + H2 at ticker level vs
      Skylit unusual sets pulled per day. Pred universe = 54 covered tickers.
  T3  UW PHX top_chains (replay days 2026-09-29/30, 10-01; ~610-ticker capture)
      -> H1 full (RVOL censored by top-15 truncation + OI-change from oi/prev_oi,
      which IS uncensored per row) + H2, contract- and ticker-level vs B.
      This is the track where the "P@50 >= 0.5" target is actually measurable.

Ground truth: data/e07/skylit_api/<date>_{unusual_volume,unusual_oi,top_tickers_premium}.json
(Flowseeker API daily rollups; captured by scripts/e07_skylit_observed_pull.py).
Never claims Skylit internals — only reproduces its published lists.

Usage:
  python3 scripts/e08_h1h2_backtest.py                     # all tracks
  python3 scripts/e08_h1h2_backtest.py --tracks T2 T3
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import statistics
import sys
import time
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
E07 = os.path.join(ROOT, "data", "e07")
SK = os.path.join(E07, "skylit_api")
E08 = os.path.join(ROOT, "data", "e08")
LED = os.path.join(E08, "leandata_contract_daily.parquet")

# Product defaults captured in model doc §4 [academy]
MIN_RVOL = 2.0
AVG_PERIOD = 10
MIN_AVG_VOLUME = 100.0
MIN_OI_CHANGE = 500.0
MIN_OI_CHANGE_PCT = 25.0
SURPRISE_PCT = 0.90          # H2 "surprising" bar: top decile vs own trailing 20d
MIN_BASE_OBS_STRICT = 10
MIN_BASE_OBS_LOOSE = 5       # T2 window only has ~9 sessions; documented deviation


# ---------- helpers ----------

def load(fn):
    with open(fn) as f:
        return json.load(f)


def norm_occ(sym: str) -> str:
    """Skylit 'SPY__261001C00761000' / 'SPY 260928C00768000' -> bare OCC."""
    return sym.replace("_", "").replace(" ", "").upper()


def pr_at_k(pred: list[str], truth: set[str], k: int) -> dict:
    top = pred[:k]
    hits = [t for t in top if t in truth]
    return {"k": k, "n_pred": len(top), "n_truth": len(truth), "hits": len(hits),
            "precision": len(hits) / len(top) if top else None,
            "recall": len(hits) / len(truth) if truth else None,
            "hit_tickers": hits}


def contract_pr(pred: set[str], truth: set[str]) -> dict:
    hits = pred & truth
    return {"n_pred": len(pred), "n_truth": len(truth), "hits": len(hits),
            "precision": len(hits) / len(pred) if pred else None,
            "recall": len(hits) / len(truth) if truth else None}


def pctile_rank_of_own_history(value: float, history: list[float]) -> float:
    """Fraction of own trailing values strictly below `value` (inclusive ties=0.5)."""
    if not history:
        return float("nan")
    below = sum(1 for h in history if h < value)
    ties = sum(1 for h in history if h == value)
    return (below + 0.5 * ties) / len(history)


class ContractHist:
    """Per-contract rolling daily history -> H1/H2 flags for one contract-day."""

    def __init__(self):
        self.days: dict[str, dict[str, list]] = defaultdict(lambda: {"occ": []})

    @staticmethod
    def flags(rows: list[dict], date: str, min_base_obs: int, with_oi: bool) -> dict:
        """rows: chronological contract-day dicts {date, volume, premium, oi, prev_oi}.
        Flags for the LAST row (== date)."""
        cur = rows[-1]
        hist = rows[:-1]
        base = [r["volume"] for r in hist[-AVG_PERIOD:]]
        out = {"date": date, "occ": cur.get("occ"), "volume": cur["volume"],
               "premium": cur["premium"]}
        avg = statistics.fmean(base) if base else 0.0
        out["base_obs"] = len(base)
        out["base_avg_volume"] = avg
        out["rvol"] = (cur["volume"] / avg) if avg > 0 else (float("inf") if cur["volume"] > 0 else 0.0)
        out["flag_rvol"] = bool(len(base) >= min_base_obs and avg >= MIN_AVG_VOLUME
                                and out["rvol"] >= MIN_RVOL)
        prem_hist = [r["premium"] for r in hist[-20:]]
        out["prem_pctile_20d"] = pctile_rank_of_own_history(cur["premium"], prem_hist)
        out["flag_h2"] = bool(len(prem_hist) >= min_base_obs
                              and out["prem_pctile_20d"] >= SURPRISE_PCT)
        if with_oi:
            oi, prev = cur.get("oi"), cur.get("prev_oi")
            if oi is not None and prev is not None:
                d = float(oi) - float(prev)
                pct = (abs(d) / float(prev) * 100.0) if prev else (float("inf") if d else 0.0)
                out["oi_change"] = d
                out["oi_change_pct"] = pct
                out["flag_oi"] = bool(abs(d) >= MIN_OI_CHANGE or pct >= MIN_OI_CHANGE_PCT)
            else:
                out["flag_oi"] = False
        return out


def per_contract_flags(day_rows: list[dict], dates_sorted: list[str], date: str,
                       min_base_obs: int, with_oi: bool) -> list[dict]:
    """day_rows: flat contract-day rows. Computes flags for all contracts on `date`."""
    by_occ: dict[str, list[dict]] = defaultdict(list)
    for r in day_rows:
        by_occ[r["occ"]].append(r)
    out = []
    for occ, rs in by_occ.items():
        rs.sort(key=lambda r: r["date"])
        rs = [r for r in rs if r["date"] <= date]
        if not rs or rs[-1]["date"] != date:
            continue
        out.append(ContractHist.flags(rs, date, min_base_obs, with_oi))
    return out


# ---------- ground truth ----------

def truth_for(date: str) -> dict:
    uv, uo = [], []
    fu = os.path.join(SK, f"{date}_unusual_volume.json")
    fo = os.path.join(SK, f"{date}_unusual_oi.json")
    if os.path.isfile(fu):
        uv = load(fu).get("data", [])
    if os.path.isfile(fo):
        uo = load(fo).get("data", [])
    vol_t = {r["ticker"] for r in uv}
    oi_t = {r["ticker"] for r in uo}
    return {
        "vol_tickers": vol_t, "oi_tickers": oi_t, "b_tickers": vol_t | oi_t,
        "vol_contracts": {norm_occ(r["symbol"]) for r in uv if r.get("symbol")},
        "oi_contracts": {norm_occ(r["symbol"]) for r in uo if r.get("symbol")},
        "vol_rows": {norm_occ(r["symbol"]): r for r in uv if r.get("symbol")},
        "oi_rows": {norm_occ(r["symbol"]): r for r in uo if r.get("symbol")},
        "n_vol_rows": len(uv), "n_oi_rows": len(uo),
    }


# ---------- T1: leandata eod mechanics ----------

def run_t1() -> dict:
    import pyarrow.parquet as pq
    df = pq.read_table(LED, columns=["source", "occ", "date", "volume", "premium"]).to_pandas()
    df = df[df["source"] == "eod"]
    rows = df.to_dict("records")
    by_occ: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_occ[r["occ"]].append(r)
    n_eligible = n_flagged = n_days = 0
    rvol_vals, prem_pcts = [], []
    examples = []
    for occ, rs in by_occ.items():
        rs.sort(key=lambda r: r["date"])
        if len(rs) < MIN_BASE_OBS_STRICT + 1:
            continue
        n_eligible += 1
        for i in range(MIN_BASE_OBS_STRICT, len(rs)):
            f = ContractHist.flags(rs[: i + 1], rs[i]["date"], MIN_BASE_OBS_STRICT, with_oi=False)
            n_days += 1
            rvol_vals.append(f["rvol"])
            if f["prem_pctile_20d"] == f["prem_pctile_20d"]:
                prem_pcts.append(f["prem_pctile_20d"])
            if f["flag_rvol"]:
                n_flagged += 1
                if len(examples) < 10:
                    examples.append({"occ": occ, **{k: f[k] for k in
                                     ("date", "volume", "base_avg_volume", "rvol", "premium")}})
    return {
        "track": "T1 leandata options_eod (mechanics only, no truth in window)",
        "window": "SPY/QQQ; rich uncensored SPY 2021-11-22..2022-11-02",
        "n_contract_day_rows": len(rows),
        "n_contracts_total": len(by_occ),
        "n_contracts_eligible_ge11d": n_eligible,
        "n_contract_days_scored": n_days,
        "flag_rvol_rate": (n_flagged / n_days) if n_days else None,
        "rvol_median": statistics.median(rvol_vals) if rvol_vals else None,
        "rvol_p90": sorted(rvol_vals)[int(len(rvol_vals) * 0.9)] if rvol_vals else None,
        "h2_prem_pctile_uniform_check_mean": (statistics.fmean(prem_pcts) if prem_pcts else None),
        "examples_flag_rvol": examples,
        "truth": "NONE — Skylit rollups empty for 2022 (2022-03-15 probe: 7/7 endpoints 0 rows); "
                 "H1 P/R not measurable on this track; OI half of H1 untestable (no OI in options_eod)",
    }


# ---------- T2: leandata minute, 54 tickers ----------

def run_t2() -> dict:
    import pyarrow.parquet as pq
    df = pq.read_table(LED, columns=["source", "ticker", "occ", "date", "volume", "premium"]).to_pandas()
    df = df[df["source"] == "minute"]
    rows = df.to_dict("records")
    by_occ: dict[str, list[dict]] = defaultdict(list)
    tick_days: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        by_occ[r["occ"]].append(r)
        tick_days[r["ticker"]][r["date"]] += float(r["premium"])
    dates = sorted({r["date"] for r in rows})
    universe = sorted(tick_days)
    out = {"track": "T2 leandata options_minute (54-ticker covered universe)",
           "dates": dates, "n_universe": len(universe),
           "k_caveat": "K=50 approaches the 54-ticker universe size -> P@50 ~= truth prevalence "
                       "in-universe, NOT discriminative; read @10/@25 as the real signal",
           "baseline_deviation": f"RVOL baseline = up-to-10 prior obs, min {MIN_BASE_OBS_LOOSE} "
                                 f"(window has only {len(dates)} sessions; strict-10 reported separately)",
           "per_day": {}}
    strict_flag_days = 0
    for D in dates:
        t = truth_for(D)
        if not t["n_vol_rows"] and not t["n_oi_rows"]:
            out["per_day"][D] = {"truth": "no skylit rows pulled"}
            continue
        flags = per_contract_flags(rows, dates, D, MIN_BASE_OBS_LOOSE, with_oi=False)
        strict = per_contract_flags(rows, dates, D, MIN_BASE_OBS_STRICT, with_oi=False)
        strict_flag_days += sum(1 for f in strict if f["flag_rvol"])
        # ticker-level ranks
        rvol_s: dict[str, float] = defaultdict(float)
        h2_s: dict[str, float] = defaultdict(float)
        prem: dict[str, float] = defaultdict(float)
        nflag: dict[str, int] = defaultdict(int)
        occ2tk = {r["occ"]: r["ticker"] for r in rows}
        for f in flags:
            tk = occ2tk.get(f["occ"])
            if tk is None:
                continue
            prem[tk] += f["premium"]
            if f["rvol"] == f["rvol"] and f["rvol"] != float("inf"):
                rvol_s[tk] = max(rvol_s[tk], f["rvol"])
            if f["flag_rvol"]:
                nflag[tk] += 1
            if f["prem_pctile_20d"] == f["prem_pctile_20d"]:
                h2_s[tk] = max(h2_s[tk], f["prem_pctile_20d"])
        # ticker-level H2 surprise: premium vs own trailing days in-window
        h2_tick: dict[str, float] = {}
        for tk, series in tick_days.items():
            hist = [series[d] for d in dates if d < D and d in series]
            if len(hist) >= MIN_BASE_OBS_LOOSE:
                h2_tick[tk] = pctile_rank_of_own_history(series.get(D, 0.0), hist[-20:])
        # rank only tickers with >=1 scored contract; ties -> premium desc, then name.
        # (filling the tail with unscored tickers produced alphabetical artifacts)
        ranked_uni = sorted(prem, key=lambda t_: (-nflag[t_], -rvol_s.get(t_, 0.0),
                                                  -prem.get(t_, 0.0), t_))
        rank_rvol = ranked_uni
        rank_h1 = rank_rvol
        rank_h2c = sorted(prem, key=lambda t_: (-h2_s.get(t_, -1.0), -prem.get(t_, 0.0), t_))
        rank_h2t = sorted(prem, key=lambda t_: (-h2_tick.get(t_, -1.0), -prem.get(t_, 0.0), t_))
        rank_prem = sorted(prem, key=lambda t_: (-prem.get(t_, 0.0), t_))
        B = t["b_tickers"]
        cov = B & set(universe)
        out["per_day"][D] = {
            "truth_n_rows": {"unusual_volume": t["n_vol_rows"], "unusual_oi": t["n_oi_rows"]},
            "truth_n_tickers": {"B": len(B), "B_in_universe": len(cov)},
            "n_contracts_scored": len(flags),
            "n_tickers_ranked": len(ranked_uni),
            "n_flag_rvol": sum(1 for f in flags if f["flag_rvol"]),
            "n_flag_h2_contract": sum(1 for f in flags if f["flag_h2"]),
            "vs_B_all": {f"{name}@{k}": pr_at_k(rk, B, k)
                         for name, rk in (("h1_rvol", rank_h1), ("h2_contract", rank_h2c),
                                          ("h2_ticker", rank_h2t), ("premium_raw", rank_prem))
                         for k in (10, 25, 50)},
            "vs_B_in_universe": {f"{name}@{k}": pr_at_k(rk, cov, k)
                                 for name, rk in (("h1_rvol", rank_h1), ("h2_ticker", rank_h2t),
                                                  ("premium_raw", rank_prem))
                                 for k in (10, 25)},
        }
    out["strict10_flag_contract_days"] = strict_flag_days
    return out


# ---------- T3: UW top_chains, replay days ----------

def uw_env():
    env = {}
    for p in (os.path.join(ROOT, ".env"), "/Users/admin/Desktop/Github Projects/SignalForge/.env"):
        if not os.path.isfile(p):
            continue
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def topchains_day(day: str, env: dict) -> list[dict]:
    """Per-contract rows for one trade date (both sorts, dedup by option_symbol)."""
    cache = os.path.join(E08, f"topchains_{day}.json")
    if os.path.isfile(cache):
        return json.load(open(cache))
    url = (env.get("GAMMASUMMIT_UW_URL") or env.get("SUPABASE_URL") or "").rstrip("/") + "/rest/v1/"
    key = env.get("GAMMASUMMIT_UW_SERVICE_KEY") or env.get("SUPABASE_SERVICE_KEY") or ""

    def get(params):
        req = urllib.request.Request(url + "top_chains?" + params,
                                     headers={"apikey": key, "Authorization": "Bearer " + key})
        return json.loads(urllib.request.urlopen(req, timeout=120).read())

    out, off = [], 0
    while True:
        batch = get("select=option_symbol,ticker,volume,avg_price,open_interest,prev_oi,"
                    "ask_volume,bid_volume,mid_volume,strike,expiry,side,trade_date"
                    f"&trade_date=eq.{day}&limit=1000&offset={off}")
        out += batch
        if len(batch) < 1000:
            break
        off += 1000
        time.sleep(0.05)
    seen: dict[str, dict] = {}
    for r in out:
        sym = r.get("option_symbol") or f"{r['ticker']}|{r.get('strike')}|{r.get('expiry')}"
        prev = seen.get(sym)
        if prev is None or (r.get("volume") or 0) > (prev.get("volume") or 0):
            seen[sym] = r
    rows = list(seen.values())
    with open(cache, "w") as f:
        json.dump(rows, f)
    return rows


def run_t3(replay_dates: list[str]) -> dict:
    env = uw_env()
    out = {"track": "T3 UW PHX top_chains vs Skylit unusual sets (headline H1 test)",
           "censoring_note": "top_chains keeps top-15 contracts/ticker/day (2 sorts): contract "
                             "volume history is censored (absence != zero) so RVOL baselines are "
                             "conditional on top-15 presence; oi/prev_oi per row are uncensored",
           "per_day": {}}
    for D in replay_dates:
        d = datetime.date.fromisoformat(D)
        baseline_days = []
        probe = d - datetime.timedelta(days=1)
        floor = d - datetime.timedelta(days=45)
        while probe >= floor and len(baseline_days) < 25:
            ds = probe.isoformat()
            try:
                rows = topchains_day(ds, env)
                if rows:
                    baseline_days.append(ds)
            except Exception as e:  # noqa: BLE001
                print(f"  baseline {ds}: {e}", file=sys.stderr)
            probe -= datetime.timedelta(days=1)
        all_rows: list[dict] = []
        for ds in baseline_days + [D]:
            all_rows += topchains_day(ds, env)
        for r in all_rows:
            r["date"] = r["trade_date"]
            r["occ"] = norm_occ(r.get("option_symbol") or "")
            r["volume"] = float(r.get("volume") or 0)
            r["premium"] = float(r.get("avg_price") or 0) * float(r.get("volume") or 0) * 100.0
            r["oi"] = float(r.get("open_interest") or 0)
            r["prev_oi"] = float(r.get("prev_oi") or 0)
        flags = per_contract_flags(all_rows, baseline_days + [D], D, MIN_BASE_OBS_LOOSE, with_oi=True)
        t = truth_for(D)
        occ2tk = {r["occ"]: r["ticker"] for r in all_rows if r["date"] == D}
        rvol_s: dict[str, float] = defaultdict(float)
        oi_s: dict[str, float] = defaultdict(float)
        h2_s: dict[str, float] = defaultdict(float)
        prem: dict[str, float] = defaultdict(float)
        nflag: dict[str, int] = defaultdict(int)
        noiflag: dict[str, int] = defaultdict(int)
        for f in flags:
            tk = occ2tk.get(f["occ"])
            if tk is None:
                continue
            prem[tk] += f["premium"]
            if f["rvol"] == f["rvol"] and f["rvol"] != float("inf"):
                rvol_s[tk] = max(rvol_s[tk], f["rvol"])
            if f["flag_rvol"]:
                nflag[tk] += 1
            if f.get("flag_oi"):
                noiflag[tk] += 1
                oi_s[tk] = max(oi_s[tk], abs(f.get("oi_change", 0.0)))
            if f["prem_pctile_20d"] == f["prem_pctile_20d"]:
                h2_s[tk] = max(h2_s[tk], f["prem_pctile_20d"])
        uni = sorted(set(occ2tk.values()))
        rank_h1vol = sorted(uni, key=lambda t_: (-nflag[t_], -rvol_s.get(t_, 0.0), -prem.get(t_, 0.0), t_))
        rank_h1oi = sorted(uni, key=lambda t_: (-noiflag[t_], -oi_s.get(t_, 0.0), -prem.get(t_, 0.0), t_))
        rank_h1 = sorted(set(rank_h1vol) | set(rank_h1oi),
                         key=lambda t_: (-(nflag[t_] + noiflag[t_]),
                                         -(rvol_s.get(t_, 0.0) + oi_s.get(t_, 0.0)),
                                         -prem.get(t_, 0.0), t_))
        rank_h2 = sorted(uni, key=lambda t_: (-h2_s.get(t_, -1.0), -prem.get(t_, 0.0), t_))
        rank_prem = sorted(uni, key=lambda t_: (-prem.get(t_, 0.0), t_))
        B = t["b_tickers"]
        pred_contracts = {f["occ"] for f in flags if f["flag_rvol"] or f.get("flag_oi")}
        truth_contracts = t["vol_contracts"] | t["oi_contracts"]
        # censoring diagnostic: what did we compute for the truth contracts that ARE
        # captured in top_chains, vs Skylit's own published rvol/oiChange for them?
        f_by_occ = {f["occ"]: f for f in flags}
        diag = []
        for occ in sorted(truth_contracts & set(occ2tk)):
            f = f_by_occ.get(occ, {})
            sv = t["vol_rows"].get(occ, {})
            so = t["oi_rows"].get(occ, {})
            diag.append({
                "occ": occ,
                "skylit_rvol": sv.get("rvol"), "our_rvol": f.get("rvol"),
                "our_flag_rvol": f.get("flag_rvol"), "our_base_obs": f.get("base_obs"),
                "skylit_oi_change": so.get("oiChange"), "our_oi_change": f.get("oi_change"),
                "our_flag_oi": f.get("flag_oi"),
            })
        out["per_day"][D] = {
            "n_baseline_days": len(baseline_days),
            "n_contract_rows_day": len(occ2tk),
            "n_tickers_day": len(uni),
            "n_contracts_scored": len(flags),
            "n_flag_rvol": sum(1 for f in flags if f["flag_rvol"]),
            "n_flag_oi": sum(1 for f in flags if f.get("flag_oi")),
            "truth_n_rows": {"unusual_volume": t["n_vol_rows"], "unusual_oi": t["n_oi_rows"]},
            "truth_n_tickers": {"B": len(B), "B_captured_in_topchains": len(B & set(uni))},
            "ticker_level_vs_B": {
                "h1_union": [pr_at_k(rank_h1, B, k) for k in (25, 50)],
                "h1_rvol_vs_Bvol": [pr_at_k(rank_h1vol, t["vol_tickers"], k) for k in (25, 50)],
                "h1_oi_vs_Boi": [pr_at_k(rank_h1oi, t["oi_tickers"], k) for k in (25, 50)],
                "h2_surprise_vs_B": [pr_at_k(rank_h2, B, k) for k in (25, 50)],
                "premium_raw_vs_B": [pr_at_k(rank_prem, B, k) for k in (25, 50)],
            },
            "contract_level": {
                "h1_flags_vs_unusual_contracts": contract_pr(pred_contracts, truth_contracts),
                "rvol_flags_vs_unusual_volume_contracts":
                    contract_pr({f["occ"] for f in flags if f["flag_rvol"]}, t["vol_contracts"]),
                "oi_flags_vs_unusual_oi_contracts":
                    contract_pr({f["occ"] for f in flags if f.get("flag_oi")}, t["oi_contracts"]),
                "captured_truth_contracts": len(truth_contracts & set(occ2tk)),
                "captured_truth_diag": diag,
            },
        }
    return out


def render_md(rep: dict) -> str:
    md = ["# E0.8 — H1/H2 backtest report (clean-room)", "",
          f"Generated: {rep['generated_utc']}",
          "Hypotheses: docs/build/skylit-ticker-selection-model.md §6 (H1, H2).",
          "Ground truth: Skylit Flowseeker daily rollup lists ONLY (unusual_volume / unusual_oi).",
          "Sample sizes reported everywhere; no Skylit internals claimed.", ""]
    for tr in rep["tracks"].values():
        md.append(f"## {tr['track']}")
        for k, v in tr.items():
            if k in ("track", "per_day"):
                continue
            md.append(f"- {k}: {json.dumps(v) if isinstance(v, (dict, list)) else v}")
        for D, day in tr.get("per_day", {}).items():
            md.append(f"### {D}")
            for k, v in day.items():
                if k == "vs_B_all":
                    md.append("  - vs B (all truth tickers):")
                    for kk, vv in v.items():
                        if vv["precision"] is not None:
                            md.append(f"    - {kk}: P={vv['precision']:.2f} R={vv['recall']:.2f} "
                                      f"hits={vv['hits']} pred={vv['n_pred']} truth={vv['n_truth']}")
                    continue
                if k in ("vs_B_in_universe", "ticker_level_vs_B"):
                    md.append(f"  - {k}:")
                    if isinstance(v, dict):
                        for kk, vv in v.items():
                            for row in ([vv] if isinstance(vv, dict) else vv):
                                if row.get("precision") is not None:
                                    md.append(f"    - {kk}@{row['k']}: P={row['precision']:.2f} "
                                              f"R={row['recall']:.2f} hits={row['hits']} "
                                              f"pred={row['n_pred']} truth={row['n_truth']}")
                    else:
                        for row in v:
                            if row.get("precision") is not None:
                                md.append(f"    - @{row['k']}: P={row['precision']:.2f} "
                                          f"R={row['recall']:.2f} hits={row['hits']} "
                                          f"pred={row['n_pred']} truth={row['n_truth']}")
                    continue
                if k == "contract_level":
                    md.append("  - contract level:")
                    for kk, vv in v.items():
                        if isinstance(vv, dict):
                            p = f"P={vv['precision']:.3f}" if vv["precision"] is not None else "P=n/a"
                            r = f"R={vv['recall']:.3f}" if vv["recall"] is not None else "R=n/a"
                            md.append(f"    - {kk}: {p} {r} hits={vv['hits']} "
                                      f"pred={vv['n_pred']} truth={vv['n_truth']}")
                        else:
                            md.append(f"    - {kk}: {vv}")
                    continue
                md.append(f"  - {k}: {json.dumps(v) if isinstance(v, (dict, list)) else v}")
        md.append("")
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracks", nargs="+", default=["T1", "T2", "T3"],
                    choices=["T1", "T2", "T3"])
    ap.add_argument("--t3-dates", nargs="+", default=["2026-09-29", "2026-09-30", "2026-10-01"])
    args = ap.parse_args()
    os.makedirs(E08, exist_ok=True)

    rep = {"generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "spec": {"min_rvol": MIN_RVOL, "avg_period": AVG_PERIOD,
                    "min_avg_volume": MIN_AVG_VOLUME, "min_oi_change": MIN_OI_CHANGE,
                    "min_oi_change_pct": MIN_OI_CHANGE_PCT, "h2_surprise_pctile": SURPRISE_PCT},
           "tracks": {}}
    if "T1" in args.tracks:
        rep["tracks"]["T1"] = run_t1()
    if "T2" in args.tracks:
        rep["tracks"]["T2"] = run_t2()
    if "T3" in args.tracks:
        rep["tracks"]["T3"] = run_t3(args.t3_dates)

    fn = os.path.join(E08, "h1h2_backtest_report.json")
    with open(fn, "w") as f:
        json.dump(rep, f, indent=1, default=str)
    md = render_md(rep)
    fn_md = os.path.join(E08, "h1h2_backtest_report.md")
    with open(fn_md, "w") as f:
        f.write(md)
    print(md)
    print(f"\nwrote {fn} + {fn_md}")


if __name__ == "__main__":
    main()
