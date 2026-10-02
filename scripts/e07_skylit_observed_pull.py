#!/usr/bin/env python3
"""E0.7 observed-picks puller — Skylit Flowseeker API (READ-ONLY, paced).

Pulls the surfaces that encode "which tickers does Skylit surface" for a set of
historical dates (daily rollup tables) and saves raw JSON + observations.jsonl:

  /v1/underlying?date=D&limit=500            full options-active universe, premium-ranked (1 cr)
  /v1/underlying/top/daily?date=D            top tickers by premium|volume|net_premium (1 cr each)
  /v1/contract/top/daily?date=D              market-wide top contracts (3 cr)
  /v1/contract/unusual-volume?date=D         RVOL anomalies, defaults = product defaults (3 cr)
  /v1/contract/unusual-oi?date=D             OI-change anomalies, defaults (3 cr)

Pacing: >=3 s between calls (50%-of-limit rule; limit 120 rpm), backoff on 429,
HARD STOP on 402 (out of credits). API key from .env (SKYLIT_API_KEY) — never
printed. Skylit API = temporary RE tool; production runs UW-only.

Usage:
  python3 scripts/e07_skylit_observed_pull.py --dates 2026-09-29 2026-09-30
  python3 scripts/e07_skylit_observed_pull.py --dates ... --dry-run   # cost report only
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "e07", "skylit_api")
OBS_PATH = os.path.join(ROOT, "data", "e07", "observations.jsonl")
BASE = "https://api.skylit.ai"
MIN_GAP_S = 3.0


def load_key() -> str:
    k = os.environ.get("GAMMASUMMIT_SKYLIT_API_KEY") or os.environ.get("SKYLIT_API_KEY")
    if k:
        return k
    for p in (os.path.join(ROOT, ".env"), os.path.expanduser("~/.hermes/.env")):
        if not os.path.isfile(p):
            continue
        for line in open(p):
            line = line.strip()
            if line.startswith("SKYLIT_API_KEY=") or line.startswith("GAMMASUMMIT_SKYLIT_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("SKYLIT_API_KEY not found (gammasummit/.env or ~/.hermes/.env)")


def call(key: str, path: str, params: dict) -> tuple[int, dict | str, dict]:
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key,
                                               "Accept": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=60)
        body = json.loads(r.read())
        meta = {h: r.headers.get(h) for h in ("X-Credits-Remaining", "X-RateLimit-Remaining",
                                              "X-RateLimit-Limit")}
        return r.status, body, meta
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, raw, {"X-Credits-Remaining": e.headers.get("X-Credits-Remaining")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="+", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--include-market-overview", action="store_true")
    args = ap.parse_args()

    # endpoint plan: (path, params_fn, credits, label)
    def plan(date: str):
        eps = [
            ("/v1/underlying", {"date": date, "limit": 500}, 1, "underlying_universe"),
            ("/v1/underlying/top/daily", {"date": date, "limit": 100, "order_by": "premium"}, 1, "top_tickers_premium"),
            ("/v1/underlying/top/daily", {"date": date, "limit": 100, "order_by": "volume"}, 1, "top_tickers_volume"),
            ("/v1/underlying/top/daily", {"date": date, "limit": 100, "order_by": "net_premium"}, 1, "top_tickers_net_premium"),
            ("/v1/contract/top/daily", {"date": date, "limit": 100}, 3, "top_contracts_premium"),
            ("/v1/contract/unusual-volume", {"date": date, "limit": 100}, 3, "unusual_volume"),
            ("/v1/contract/unusual-oi", {"date": date, "limit": 100}, 3, "unusual_oi"),
        ]
        if args.include_market_overview:
            eps.append(("/v1/market/overview", {"date": date}, 1, "market_overview"))
        return eps

    total = sum(c for d in args.dates for (_, _, c, _) in plan(d))
    print(f"plan: {len(args.dates)} dates x ~{total // max(len(args.dates),1)} cr = ~{total} credits")
    if args.dry_run:
        for d in args.dates:
            for path, params, cr, label in plan(d):
                print(f"  {d} {label:26s} {cr}cr GET {path} {params}")
        return

    key = load_key()
    os.makedirs(OUT_DIR, exist_ok=True)
    last_call = 0.0
    for d in args.dates:
        for path, params, cr, label in plan(d):
            gap = time.time() - last_call
            if gap < MIN_GAP_S:
                time.sleep(MIN_GAP_S - gap)
            last_call = time.time()
            status, body, meta = call(key, path, params)
            credits_left = meta.get("X-Credits-Remaining")
            print(f"{d} {label:26s} -> {status}  credits_left={credits_left}")
            if status == 429:
                print("RATE LIMITED — backing off 60s (incident: record + stop per standing rule)")
                time.sleep(60)
                status, body, meta = call(key, path, params)
                print(f"  retry -> {status} credits_left={meta.get('X-Credits-Remaining')}")
                if status == 429:
                    raise SystemExit("still rate limited — aborting run (standing rule: never hit limits)")
            if status == 402:
                raise SystemExit("402 out of credits — stopping (do not top up without owner)")
            if status == 200:
                fn = os.path.join(OUT_DIR, f"{d}_{label}.json")
                with open(fn, "w") as f:
                    json.dump(body, f)
                rows = body.get("data") if isinstance(body, dict) else None
                n = len(rows) if isinstance(rows, list) else "?"
                with open(OBS_PATH, "a") as f:
                    f.write(json.dumps({
                        "ts_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "source": f"skylit_api:{path}",
                        "params": params,
                        "target_date": d,
                        "label": label,
                        "n_rows": n,
                        "file": os.path.relpath(fn, ROOT),
                        "credits_left": credits_left,
                    }) + "\n")
            else:
                print("  body:", str(body)[:200])
    print("done")


if __name__ == "__main__":
    main()
