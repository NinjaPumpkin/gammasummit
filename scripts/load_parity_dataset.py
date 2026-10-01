#!/usr/bin/env python3
"""load_parity_dataset.py — P0 parity dataset loader + validator (E0.1).

Read-only tool. Builds / validates the parity dataset from two sources:

  1. Skylit RE captures (read-only) at
     /Volumes/X10 Pro/gammasummit/t3/re/raw/
     - capture_manifest.jsonl  capture log (t, metric, file, credits_remaining)
     - matrix/<metric>/<date>/<HHMMSS>.json.gz   per-strike value + nodeType
       grid (+ per-expiry matrix column breakdown), 4 symbols per file
     - range/gamma/<date>/<HHMMSS>.json.gz       1s frames, 26 expiry axes
  2. SignalForge Supabase `gamma_data_v2` (UW-derived strike x expiry rows)
     via PostgREST **GET only** — NEVER writes to SignalForge prod.

Safety:
  - Only HTTP GET is ever issued to the Supabase REST API.
  - No writes anywhere except output files under data/parity-evidence/.
  - Credentials come from env vars only:
      GAMMASUMMIT_UW_URL              Supabase project URL
      GAMMASUMMIT_UW_SERVICE_KEY      service key (read queries)
    (aliases GAMMASUMMIT_SUPABASE_URL / GAMMASUMMIT_SUPABASE_SERVICE_KEY)

Subcommands:
  inventory   file-level inventory of the RE raw tree + manifest + fidelity
  scan-matrix full parse of matrix/*.json.gz -> matrix_scan.jsonl (resumable)
  uw-check    per-session-day UW gamma_data_v2 coverage + input-column check
  frames      join scan + UW -> session-day frame list + alignment + tables
  all         inventory -> scan-matrix -> uw-check -> frames

Outputs (all under data/parity-evidence/):
  re_inventory.json     file counts, per-day coverage, gaps, node-type census
  matrix_scan.jsonl     one line per matrix capture (resumable append)
  uw_coverage.json      per day/ticker UW coverage + column completeness
  session_day_frames.json  the documented session-day frame list
  availability.md       per-day availability + alignment tables (markdown)
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

RAW_ROOT = "/Volumes/X10 Pro/gammasummit/t3/re/raw"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO, "data", "parity-evidence")

SYMBOLS = ("SPX", "SPY", "QQQ", "IWM")

# RTH window in UTC (ET 09:30-16:00, UTC-4 in Sept 2026)
RTH_START = "13:30:00"
RTH_END = "20:00:00"

# UW gamma_data_v2 columns required as clean-room exposure inputs
UW_INPUT_COLUMNS = (
    "ticker", "strike", "expiry_date", "timestamp", "spot_price",
    "call_gex", "put_gex", "gex_value",
    "call_vanna", "put_vanna",
    "call_bid_vol", "call_ask_vol", "put_bid_vol", "put_ask_vol",
    "call_prev_oi", "put_prev_oi",
    "call_oi", "put_oi", "iv",
)


# ---------------------------------------------------------------- utilities

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def out_path(name: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    return os.path.join(OUT_DIR, name)


def read_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def uw_env() -> tuple[str, str]:
    url = os.environ.get("GAMMASUMMIT_UW_URL") or os.environ.get(
        "GAMMASUMMIT_SUPABASE_URL"
    )
    key = os.environ.get("GAMMASUMMIT_UW_SERVICE_KEY") or os.environ.get(
        "GAMMASUMMIT_SUPABASE_SERVICE_KEY"
    )
    if not url or not key:
        sys.exit(
            "missing env: set GAMMASUMMIT_UW_URL + GAMMASUMMIT_UW_SERVICE_KEY"
        )
    return url.rstrip("/"), key


def uw_get(url: str, key: str, table: str, params: dict, head: bool = False):
    """READ-ONLY PostgREST call. GET/HEAD only — hard-guaranteed here."""
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}?{qs}",
        method="HEAD" if head else "GET",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "count=exact",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8") if not head else ""
            cr = resp.headers.get("Content-Range", "*/*")
            return json.loads(body) if body else [], cr
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{table} {params}: HTTP {e.code} {e.read()[:200]!r}")


def count_from_range(cr: str) -> int:
    # "0-999/17461" -> 17461 ; "*/*" or "*/0" -> 0
    try:
        return int(cr.split("/")[-1])
    except ValueError:
        return -1


def parse_day(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


# --------------------------------------------------------------- inventory

def list_capture_files(metric_dir: str) -> list[str]:
    """All *.json.gz under a metric dir, excluding macOS AppleDouble junk."""
    files = []
    for path in glob.glob(os.path.join(metric_dir, "*", "*.json.gz")):
        if os.path.basename(path).startswith("._"):
            continue
        files.append(path)
    return sorted(files)


def cmd_inventory(args) -> None:
    raw = args.raw_root
    manifest_path = os.path.join(raw, "capture_manifest.jsonl")

    manifest = list(read_jsonl_manifest(manifest_path))
    inv: dict = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "raw_root": raw,
        "manifest_lines": len(manifest),
        "apple_double_junk_files": 0,
        "layers": {},
        "days": {},
    }

    # walk every layer/metric
    for layer in ("matrix", "range"):
        for metric in sorted(os.listdir(os.path.join(raw, layer))):
            mdir = os.path.join(raw, layer, metric)
            if not os.path.isdir(mdir):
                continue
            junk = 0
            for day_d in os.listdir(mdir):
                dpath = os.path.join(mdir, day_d)
                if not os.path.isdir(dpath):
                    if day_d.startswith("._"):
                        junk += 1
                    continue
                junk += sum(
                    1 for f in os.listdir(dpath) if f.startswith("._")
                )
            inv["apple_double_junk_files"] += junk
            files = list_capture_files(mdir)
            by_day: dict[str, list[str]] = {}
            for f in files:
                day = os.path.basename(os.path.dirname(f))
                by_day.setdefault(day, []).append(os.path.basename(f)[:6])
            inv["layers"][f"{layer}/{metric}"] = {
                "files": len(files),
                "days": len(by_day),
                "first_day": min(by_day) if by_day else None,
                "last_day": max(by_day) if by_day else None,
            }
            for day, tss in sorted(by_day.items()):
                d = inv["days"].setdefault(day, {})
                d[f"{layer}/{metric}_files"] = len(tss)
                d[f"{layer}/{metric}_first"] = min(tss)
                d[f"{layer}/{metric}_last"] = max(tss)

    # manifest reconciliation + per-metric counts
    man_by_metric: dict[str, int] = {}
    man_days: dict[str, set] = {}
    for row in manifest:
        m = row.get("metric") or row.get("kind") or "?"
        man_by_metric[m] = man_by_metric.get(m, 0) + 1
        day = (row.get("t") or "")[:10]
        man_days.setdefault(m, set()).add(day)
    inv["manifest_by_metric"] = man_by_metric
    inv["manifest_days"] = {k: sorted(v) for k, v in man_days.items()}

    # sampled node-type census: 3 gamma + 3 vanna files per day (first/mid/last)
    census: dict[str, int] = {}
    sampled = 0
    for day in sorted(inv["days"]):
        for metric in ("gamma", "vanna"):
            mdir = os.path.join(raw, "matrix", metric, day)
            files = [f for f in sorted(os.listdir(mdir)) if f.endswith(".json.gz")
                     and not f.startswith("._")]
            if not files:
                continue
            picks = {files[0], files[len(files) // 2], files[-1]}
            for fn in sorted(picks):
                p = os.path.join(mdir, fn)
                try:
                    with gzip.open(p, "rt", encoding="utf-8") as fh:
                        data = json.load(fh)
                except Exception as e:  # noqa: BLE001
                    inv.setdefault("parse_errors", []).append(f"{p}: {e}")
                    continue
                sampled += 1
                for sym in data.get("data", {}).get("symbols", []):
                    for st in sym.get("strikes", []):
                        nt = st.get("nodeType", "?")
                        census[nt] = census.get(nt, 0) + 1
    inv["node_type_census_sampled_strikes"] = census
    inv["node_type_sample_files_parsed"] = sampled

    with open(out_path("re_inventory.json"), "w", encoding="utf-8") as fh:
        json.dump(inv, fh, indent=1)
    log(f"re_inventory.json written ({len(inv['days'])} days)")
    for lay, st in inv["layers"].items():
        log(f"  {lay}: {st['files']} files / {st['days']} days "
            f"({st['first_day']} .. {st['last_day']})")
    log(f"  node types (sampled): {census}")


def read_jsonl_manifest(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# ------------------------------------------------------------- scan-matrix

def cmd_scan_matrix(args) -> None:
    raw = args.raw_root
    cache = out_path("matrix_scan.jsonl")
    done: set[str] = set()
    if os.path.exists(cache) and not args.restart:
        for row in read_jsonl(cache):
            done.add(row["file"])
    log(f"scan-matrix: {len(done)} files already in cache")

    files = list_capture_files(os.path.join(raw, "matrix", "gamma"))
    todo = [f for f in files if f not in done]
    log(f"scan-matrix: {len(todo)} gamma matrix files to parse")
    t0 = time.time()
    n = 0
    with open(cache, "a", encoding="utf-8") as fh:
        for path in todo:
            rec = scan_one_matrix(path)
            fh.write(json.dumps(rec) + "\n")
            n += 1
            if n % 100 == 0:
                rate = n / (time.time() - t0)
                log(f"scan-matrix: {n}/{len(todo)} done ({rate:.1f} files/s)")
    log(f"scan-matrix: finished {n} files -> {cache}")


def scan_one_matrix(path: str) -> dict:
    """Parse one matrix capture -> compact per-snapshot parity record.

    Skylit node values kept: per symbol the total-grid king (argmax |value|),
    the per-expiry column kings (matrix[i] row = strike i, one value per
    expiry), node-type census and spot. Full grid stays on X10 for re-reads.
    """
    rel = os.path.relpath(path, RAW_ROOT)
    day = os.path.basename(os.path.dirname(path))
    t = os.path.basename(path)[:6]
    rec: dict = {"file": rel, "day": day, "t": t, "symbols": {}}
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as e:  # noqa: BLE001
        rec["error"] = str(e)
        return rec
    meta = data.get("meta", {})
    rec["metric"] = meta.get("metric")
    for sym in data.get("data", {}).get("symbols", []):
        name = sym.get("symbol")
        strikes = sym.get("strikes", [])
        expirations = sym.get("expirations", [])
        grid = sym.get("matrix", [])
        node_counts: dict[str, int] = {}
        king = None
        for st in strikes:
            nt = st.get("nodeType", "?")
            node_counts[nt] = node_counts.get(nt, 0) + 1
            v = st.get("value", 0) or 0
            if king is None or abs(v) > abs(king.get("value", 0)):
                king = {"strike": st.get("strike"), "value": v, "nodeType": nt}
        col_kings = []
        if grid and expirations:
            for j, exp in enumerate(expirations):
                best = None
                for i, row in enumerate(grid):
                    v = row[j] if j < len(row) else 0
                    v = v or 0
                    if best is None or abs(v) > abs(best[1]):
                        best = (strikes[i]["strike"] if i < len(strikes) else None, v)
                col_kings.append(
                    {"expiry": exp, "strike": best[0], "value": best[1]}
                    if best and best[1]
                    else {"expiry": exp, "strike": None, "value": 0}
                )
        rec["symbols"][name] = {
            "asOf": sym.get("asOf"),
            "spot": sym.get("spot"),
            "n_strikes": len(strikes),
            "n_expiries": len(expirations),
            "node_counts": node_counts,
            "king": king,
            "column_kings": col_kings,
        }
    return rec


# ----------------------------------------------------------------- uw-check

def cmd_uw_check(args) -> None:
    url, key = uw_env()
    days = dataset_days(args.raw_root)
    cov: dict = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "supabase_url": url,
        "table": "gamma_data_v2",
        "access": "read-only GET/HEAD via PostgREST",
        "days": {},
    }

    # input-column completeness on one fresh row (filter needed: unfiltered
    # scans on the partitioned parent hit the PostgREST statement timeout)
    fresh = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    row, _ = uw_get(url, key, "gamma_data_v2",
                    {"select": ",".join(UW_INPUT_COLUMNS), "limit": "1",
                     "ticker": "eq.SPX",
                     "timestamp": f"gte.{fresh.strftime('%Y-%m-%d')}T00:00:00Z"})
    cov["input_columns_present"] = sorted(row[0].keys()) if row else []
    cov["input_columns_missing"] = (
        [c for c in UW_INPUT_COLUMNS if c not in (row[0] if row else {})]
    )
    log(f"uw-check: input columns missing: {cov['input_columns_missing'] or 'none'}")

    for day in days:
        d0 = f"{day}T00:00:00Z"
        d1 = f"{day}T23:59:59Z"
        r0 = f"{day}T{RTH_START}Z"
        r1 = f"{day}T{RTH_END}Z"
        entry: dict = {}
        for tk in SYMBOLS:
            nd = dt.date.fromisoformat(day) + dt.timedelta(days=1)
            # PostgREST needs repeated keys -> build query manually
            q = f"select=ticker&ticker=eq.{tk}&timestamp=gte.{d0}&timestamp=lt.{nd}T00:00:00Z"
            _, cr_day = uw_head(url, key, "gamma_data_v2", q)
            q_rth = (f"select=ticker&ticker=eq.{tk}"
                     f"&timestamp=gte.{r0}&timestamp=lt.{r1}")
            _, cr_rth = uw_head(url, key, "gamma_data_v2", q_rth)
            # snapshot cadence probe: pick a strike present that day, front expiry
            probe = uw_probe_cadence(url, key, tk, day)
            entry[tk] = {
                "rows_full_day": count_from_range(cr_day),
                "rows_rth": count_from_range(cr_rth),
                "probe": probe,
            }
            log(f"uw-check: {day} {tk} day={entry[tk]['rows_full_day']} "
                f"rth={entry[tk]['rows_rth']} probe_ts={probe.get('n_timestamps')}")
        cov["days"][day] = entry

    with open(out_path("uw_coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(cov, fh, indent=1)
    log("uw_coverage.json written")


def uw_head(url: str, key: str, table: str, query: str) -> tuple[None, str]:
    req = urllib.request.Request(
        f"{url}/rest/v1/{table}?{query}",
        method="HEAD",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Prefer": "count=exact"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return None, resp.headers.get("Content-Range", "*/*")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{table}?{query}: HTTP {e.code}")


def uw_query(url: str, key: str, table: str, query: str, retries: int = 2) -> list:
    """READ-ONLY raw-query GET (repeated params allowed), retry on 5xx."""
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            f"{url}/rest/v1/{table}?{query}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500:
                raise
            time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def uw_probe_cadence(url: str, key: str, ticker: str, day: str) -> dict:
    """Snapshot timestamps near ATM x front expiry on one day.

    A thin far-OTM/LEAPS strike appears only in a few snapshots, so the probe
    snaps to the row's own spot_price and probes the nearest strike grid
    points until one has rows.
    """
    nd = dt.date.fromisoformat(day) + dt.timedelta(days=1)
    q_base = (f"ticker=eq.{ticker}&timestamp=gte.{day}T00:00:00Z"
              f"&timestamp=lt.{nd}T00:00:00Z")
    try:
        return _probe_body(url, key, ticker, day, nd, q_base)
    except Exception as e:  # noqa: BLE001 — record, never crash the sweep
        return {"n_timestamps": 0, "error": f"{type(e).__name__}: {e}"}


def _probe_body(url: str, key: str, ticker: str, day: str, nd, q_base: str) -> dict:
    # 0) spot for the day
    rows = uw_query(url, key, "gamma_data_v2",
                    f"select=spot_price&limit=1&{q_base}")
    if not rows or rows[0].get("spot_price") is None:
        return {"n_timestamps": 0, "note": "no rows that day"}
    spot = float(rows[0]["spot_price"])
    # short windows — day-wide scans on the partitioned parent hit the
    # PostgREST statement timeout
    windows = [(f"{day}T13:30:00Z", f"{day}T15:30:00Z"),
               (f"{day}T15:30:00Z", f"{day}T18:00:00Z"),
               (f"{day}T18:00:00Z", f"{day}T20:00:00Z"),
               (f"{day}T06:00:00Z", f"{day}T08:00:00Z")]
    # 1) pick a probe strike x expiry from real sampled rows near spot.
    #    Strike-grid guessing with per-candidate lookups is too slow (each
    #    miss scans a window and can hit the PostgREST statement timeout).
    sample = []
    for w0, w1 in windows:
        sample += uw_query(url, key, "gamma_data_v2",
                           f"select=strike,expiry_date&timestamp=gte.{w0}"
                           f"&timestamp=lt.{w1}&limit=20")
        if sample:
            break
    if not sample:
        return {"n_timestamps": 0, "note": f"no sampled rows near spot {spot}"}
    best = min(sample, key=lambda r: abs(float(r["strike"]) - spot))
    strike, expiry = best["strike"], best["expiry_date"]
    # 2) pull its RTH timestamps (one row per snapshot for a fixed strike/expiry)
    rows = []
    for w0, w1 in windows:
        rows += uw_query(url, key, "gamma_data_v2",
                         f"select=timestamp&strike=eq.{strike}"
                         f"&expiry_date=eq.{expiry}"
                         f"&timestamp=gte.{w0}&timestamp=lt.{w1}"
                         f"&order=timestamp&limit=5000")
    ts = sorted({r["timestamp"] for r in rows})
    deltas = [
        (dt.datetime.fromisoformat(ts[i + 1]) - dt.datetime.fromisoformat(ts[i])
         ).total_seconds()
        for i in range(len(ts) - 1)
    ]
    med = sorted(deltas)[len(deltas) // 2] if deltas else None
    return {
        "spot": spot,
        "probe_strike": strike, "probe_expiry": expiry,
        "n_timestamps": len(ts),
        "first_ts": ts[0] if ts else None,
        "last_ts": ts[-1] if ts else None,
        "median_cadence_s": med,
        "timestamps": [t.replace("+00:00", "Z") for t in ts],
    }


def dataset_days(raw_root: str) -> list[str]:
    inv_path = out_path("re_inventory.json")
    if os.path.exists(inv_path):
        with open(inv_path, encoding="utf-8") as fh:
            return sorted(json.load(fh)["days"].keys())
    mdir = os.path.join(raw_root, "matrix", "gamma")
    return sorted(d for d in os.listdir(mdir)
                  if os.path.isdir(os.path.join(mdir, d)) and not d.startswith("."))


# ------------------------------------------------------------------- frames

def cmd_frames(args) -> None:
    scan_path = out_path("matrix_scan.jsonl")
    uw_path = out_path("uw_coverage.json")
    if not os.path.exists(scan_path):
        sys.exit("run scan-matrix first")
    if not os.path.exists(uw_path):
        sys.exit("run uw-check first")

    scans = list(read_jsonl(scan_path))
    with open(uw_path, encoding="utf-8") as fh:
        uw = json.load(fh)

    by_day: dict[str, list] = {}
    for rec in scans:
        if "error" in rec:
            continue
        by_day.setdefault(rec["day"], []).append(rec)

    frame_list = []
    avail_rows = []
    for day in sorted(by_day):
        recs = sorted(by_day[day], key=lambda r: r["t"])
        re_ts = [f"{day}T{r['t'][:2]}:{r['t'][2:4]}:{r['t'][4:6]}Z" for r in recs]
        uw_day = uw["days"].get(day, {})
        # UW availability: any ticker with rows that day
        uw_rows_rth = sum(tk.get("rows_rth", 0) for tk in uw_day.values())
        uw_rows_day = sum(tk.get("rows_full_day", 0) for tk in uw_day.values())
        # alignment: RE snapshot ts vs UW probe ts (union of all ticker probes)
        uw_ts = sorted({
            t
            for tk in uw_day.values()
            for t in tk.get("probe", {}).get("timestamps", [])
        })
        matched, deltas = align_timestamps(re_ts, uw_ts, tol_s=90)
        # king census across the day (from scan records)
        kings = {}
        for r in recs:
            for sym, s in r["symbols"].items():
                if s.get("king") and s["king"].get("nodeType") == "king":
                    k = kings.setdefault(sym, {"n": 0, "strikes": set()})
                    k["n"] += 1
                    k["strikes"].add(s["king"]["strike"])
        king_summary = {
            s: {"snapshots_with_king": v["n"],
                "distinct_king_strikes": sorted(x for x in v["strikes"]
                                                if x is not None)}
            for s, v in kings.items()
        }
        usable = (uw_rows_rth > 0 and len(re_ts) > 0 and len(matched) > 0)
        frame_list.append({
            "day": day,
            "re_snapshots": len(re_ts),
            "re_first": re_ts[0] if re_ts else None,
            "re_last": re_ts[-1] if re_ts else None,
            "uw_rows_rth": uw_rows_rth,
            "uw_rows_full_day": uw_rows_day,
            "uw_probe_timestamps": len(uw_ts),
            "aligned_pairs_tol90s": len(matched),
            "alignment_median_delta_s": deltas[len(deltas) // 2] if deltas else None,
            "alignment_max_delta_s": max(deltas) if deltas else None,
            "king_summary": king_summary,
            "usable_for_king_exact": usable,
        })
        avail_rows.append(
            f"| {day} | {len(re_ts)} | {re_ts[0][11:19] if re_ts else '-'} | "
            f"{re_ts[-1][11:19] if re_ts else '-'} | {uw_rows_rth} | "
            f"{len(uw_ts)} | {len(matched)} | "
            f"{deltas[len(deltas) // 2] if deltas else '-'} | "
            f"{'YES' if usable else 'NO'} |"
        )

    usable_days = [f for f in frame_list if f["usable_for_king_exact"]]
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tolerance_s": 90,
        "n_session_days_re": len(frame_list),
        "n_usable_king_exact": len(usable_days),
        "frame_list": frame_list,
    }
    with open(out_path("session_day_frames.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)

    md = [
        "# Per-day availability + alignment (auto-generated — do not edit by hand)",
        "",
        "RE snapshots = parsed matrix captures (Skylit node values, incl. "
        "nodeType). UW rows = `gamma_data_v2` rows in RTH 13:30-20:00Z "
        "(read-only). Aligned = RE snapshot with UW probe timestamp within "
        "90 s.",
        "",
        "| day | RE snaps | RE first | RE last | UW rows RTH | UW probe ts "
        "| aligned pairs | median dt (s) | usable |",
        "|---|---|---|---|---|---|---|---|---|",
        *avail_rows,
        "",
        f"Usable session-days for king-exact comparison: "
        f"**{len(usable_days)}/{len(frame_list)}**",
    ]
    with open(out_path("availability.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    log(f"session_day_frames.json + availability.md written: "
        f"{len(usable_days)}/{len(frame_list)} usable days")
    print("\n".join(md))


def align_timestamps(re_ts: list[str], uw_ts: list[str], tol_s: float = 90):
    """Nearest-neighbour alignment; returns (matched_pairs, |delta|s list)."""
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    def norm(t: str) -> dt.datetime:
        return dt.datetime.strptime(t.replace("Z", "+0000").replace("+00:00", "+0000"),
                                    fmt.replace("%z", "%z")) if False else \
            dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    uw_dt = sorted(norm(t) for t in uw_ts)
    matched = []
    deltas = []
    for t in re_ts:
        rt = norm(t)
        lo, hi = 0, len(uw_dt)
        while lo < hi:
            mid = (lo + hi) // 2
            if uw_dt[mid] < rt:
                lo = mid + 1
            else:
                hi = mid
        cands = [uw_dt[j] for j in (lo - 1, lo) if 0 <= j < len(uw_dt)]
        if not cands:
            continue
        best = min(cands, key=lambda u: abs((u - rt).total_seconds()))
        d = abs((best - rt).total_seconds())
        if d <= tol_s:
            matched.append((t, best.isoformat()))
            deltas.append(d)
    return matched, deltas


# ----------------------------------------------------------------- load-day

def cmd_load_day(args) -> None:
    """Loader used by later E0 cards: one aligned frame pair (Skylit + UW)."""
    url, key = uw_env()
    day = args.day
    t = args.time  # HHMMSS
    raw = args.raw_root
    path = os.path.join(raw, "matrix", "gamma", day, f"{t}.json.gz")
    if not os.path.exists(path):
        sys.exit(f"no RE capture at {path}")
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        skylit = json.load(fh)
    ts_iso = f"{day}T{t[:2]}:{t[2:4]}:{t[4:6]}Z"
    nd = parse_day(day) + dt.timedelta(days=1)
    ts_next = f"{nd}T00:00:00Z"
    q = (f"select={urllib.parse.quote(','.join(UW_INPUT_COLUMNS))}"
         f"&ticker=eq.{args.symbol}&order=timestamp&limit=20000"
         f"&timestamp=gte.{ts_iso}&timestamp=lt.{ts_next}")
    req = urllib.request.Request(
        f"{url}/rest/v1/gamma_data_v2?{q}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        uw_rows = json.loads(resp.read().decode("utf-8"))
    print(json.dumps({
        "skylit_asOf": [s.get("asOf") for s in skylit["data"]["symbols"]],
        "skylit_symbol": args.symbol,
        "skylit_frame": next(
            (s for s in skylit["data"]["symbols"] if s["symbol"] == args.symbol),
            None,
        ),
        "uw_rows_after_ts": len(uw_rows),
        "uw_first_rows": uw_rows[:5],
    }, indent=1)[:8000])


# --------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-root", default=RAW_ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory")
    p = sub.add_parser("scan-matrix")
    p.add_argument("--restart", action="store_true")
    sub.add_parser("uw-check")
    sub.add_parser("frames")
    sub.add_parser("all")
    p = sub.add_parser("load-day")
    p.add_argument("--day", required=True)
    p.add_argument("--time", required=True)
    p.add_argument("--symbol", default="SPX")
    args = ap.parse_args()

    if args.cmd in ("inventory", "all"):
        cmd_inventory(args)
    if args.cmd in ("scan-matrix", "all"):
        cmd_scan_matrix(args)
    if args.cmd in ("uw-check", "all"):
        cmd_uw_check(args)
    if args.cmd in ("frames", "all"):
        cmd_frames(args)
    if args.cmd == "load-day":
        cmd_load_day(args)


if __name__ == "__main__":
    main()
