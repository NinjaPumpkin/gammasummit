#!/usr/bin/env python3
"""E0.5a UW cache refresh — repair the batch-snapshot truncation data bug.

Bug (verified 2026-10-01 on live gamma_data_v2): PostgREST (Supabase) caps
every row response at the server-side db-max-rows limit (measured 1000) even
when the client requests more. The E0.2 fetch path (uw_rows_cached -> UWClient.q,
pre-fix) therefore cached at most 1,000 rows per (batch ts, ticker) snapshot
while a real batch carries 4,000+ rows (HEAD count 4,397 at
2026-09-30T16:26:06+00:00 SPX). 341/389 cache files held exactly 1,000 rows.
The E0.2 fit dataset (data/e02/fit_dataset) and every metric derived from it
(E0.3 harness, E0.4 acceptance stats) ran on silently truncated chains.

This script re-fetches every snapshot referenced by the fit index with the
PAGINATED client (UWClient.q fixed in this card) and rebuilds each fit record's
`uw` map from the complete rows using the exact prepare-time construction
(scripts/e02_cross_expiry_fit.py cmd_prepare: FEAT_KEYS order, expiry filter
against rec["expiries"], strike keys as f"{st:g}"). The Skylit side of each
record (expiries, strikes, node_values, node_types, cells, alignment) is NOT
touched — no RE captures needed, no re-pairing risk.

Snapshot completeness check per batch: HEAD count (count=exact) must equal the
cached row count after the refresh; mismatches are reported and fail the run.

Usage:
  python3 scripts/e05a_refresh_uw.py --env-file <dotenv>            # dry-run
  python3 scripts/e05a_refresh_uw.py --env-file <dotenv> --execute  # apply
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from collections import defaultdict

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)

from e02_cross_expiry_fit import (  # noqa: E402
    FEAT_KEYS, FITSET_DIR, UWCACHE_DIR, UWClient, UW_COLS, load_env_file,
)


def _jgzload(path):
    with gzip.open(path, "rt") as f:
        return json.load(f)


def _jgzdump(obj, path):
    # atomic replace: the other E0.5a worker reads these files concurrently
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def cache_path(ts: str, ticker: str) -> str:
    import re
    fn = re.sub(r"[^0-9A-Za-z]", "_", f"{ts}_{ticker}") + ".json.gz"
    return os.path.join(UWCACHE_DIR, fn)


def build_uwmap(rows, expiries):
    """Exact prepare-time uw map construction (cmd_prepare)."""
    eidx = {e: j for j, e in enumerate(expiries)}
    uwmap = defaultdict(dict)
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
    return {f"{st:g}": exp for st, exp in uwmap.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", help="dotenv with GAMMASUMMIT_UW_* / SUPABASE_* keys")
    ap.add_argument("--execute", action="store_true",
                    help="write refreshed caches + rebuilt records (default: dry-run)")
    ap.add_argument("--skip-fetch", action="store_true",
                    help="rebuild record uw maps from existing caches only (offline)")
    args = ap.parse_args()
    if args.env_file:
        load_env_file(args.env_file)

    with open(os.path.join(FITSET_DIR, "index.json")) as f:
        index = json.load(f)
    pairs = sorted({(e["uw_ts"], e["symbol"]) for e in index["instants"]})
    print(f"fit index: {len(index['instants'])} instants, "
          f"{len(pairs)} distinct (uw_ts, symbol) batches")

    log = {"pairs": [], "fetch_failures": [], "record_rebuilds": 0,
           "uw_cells_before": 0, "uw_cells_after": 0}
    refreshed: dict = {}  # (ts, sym) -> rows

    uw = None if args.skip_fetch else UWClient()
    for i, (ts, sym) in enumerate(pairs, 1):
        path = cache_path(ts, sym)
        before = _jgzload(path) if os.path.exists(path) else []
        entry = {"ts": ts, "symbol": sym, "cached_before": len(before)}
        if not args.skip_fetch:
            try:
                server_n = uw.q("gamma_data_v2", select="strike", head=True,
                                params={"ticker": f"eq.{sym}", "timestamp": f"eq.{ts}"})
            except Exception as ex:  # noqa: BLE001
                log["fetch_failures"].append({"ts": ts, "symbol": sym, "error": str(ex)})
                continue
            entry["server_count"] = server_n
            if len(before) != server_n:
                # paginated fetch through the FIXED client (full snapshot)
                rows = uw.q("gamma_data_v2", select=UW_COLS,
                            params={"ticker": f"eq.{sym}", "timestamp": f"eq.{ts}"})
                entry["refetched"] = True
                if args.execute:
                    _jgzdump(rows, path)  # overwrite truncated cache file
            else:
                rows = before
                entry["refetched"] = False
            entry["fetched"] = len(rows)
            entry["complete"] = len(rows) == server_n
        else:
            rows = before
            entry["fetched"] = len(rows)
            entry["complete"] = None
        refreshed[(ts, sym)] = rows
        log["pairs"].append(entry)
        if i % 50 == 0:
            print(f"  ... {i}/{len(pairs)} batches", flush=True)

    bad = [e for e in log["pairs"] if e.get("complete") is False]
    print(f"batches: {len(log['pairs'])}, incomplete after fetch: {len(bad)}, "
          f"fetch failures: {len(log['fetch_failures'])}")

    # ---- rebuild record uw maps --------------------------------------------
    instants = sorted(index["instants"], key=lambda e: (e["symbol"], e["uw_ts"], e["asOf"]))
    for n, e in enumerate(instants, 1):
        rpath = os.path.join(FITSET_DIR, e["key"].replace("/", "_") + ".json.gz")
        rec = _jgzload(rpath)
        rows = refreshed.get((rec["uw_ts"], rec["symbol"]))
        if rows is None:
            continue
        before_cells = sum(len(v) for v in rec["uw"].values())
        new_uw = build_uwmap(rows, rec["expiries"])
        after_cells = sum(len(v) for v in new_uw.values())
        log["uw_cells_before"] += before_cells
        log["uw_cells_after"] += after_cells
        log["record_rebuilds"] += 1
        if args.execute:
            rec["uw"] = new_uw
            _jgzdump(rec, rpath)
        if n % 200 == 0:
            print(f"  ... {n}/{len(instants)} records rebuilt", flush=True)

    out = os.path.join(os.path.dirname(FITSET_DIR), "..", "e05a", "refresh_uw_log.json")
    out = os.path.normpath(out)
    print(f"\nuw (strike,expiry) cells across records: "
          f"{log['uw_cells_before']} -> {log['uw_cells_after']}")
    if args.execute:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(log, f, indent=1)
        print("wrote", out)
    else:
        print("DRY-RUN: nothing written. re-run with --execute to apply")
    complete = sum(1 for e in log["pairs"] if e.get("complete"))
    print(f"snapshot completeness: {complete}/{len(log['pairs'])} verified equal to HEAD count")
    return 0 if (args.skip_fetch or complete == len(log["pairs"])) and not log["fetch_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
