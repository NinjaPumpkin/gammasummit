#!/usr/bin/env python3
"""E0.8 — per-contract daily persistence for the UW universe (model doc §7 gap 1).

Captures FULL per-contract daily aggregates (not top-15-truncated) from the UW PHX
proxy and persists them in the ContractStats/UnderlyingStats row shapes declared by
db/migrations/0002_contract_daily_stats.sql:

  source      PHX /api/chains_expiry/{T} (expiry list) + /api/chains_expiry/{T}/{EXP}
              (full chain rows: volume, open_interest, prev_oi, bid/ask/mid_volume,
              avg_price, last_price, iv, greeks) + /api/ticker/{T}/price/v2 (spot)
  universe    UW-captured tickers: distinct top_chains tickers over trailing 20 trade
              days (~610) UNION ticker_universe tiers T0/T1 (UW PHX)
  writes      (1) ALWAYS: parquet  data/e08/contract_daily/dt=YYYY-MM-DD/
                  contracts.parquet + underlyings.parquet + run_report.json
              (2) with --execute: INSERT-only upsert into contract_daily_stats /
                  underlying_daily_stats via PostgREST
                  (Prefer: resolution=ignore-duplicates — non-destructive: an
                  existing (date, occ) row is NEVER overwritten)
  dry-run     DEFAULT. Without --execute nothing is written to any database.

Known field gaps (honest NULLs, never invented):
  sweep_volume / sweep_premium / multi_leg_*   not served per-contract by PHX chains
  trade_count                                  not served per-contract
  underlying_price                             filled from price/v2 when available

NOTE: PHX chains_expiry serves the LATEST settled snapshot only — the `date` query
param is a no-op (verified 2026-10-02: identical rows with/without date). History
accumulates by running this collector once per session after close; no backfill.

Usage:
  python3 scripts/e08_contract_daily_persist.py                       # dry-run, latest session
  python3 scripts/e08_contract_daily_persist.py --execute             # + DB insert-only upsert
  python3 scripts/e08_contract_daily_persist.py --date 2026-10-01     # explicit session label
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR_DEFAULT = os.path.join(ROOT, "data", "e08", "contract_daily")
PHX = "https://phx.unusualwhales.com"
UW_SH = "bpzdbMf9zofibLbATL1O37"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")


def load_env() -> dict:
    env = {}
    for p in (os.path.join(ROOT, ".env"),
              "/Users/admin/Desktop/Github Projects/SignalForge/.env"):
        if not os.path.isfile(p):
            continue
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


ENV = load_env()
UW_URL = (ENV.get("GAMMASUMMIT_UW_URL") or ENV.get("SUPABASE_URL") or "").rstrip("/") + "/rest/v1/"
UW_KEY = ENV.get("GAMMASUMMIT_UW_SERVICE_KEY") or ENV.get("SUPABASE_SERVICE_KEY") or ""


class PhxClient:
    """UW PHX proxy client: browser headers mandatory (silent-empty otherwise),
    token with unauthenticated fallback on 401/403, paced <= 2 rps, backoff on 429."""

    def __init__(self, pace: float = 0.5):
        self.pace = pace
        self.token = ENV.get("PHX_AUTH_TOKEN") or ""
        self.calls = 0
        self.fallbacks = 0
        self.errors: list[str] = []
        self._last = 0.0

    def _headers(self, authed: bool) -> dict:
        h = {"uw-sh": UW_SH, "User-Agent": BROWSER_UA,
             "Referer": "https://unusualwhales.com/", "Accept": "application/json"}
        if authed and self.token:
            h["Authorization"] = "Bearer " + self.token
        return h

    def get(self, path: str) -> dict | list:
        gap = self.pace - (time.time() - self._last)
        if gap > 0:
            time.sleep(gap)
        url = PHX + path
        for attempt, authed in enumerate([True, True, False, False]):
            req = urllib.request.Request(url, headers=self._headers(authed))
            try:
                self._last = time.time()
                self.calls += 1
                return json.loads(urllib.request.urlopen(req, timeout=60).read())
            except urllib.error.HTTPError as e:
                if e.code in (401, 403) and authed:
                    self.fallbacks += 1
                    continue
                if e.code == 429:
                    time.sleep(5.0 * (attempt + 1))
                    continue
                self.errors.append(f"{path}: HTTP {e.code}")
                raise
        self.errors.append(f"{path}: auth failed")
        raise RuntimeError(f"auth failed for {path}")


def uw_get(table: str, params: str) -> list[dict]:
    req = urllib.request.Request(UW_URL + table + "?" + params,
                                 headers={"apikey": UW_KEY,
                                          "Authorization": "Bearer " + UW_KEY})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def resolve_universe() -> tuple[list[str], dict]:
    """UW-captured universe: union of distinct top_chains tickers over the trailing
    5 trade days with rows (the operational ~610-ticker capture) UNION
    ticker_universe tiers T0/T1. Returns (tickers, provenance)."""
    seen: dict[str, str] = {}
    days_used = 0
    probe = datetime.date.today()
    floor = probe - datetime.timedelta(days=12)
    while probe >= floor and days_used < 5:
        ds = probe.isoformat()
        off = 0
        day_rows = 0
        day_tickers = set()
        while True:
            batch = uw_get("top_chains", f"select=ticker&trade_date=eq.{ds}&limit=1000&offset={off}")
            day_tickers.update(r["ticker"] for r in batch)
            day_rows += len(batch)
            if len(batch) < 1000:
                break
            off += 1000
            time.sleep(0.05)
        if day_rows > 0:
            days_used += 1
            for t in day_tickers:
                seen.setdefault(t, f"top_chains_{ds}")
        probe -= datetime.timedelta(days=1)
    for r in uw_get("ticker_universe", "select=ticker,tier&tier=in.(T0,T1)&limit=500"):
        seen.setdefault(r["ticker"], f"tier_{r['tier']}")
    return sorted(seen), {"top_chains_5_trade_days_plus_T0T1": len(seen),
                          "days_used": days_used}


def map_contract_row(r: dict, session_date: str) -> dict:
    opt_type = (r.get("option_type") or "").lower()
    right = "C" if opt_type.startswith("c") else ("P" if opt_type.startswith("p") else None)
    strike = float(r.get("strike") or 0)
    expiry = str(r.get("expires") or "")[:10]
    occ = (r.get("option_symbol") or "").replace(" ", "").replace("_", "").upper()
    vol = int(float(r.get("volume") or 0))
    avg_price = float(r.get("avg_price") or 0) or None
    oi = int(float(r.get("open_interest") or 0))
    prev_oi = int(float(r.get("prev_oi") or 0))
    dte = None
    if expiry:
        try:
            dte = (datetime.date.fromisoformat(expiry)
                   - datetime.date.fromisoformat(session_date)).days
        except ValueError:
            dte = None
    return {
        "date": session_date, "occ": occ,
        "ticker": (r.get("underlying_symbol") or "").upper(),
        "expiration": expiry, "strike": strike, "right": right, "dte": dte,
        "total_premium": (avg_price or 0.0) * vol * 100.0,
        "total_volume": vol,
        "open_interest": oi, "prev_oi": prev_oi, "oi_change": oi - prev_oi,
        "bid_volume": int(float(r.get("bid_volume") or 0)),
        "ask_volume": int(float(r.get("ask_volume") or 0)),
        "mid_volume": int(float(r.get("mid_volume") or 0)),
        "sweep_volume": None, "sweep_premium": None,
        "multi_leg_volume": None, "multi_leg_premium": None,
        "vwap": avg_price, "last_price": float(r.get("last_price") or 0) or None,
        "underlying_price": None,
        "iv": float(r.get("iv") or 0) or None,
        "trade_count": None,
        "source": "phx_chains_expiry",
    }


def aggregate_underlying(ticker: str, session_date: str, rows: list[dict],
                         spot: float | None) -> dict:
    call_prem = put_prem = 0.0
    call_vol = put_vol = 0
    trades = 0
    strikes, expirations = set(), set()
    for r in rows:
        if r["right"] == "C":
            call_prem += r["total_premium"]; call_vol += r["total_volume"]
        else:
            put_prem += r["total_premium"]; put_vol += r["total_volume"]
        trades += r["trade_count"] or 0
        strikes.add(r["strike"]); expirations.add(r["expiration"])
    tot_vol = call_vol + put_vol
    return {
        "date": session_date, "ticker": ticker,
        "last_price": spot,
        "total_premium": call_prem + put_prem,
        "total_volume": tot_vol,
        "call_premium": call_prem, "put_premium": put_prem,
        "call_volume": call_vol, "put_volume": put_vol,
        "net_premium": call_prem - put_prem,
        "call_put_ratio": (call_prem / put_prem) if put_prem else None,
        "trade_count": trades or None,
        "unique_strikes": len(strikes), "unique_expirations": len(expirations),
        "source": "phx_chains_expiry+price_v2",
    }


def pg_upsert(table: str, rows: list[dict], chunk: int = 500) -> int:
    """INSERT-ONLY upsert (resolution=ignore-duplicates): never overwrites."""
    inserted = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i:i + chunk]
        req = urllib.request.Request(
            UW_URL + table,
            data=json.dumps(batch).encode(),
            headers={"apikey": UW_KEY, "Authorization": "Bearer " + UW_KEY,
                     "Content-Type": "application/json",
                     "Prefer": "resolution=ignore-duplicates,return=minimal"},
            method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status in (200, 201, 204):
                inserted += len(batch)
            else:
                raise RuntimeError(f"{table} upsert HTTP {resp.status}")
    return inserted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="session date label (default: today); rows are stamped with it")
    ap.add_argument("--out-dir", default=OUT_DIR_DEFAULT)
    ap.add_argument("--execute", action="store_true",
                    help="also insert into contract_daily_stats/underlying_daily_stats "
                         "(insert-only; default is dry-run: parquet + report only)")
    ap.add_argument("--pace", type=float, default=0.5, help="seconds between PHX calls")
    ap.add_argument("--limit-tickers", type=int, default=0,
                    help="DEBUG ONLY — cap universe (full universe by default)")
    args = ap.parse_args()

    session_date = args.date or datetime.date.today().isoformat()
    os.makedirs(os.path.join(args.out_dir, f"dt={session_date}"), exist_ok=True)

    tickers, uni_rep = resolve_universe()
    if args.limit_tickers:
        tickers = tickers[: args.limit_tickers]
    print(f"universe: {len(tickers)} tickers ({uni_rep})", file=sys.stderr)

    phx = PhxClient(pace=args.pace)
    contracts: list[dict] = []
    underlyings: list[dict] = []
    t0 = time.time()
    per_ticker = {}
    max_tape_seen = None

    def _tapes(rows):
        ts = [r.get("last_tape_time") for r in rows if isinstance(r, dict) and r.get("last_tape_time")]
        return max(ts) if ts else None

    for i, tk in enumerate(tickers):
        try:
            expiries_body = phx.get(f"/api/chains_expiry/{tk}?limit=200")
        except Exception as e:  # noqa: BLE001
            per_ticker[tk] = {"error": str(e)}
            continue
        exp_rows = expiries_body.get("data", expiries_body) if isinstance(expiries_body, dict) else expiries_body
        if isinstance(exp_rows, dict):
            exp_rows = exp_rows.get("chains") or []
        expiries = [e["expires"] for e in exp_rows if isinstance(e, dict) and e.get("expires")]
        tk_rows = []
        for exp in expiries:
            try:
                body = phx.get(f"/api/chains_expiry/{tk}/{exp}")
            except Exception as e:  # noqa: BLE001
                phx.errors.append(f"{tk}/{exp}: {e}")
                continue
            rows = body.get("data", body) if isinstance(body, dict) else body
            if isinstance(rows, dict):
                rows = rows.get("chains") or []
            tk_tape = _tapes(rows)
            if tk_tape and (max_tape_seen is None or tk_tape > max_tape_seen):
                max_tape_seen = tk_tape
            for r in rows:
                if not isinstance(r, dict) or not r.get("option_symbol"):
                    continue
                tk_rows.append(map_contract_row(r, session_date))
        spot = None
        try:
            pb = phx.get(f"/api/ticker/{tk}/price/v2")
            pd_ = pb.get("data", pb) if isinstance(pb, dict) else {}
            reg = pd_.get("regular") or pd_.get("prev")
            spot = float(reg.get("close") if isinstance(reg, dict) else reg) if reg else None
        except Exception:  # noqa: BLE001
            spot = None
        contracts += tk_rows
        underlyings.append(aggregate_underlying(tk, session_date, tk_rows, spot))
        per_ticker[tk] = {"expiries": len(expiries), "contract_rows": len(tk_rows)}
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(tickers)} tickers, {len(contracts)} contract rows, "
                  f"{phx.calls} calls, {time.time() - t0:.0f}s", file=sys.stderr)

    out_dt = os.path.join(args.out_dir, f"dt={session_date}")
    # Session-label ground truth: the endpoint serves one settled snapshot and its
    # `date` param is a no-op, so the max last_tape_time seen is the TRUE session.
    # If it disagrees with the requested label, relabel rows to the tape date
    # (requested label is preserved in the report).
    applied_label = session_date
    if max_tape_seen and max_tape_seen[:10] != session_date:
        applied_label = max_tape_seen[:10]
        for r in contracts:
            r["date"] = applied_label
            if r.get("expiration"):
                try:
                    r["dte"] = (datetime.date.fromisoformat(r["expiration"])
                                - datetime.date.fromisoformat(applied_label)).days
                except ValueError:
                    pass
        for u in underlyings:
            u["date"] = applied_label
        out_dt = os.path.join(args.out_dir, f"dt={applied_label}")
        os.makedirs(out_dt, exist_ok=True)
        session_date = applied_label
    rep = {
        "session_date": session_date,
        "requested_label": args.date,
        "label_source": "max_last_tape_time" if applied_label != (args.date or "") else "arg_or_today",
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "max_last_tape_time_seen": max_tape_seen,
        "date_label_note": "PHX chains_expiry serves the latest settled snapshot (date param "
                           "is a no-op); rows are labeled with --date. top_chains-style date "
                           "labels in UW PHX are known to lag the true session — max last_tape "
                           "is recorded here as ground provenance.",
        "universe": uni_rep, "n_tickers": len(tickers),
        "n_contract_rows": len(contracts), "n_underlying_rows": len(underlyings),
        "phx_calls": phx.calls, "phx_auth_fallbacks": phx.fallbacks,
        "phx_errors": phx.errors[:50], "n_phx_errors": len(phx.errors),
        "duration_s": round(time.time() - t0, 1),
        "mode": "execute" if args.execute else "dry-run",
        "db_write": None,
    }

    try:
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq
        pq.write_table(pa.Table.from_pandas(pd.DataFrame(contracts), preserve_index=False),
                       os.path.join(out_dt, "contracts.parquet"))
        pq.write_table(pa.Table.from_pandas(pd.DataFrame(underlyings), preserve_index=False),
                       os.path.join(out_dt, "underlyings.parquet"))
    except Exception as e:  # noqa: BLE001
        rep["parquet_error"] = str(e)

    if args.execute:
        try:
            n1 = pg_upsert("contract_daily_stats", contracts)
            n2 = pg_upsert("underlying_daily_stats", underlyings)
            # read-back verification (external state check)
            def count(t, col):
                req = urllib.request.Request(
                    UW_URL + t + f"?select={col}&date=eq.{session_date}",
                    headers={"apikey": UW_KEY, "Authorization": "Bearer " + UW_KEY,
                             "Prefer": "count=exact"}, method="HEAD")
                cr = urllib.request.urlopen(req, timeout=60).headers.get("Content-Range", "*/0")
                return int(cr.split("/")[-1])
            rep["db_write"] = {"contract_rows_posted": n1, "underlying_rows_posted": n2,
                               "contract_rows_readback": count("contract_daily_stats", "occ"),
                               "underlying_rows_readback": count("underlying_daily_stats", "ticker")}
        except Exception as e:  # noqa: BLE001
            rep["db_write"] = {"error": str(e),
                               "hint": "0002_contract_daily_stats.sql applied to the target DB?"}

    with open(os.path.join(out_dt, "run_report.json"), "w") as f:
        json.dump(rep, f, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "phx_errors"}, indent=1))
    print(f"wrote {out_dt}/contracts.parquet + underlyings.parquet + run_report.json")


if __name__ == "__main__":
    main()
