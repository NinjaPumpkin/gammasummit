#!/usr/bin/env python3
"""P0 parity dataset — inventory, UW coverage cross-check, session-day frame list.

E0.1 deliverable (gammasummit). READ-ONLY against every external system:
- RE captures on /Volumes/X10 Pro (never written)
- SignalForge Supabase gamma_data_v2 via PostgREST SELECT/HEAD only

Credentials (never hardcode, never commit):
  GAMMASUMMIT_UW_URL            Supabase project URL (https://<ref>.supabase.co)
  GAMMASUMMIT_UW_SERVICE_KEY   service key for read-only REST queries

Subcommands:
  inventory     scan RE raw captures -> data/p0/re_inventory.json
  uw-coverage   probe gamma_data_v2 coverage -> data/p0/uw_coverage.json
  frames        build session-day frame list -> data/p0/session_day_frames.{json,csv}
  verify        run alignment checks over the built frame list (exit != 0 on failure)

Importable loaders (used by later E0 cards):
  load_manifest(), load_matrix_file(), load_range_file(),
  uw_snapshot_timestamps(), uw_rows_at(), align_day()

Usage:
  python3 scripts/p0_parity_dataset.py inventory
  python3 scripts/p0_parity_dataset.py uw-coverage --days 2026-09-28,2026-09-29,2026-09-30
  python3 scripts/p0_parity_dataset.py frames
  python3 scripts/p0_parity_dataset.py verify
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from typing import Any
from datetime import date, datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_ROOT = "/Volumes/X10 Pro/gammasummit/t3/re/raw"
OUT_DIR = os.path.join(REPO, "data", "p0")
MANIFEST_JSONL = os.path.join(OUT_DIR, "capture_manifest.jsonl")
KINDS = ("matrix/gamma", "matrix/vanna", "range/gamma")

# Alignment tolerance: RE matrix captures land on whole minutes; UW daemon batch
# timestamps are wall-clock commit times (odd seconds). Same-instant pairing in
# the 09-30 rescore was exact; replay pairs need a nearest-within-tolerance rule.
ALIGN_TOL_S = float(os.environ.get("GAMMASUMMIT_ALIGN_TOL_S", "90"))


# ---------------------------------------------------------------- RE loaders

def load_manifest(path: str = MANIFEST_JSONL) -> list[dict]:
    """capture_manifest.jsonl -> list of {t, metric?, kind?, file, credits_remaining}."""
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def manifest_kind(rec: dict) -> str:
    m = re.search(r"/re/raw/(matrix|range)/([^/]+)/", rec["file"])
    return f"{m.group(1)}/{m.group(2)}" if m else "unknown"


def load_matrix_file(path: str) -> dict:
    """One matrix capture -> {meta, symbols: {SYM: {asOf, spot, expirations,
    strikes: [{strike, value, nodeType}], cells: {(strike, expiry): value}}}}."""
    with gzip.open(path, "rt") as f:
        d = json.load(f)
    out = {"meta": d.get("meta", {}), "symbols": {}}
    for sym in d.get("data", {}).get("symbols", []):
        exps = sym.get("expirations", [])
        cells = {}
        for i, row in enumerate(sym.get("matrix", [])):
            strike = sym["strikes"][i]["strike"]
            for j, v in enumerate(row):
                if v:
                    cells[(float(strike), exps[j])] = v
        out["symbols"][sym["symbol"]] = {
            "asOf": sym.get("asOf"),
            "spot": sym.get("spot"),
            "expirations": exps,
            "strikes": sym.get("strikes", []),
            "cells": cells,
        }
    return out


def load_range_file(path: str) -> dict:
    """One range capture -> {meta, from, to, symbols: {SYM: {axes, frames}}}."""
    with gzip.open(path, "rt") as f:
        d = json.load(f)
    data = d.get("data", {})
    out = {"meta": d.get("meta", {}), "from": data.get("from"), "to": data.get("to"),
           "symbols": {}}
    for sym in data.get("symbols", []):
        out["symbols"][sym["symbol"]] = {"axes": sym.get("axes", []), "frames": sym.get("frames", [])}
    return out


# ---------------------------------------------------------------- UW access

class UWClient:
    """Read-only PostgREST client for gamma_data_v2 (SELECT / HEAD only)."""

    def __init__(self):
        self.url = os.environ.get("GAMMASUMMIT_UW_URL", "").rstrip("/") + "/rest/v1"
        self.key = os.environ.get("GAMMASUMMIT_UW_SERVICE_KEY", "")
        if not self.key or "rest/v1" == self.url:
            raise SystemExit("set GAMMASUMMIT_UW_URL and GAMMASUMMIT_UW_SERVICE_KEY")

    def q(self, table, *, select="*", head=False, params=None, limit=None, order=None, retries=3) -> Any:
        # E0.5a fix: PostgREST (Supabase) truncates every row response at the
        # server-side db-max-rows cap (measured 1000) regardless of the
        # requested limit. Row fetches now paginate via limit/offset until
        # exhausted or the requested limit is reached; HEAD unchanged.
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
                    with urllib.request.urlopen(req, timeout=90) as r:
                        body = r.read()
                        if head:
                            return int(r.headers.get("Content-Range", "*/0").split("/")[1])
                        return json.loads(body) if body else []
                except Exception as e:
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


def uw_day_rowcount(uw: UWClient, day: str, ticker: str) -> int:
    lo, hi = _day_bounds(day)
    try:
        return uw.q("gamma_data_v2", head=True,
                    params={"ticker": f"eq.{ticker}", "and": f"(timestamp.gte.{lo},timestamp.lt.{hi})"})
    except Exception:
        return -1  # probe failure (e.g. count timeout) — recorded, never faked


SNAPSHOT_CACHE = os.path.join(OUT_DIR, "uw_snapshot_cache.json")


def _snapshot_cache_load() -> dict:
    if os.path.exists(SNAPSHOT_CACHE):
        with open(SNAPSHOT_CACHE) as f:
            return json.load(f)
    return {}


def _snapshot_cache_save(cache: dict):
    with open(SNAPSHOT_CACHE, "w") as f:
        json.dump(cache, f, indent=1)


def uw_snapshot_timestamps(uw: UWClient, day: str, ticker: str = "SPX", use_cache: bool = True) -> list[str]:
    """Enumerate distinct gamma_data_v2 batch timestamps for one day.

    Batch rows share one timestamp per daemon cycle, so walking 'first ts after t'
    yields one query per snapshot. Results cached in data/p0/uw_snapshot_cache.json."""
    cache = _snapshot_cache_load()
    if use_cache and day in cache:
        return cache[day]
    lo, hi = _day_bounds(day)
    out = []
    cursor = lo
    while True:
        rows = uw.q("gamma_data_v2", select="timestamp",
                    params={"ticker": f"eq.{ticker}",
                            "and": f"(timestamp.gte.{cursor},timestamp.lt.{hi})"},
                    order="timestamp.asc", limit=1)
        if not rows:
            break
        ts = rows[0]["timestamp"]
        if out and ts == out[-1]:
            break
        out.append(ts)
        # advance strictly past this timestamp
        cursor = ts.replace("+00:00", "+00:00.000001") if ts.endswith("+00:00") else ts + "+00:00.000001"
        if len(out) > 2000:
            break
    cache[day] = out
    _snapshot_cache_save(cache)
    return out


def uw_rows_at(uw: UWClient, ts: str, tickers: list[str]) -> list[dict]:
    """All strike rows of one snapshot (exact timestamp match) for the given tickers."""
    out = []
    for tk in tickers:
        out += uw.q("gamma_data_v2", select="*",
                    params={"ticker": f"eq.{tk}", "timestamp": f"eq.{ts}"}, limit=10000)
    return out


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def align_day(rec_instants: list[str], uw_ts: list[str], tol_s: float = ALIGN_TOL_S):
    """Nearest-UW-within-tolerance alignment. Returns per-instant records + stats."""
    uwd = [_ts(t) for t in uw_ts]
    recs, misses = [], 0
    deltas = []
    for inst in rec_instants:
        t = _ts(inst)
        best, best_dt = None, None
        for u in uwd:
            dt = abs((u - t).total_seconds())
            if best_dt is None or dt < best_dt:
                best, best_dt = u, dt
        if best is not None and best_dt is not None and best_dt <= tol_s:
            deltas.append(best_dt)
            recs.append({"re_instant": inst, "uw_ts": best.isoformat(), "dt_s": round(best_dt, 3)})
        else:
            misses += 1
            recs.append({"re_instant": inst, "uw_ts": None,
                         "dt_s": round(best_dt, 3) if best_dt is not None else None})
    deltas.sort()
    stats = {
        "n_re_instants": len(rec_instants),
        "n_uw_snapshots": len(uw_ts),
        "n_aligned": len(rec_instants) - misses,
        "n_unaligned": misses,
        "tol_s": tol_s,
        "dt_s_median": deltas[len(deltas) // 2] if deltas else None,
        "dt_s_max": max(deltas) if deltas else None,
    }
    return recs, stats


# ---------------------------------------------------------------- commands

def cmd_inventory(_args):
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = load_manifest()
    inv = {
        "raw_root": RAW_ROOT,
        "scanned_at": datetime.utcnow().isoformat() + "Z",
        "manifest_entries": len(manifest),
        "manifest_by_kind": dict(Counter(manifest_kind(r) for r in manifest)),
        "manifest_by_day": dict(Counter(r["t"][:10] for r in manifest)),
        "disk_files_real": {},
        "disk_appledouble": 0,
        "manifest_vs_disk_mismatch": [],
        "node_types": Counter(),
        "node_types_by_symbol": defaultdict(Counter),
        "matrix_meta": Counter(),
        "range_meta": Counter(),
        "range_frame_counts": Counter(),
        "symbols_seen": Counter(),
        "asof_filename_mismatch": 0,
        "asof_mismatch_samples": [],
        "asof_stale_by_symbol_day": Counter(),   # records where |asOf − window_start| > 2s
        "asof_lag_hist": Counter(),              # rounded (asOf − window_start) seconds
        "scan_errors": [],
        "files_scanned": 0,
        "vol_sidecar_files": [],
    }
    for sub in KINDS:
        d = os.path.join(RAW_ROOT, sub)
        per = {}
        for day in sorted(os.listdir(d)):
            if day.startswith("._") or not os.path.isdir(os.path.join(d, day)):
                continue
            names = os.listdir(os.path.join(d, day))
            real = [n for n in names if not n.startswith("._")]
            inv["disk_appledouble"] += len(names) - len(real)
            per[day] = len(real)
        inv["disk_files_real"][sub] = per
    for e in sorted(os.listdir(RAW_ROOT)):
        if e.startswith("vol_") and not e.startswith("._"):
            inv["vol_sidecar_files"].append(e)

    man_idx = Counter((manifest_kind(r), r["t"][:10]) for r in manifest)
    for sub, per in inv["disk_files_real"].items():
        for day, n in per.items():
            if man_idx.get((sub, day)) != n:
                inv["manifest_vs_disk_mismatch"].append(
                    {"kind": sub, "day": day, "disk": n, "manifest": man_idx.get((sub, day))})

    t0 = time.time()
    for rec in manifest:
        p = rec["file"]
        try:
            if "/matrix/" in p:
                with gzip.open(p, "rt") as f:
                    d = json.load(f)
                meta = d.get("meta", {})
                inv["matrix_meta"][json.dumps({k: meta.get(k) for k in ("metric", "resolution", "mode", "cached")}, sort_keys=True)] += 1
                fname_asof = os.path.basename(p).replace(".json.gz", "")
                rec_day = rec["t"][:10]
                win_start = datetime.fromisoformat(f"{rec_day}T{fname_asof[:2]}:{fname_asof[2:4]}:{fname_asof[4:6]}+00:00")
                for sym in d.get("data", {}).get("symbols", []):
                    inv["symbols_seen"][sym["symbol"]] += 1
                    asof_raw = sym.get("asOf")
                    try:
                        asof_dt = datetime.fromisoformat((asof_raw or "").replace("Z", "+00:00"))
                        lag = round((asof_dt - win_start).total_seconds())
                        inv["asof_lag_hist"][str(min(max(lag, -3600), 3600))] += 1
                        if abs(lag) > 2:
                            inv["asof_filename_mismatch"] += 1
                            inv["asof_stale_by_symbol_day"][f"{sym['symbol']}|{rec_day}"] += 1
                            if len(inv["asof_mismatch_samples"]) < 5:
                                inv["asof_mismatch_samples"].append(
                                    {"file": p.split("/raw/")[1], "symbol": sym["symbol"], "asOf": asof_raw, "lag_s": lag})
                    except Exception:
                        inv["asof_filename_mismatch"] += 1
                    for st in sym.get("strikes", []):
                        inv["node_types"][st.get("nodeType")] += 1
                        inv["node_types_by_symbol"][sym["symbol"]][st.get("nodeType")] += 1
            else:
                with gzip.open(p, "rt") as f:
                    d = json.load(f)
                meta = d.get("meta", {})
                inv["range_meta"][json.dumps({k: meta.get(k) for k in ("metric", "resolution", "mode", "cached")}, sort_keys=True)] += 1
                for sym in d.get("data", {}).get("symbols", []):
                    inv["range_frame_counts"][len(sym.get("frames", []))] += 1
            inv["files_scanned"] += 1
        except Exception as e:
            inv["scan_errors"].append({"file": p, "err": str(e)})
        if inv["files_scanned"] % 500 == 0:
            print(f"  scanned {inv['files_scanned']}/{len(manifest)} ({time.time()-t0:.0f}s)", flush=True)

    inv["node_types"] = dict(inv["node_types"])
    inv["node_types_by_symbol"] = {k: dict(v) for k, v in inv["node_types_by_symbol"].items()}
    inv["asof_stale_by_symbol_day"] = dict(inv["asof_stale_by_symbol_day"])
    inv["asof_lag_hist"] = dict(inv["asof_lag_hist"])
    inv["matrix_meta"] = dict(inv["matrix_meta"])
    inv["range_meta"] = dict(inv["range_meta"])
    inv["range_frame_counts"] = {str(k): v for k, v in inv["range_frame_counts"].items()}
    inv["symbols_seen"] = dict(inv["symbols_seen"])
    inv["elapsed_s"] = round(time.time() - t0, 1)
    out = os.path.join(OUT_DIR, "re_inventory.json")
    with open(out, "w") as f:
        json.dump(inv, f, indent=1, default=str)
    print("wrote", out)
    print("files_scanned", inv["files_scanned"], "scan_errors", len(inv["scan_errors"]))
    print("node_types", inv["node_types"])
    return 0


def cmd_uw_coverage(args):
    os.makedirs(OUT_DIR, exist_ok=True)
    uw = UWClient()
    days = args.days.split(",") if args.days else [
        d.isoformat() for d in [date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4),
                               date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10), date(2026, 9, 11),
                               date(2026, 9, 12), date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 17),
                               date(2026, 9, 18), date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24),
                               date(2026, 9, 25), date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]]
    out = {"table": "gamma_data_v2", "probed_at": datetime.utcnow().isoformat() + "Z",
           "min_ts": None, "max_ts": None, "days": {}}
    r = uw.q("gamma_data_v2", select="timestamp", order="timestamp.asc", limit=1)
    out["min_ts"] = r[0]["timestamp"] if r else None
    r = uw.q("gamma_data_v2", select="timestamp", order="timestamp.desc", limit=1)
    out["max_ts"] = r[0]["timestamp"] if r else None
    print("gamma_data_v2 span:", out["min_ts"], "->", out["max_ts"])
    for day in days:
        rec = {"tickers": {}}
        for tk in ["SPX", "SPY", "QQQ", "IWM"]:
            rec["tickers"][tk] = uw_day_rowcount(uw, day, tk)
        ts = uw_snapshot_timestamps(uw, day) if any(v > 0 for v in rec["tickers"].values()) else []
        rec["n_snapshots"] = len(ts)
        if ts:
            rec["first_ts"], rec["last_ts"] = ts[0], ts[-1]
        out["days"][day] = rec
        print(day, rec["tickers"], "snapshots:", rec["n_snapshots"], flush=True)
    path = os.path.join(OUT_DIR, "uw_coverage.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", path)
    return 0


def cmd_frames(args):
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = load_manifest()
    uw = UWClient()
    by_day = defaultdict(lambda: {"matrix_gamma": [], "matrix_vanna": [], "range_gamma": []})
    for rec in manifest:
        k = manifest_kind(rec)
        slot = {"matrix/gamma": "matrix_gamma", "matrix/vanna": "matrix_vanna",
                "range/gamma": "range_gamma"}[k]
        by_day[rec["t"][:10]][slot].append(rec)

    frames = []
    for day in sorted(by_day):
        slots = by_day[day]
        instants = [r["t"] for r in sorted(slots["matrix_gamma"], key=lambda r: r["t"])]
        n_rows = sum(uw_day_rowcount(uw, day, tk) for tk in ["SPX", "SPY", "QQQ", "IWM"])
        rec = {
            "session_day": day,
            "re": {
                "matrix_gamma_captures": len(slots["matrix_gamma"]),
                "matrix_vanna_captures": len(slots["matrix_vanna"]),
                "range_gamma_windows": len(slots["range_gamma"]),
                "first_instant": instants[0] if instants else None,
                "last_instant": instants[-1] if instants else None,
            },
            "uw": {"gamma_data_v2_rows_4_symbols": n_rows},
        }
        if n_rows:
            ts = uw_snapshot_timestamps(uw, day)
            rec["uw"]["n_snapshots"] = len(ts)
            rec["uw"]["first_ts"], rec["uw"]["last_ts"] = ts[0], ts[-1]
            al, stats = align_day(instants, ts)
            rec["alignment"] = stats
            rec["status"] = "aligned" if stats["n_unaligned"] == 0 else "aligned-partial"
        else:
            rec["uw"]["n_snapshots"] = 0
            rec["alignment"] = {"n_re_instants": len(instants), "n_uw_snapshots": 0,
                                "n_aligned": 0, "n_unaligned": len(instants), "tol_s": ALIGN_TOL_S}
            rec["status"] = "skylit-only"
        frames.append(rec)
        print(day, rec["status"], rec["uw"], rec.get("alignment", {}).get("dt_s_median"), flush=True)

    out = {"built_at": datetime.utcnow().isoformat() + "Z", "tol_s": ALIGN_TOL_S,
           "n_session_days": len(frames),
           "n_aligned_days": sum(1 for f in frames if f["status"].startswith("aligned")),
           "frames": frames}
    with open(os.path.join(OUT_DIR, "session_day_frames.json"), "w") as f:
        json.dump(out, f, indent=1)
    with open(os.path.join(OUT_DIR, "session_day_frames.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["session_day", "status", "re_matrix_gamma", "re_matrix_vanna", "re_range_windows",
                    "uw_rows_4sym", "uw_snapshots", "aligned_instants", "unaligned_instants", "dt_s_median"])
        for r in frames:
            a = r.get("alignment", {})
            w.writerow([r["session_day"], r["status"], r["re"]["matrix_gamma_captures"],
                        r["re"]["matrix_vanna_captures"], r["re"]["range_gamma_windows"],
                        r["uw"]["gamma_data_v2_rows_4_symbols"], r["uw"].get("n_snapshots", 0),
                        a.get("n_aligned", 0), a.get("n_unaligned", 0), a.get("dt_s_median")])
    print("wrote session_day_frames.{json,csv}; aligned days:", out["n_aligned_days"], "/", out["n_session_days"])
    return 0


def cmd_verify(_args):
    ok = True
    inv_p = os.path.join(OUT_DIR, "re_inventory.json")
    fr_p = os.path.join(OUT_DIR, "session_day_frames.json")
    for p in (inv_p, fr_p, MANIFEST_JSONL):
        if not os.path.exists(p):
            print("MISSING", p)
            ok = False
    if not ok:
        return 1
    inv = json.load(open(inv_p))
    fr = json.load(open(fr_p))
    print("manifest entries:", inv["manifest_entries"], "files scanned:", inv["files_scanned"])
    ok &= inv["files_scanned"] + len(inv["scan_errors"]) == inv["manifest_entries"]
    print("manifest vs disk mismatches:", len(inv["manifest_vs_disk_mismatch"]))
    ok &= not inv["manifest_vs_disk_mismatch"]
    print("scan errors:", len(inv["scan_errors"]))
    ok &= not inv["scan_errors"]
    print("node type census:", inv["node_types"])
    print("session days in frame list:", fr["n_session_days"],
          "aligned:", fr["n_aligned_days"])
    aligned = [f for f in fr["frames"] if f["status"].startswith("aligned")]
    for f in aligned:
        a = f["alignment"]
        print(f"  {f['session_day']}: aligned {a['n_aligned']}/{a['n_re_instants']} "
              f"dt_median={a.get('dt_s_median')} dt_max={a.get('dt_s_max')}")
        ok &= a["n_aligned"] > 0
    print("VERIFY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory")
    p = sub.add_parser("uw-coverage")
    p.add_argument("--days", help="comma-separated YYYY-MM-DD list (default: 20 RE session-days)")
    sub.add_parser("frames")
    sub.add_parser("verify")
    args = ap.parse_args()
    return {"inventory": cmd_inventory, "uw-coverage": cmd_uw_coverage,
            "frames": cmd_frames, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
