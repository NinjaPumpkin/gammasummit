#!/usr/bin/env python3
"""skylit_api_archive.py — Skylit API max-extraction archive client (D2, t_5ac5cb30).

Owner directive 2026-10-01: extract everything valuable from the Skylit API
before the subscription ends ~Nov 2026 and archive it on the X10 Pro disk.
Owner rule 2026-10-02 (RATE-LIMIT DISCIPLINE, hard): pacing <= 50% of the
documented 120 rpm limit with jitter; exponential backoff + cooldown on ANY
429/403/rate signal; stop-on-first-sign, never retry-storm; daily request caps
tracked in the manifest; every pull credit-budgeted. A rate-limit hit = card
incident comment + pause.

Costs (per card; measured deltas recorded per call):
  /v1/heatmap          1 cr per call
  /v1/historical       5 cr per call   (matrix frames, fit-target data)
  /v1/historical/range 25 cr per 15-min window, <= 5 symbols (dense 1s frames)
Reserve floor: STOP at 5,000 credits remaining.

Storage: /Volumes/X10 Pro/gammasummit/skylit_api/ when the volume responds,
else local staging data/skylit_api-staging/ (never lose pulls to a wedged
disk) — `mover` rsyncs staging to X10 once healthy. Layout (Hive-partitioned):

  raw/endpoint=<ep>/symbol=<SYM>/date=<YYYY-MM-DD>/<hhmmss>_<pullid>.json.gz
  parquet/endpoint=<ep>/symbol=<SYM>/date=<YYYY-MM-DD>/<hhmmss>_<pullid>.parquet
  pull_manifest.jsonl    per pull: ts, endpoint, params, credits, rows, sha256
  credit_ledger.jsonl    per call: ts, endpoint, spent, remaining, source
  state/daily_caps.json  running daily request/credit totals

Commands (default dry-run; --execute to spend credits):

  python3 scripts/skylit_api_archive.py plan      [--batch all|probe|historical|range|heatmap]
  python3 scripts/skylit_api_archive.py pull      [--batch ...] [--execute]
                          [--max-credits N] [--max-requests N] [--rpm N]
  python3 scripts/skylit_api_archive.py mover     [--execute]
  python3 scripts/skylit_api_archive.py coverage  [--execute]

Idempotent: a pull whose pull_id is already in the manifest with a matching
file + sha256 is skipped. All pulls read-only against the API. The API key is
never written to the archive. Secrets: GAMMASUMMIT_SKYLIT_API_KEY (legacy
SKYLIT_API_KEY accepted) from env / gammasummit/.env / ~/.hermes/.env.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.skylit.ai"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
X10_ROOT = "/Volumes/X10 Pro/gammasummit/skylit_api"
STAGING_ROOT = os.path.join(REPO, "data", "skylit_api-staging")
COVERAGE_DOC = os.path.join(REPO, "docs", "data", "skylit-api-archive.md")

COST_TABLE = {"heatmap": 1, "historical": 5, "historical/range": 25}
RESERVE_FLOOR = 5000           # STOP when credits_remaining <= this
DEFAULT_RPM = 50               # <= 50% of the 120 rpm limit (owner rule)
DEFAULT_MAX_CREDITS = 12000    # per run
DEFAULT_MAX_REQUESTS = 3000    # per run
DEFAULT_DAILY_MAX_REQUESTS = 6000
DEFAULT_DAILY_MAX_CREDITS = 40000
MAX_SYMBOLS_PER_CALL = 5       # range endpoint prices <= 5 symbols
SWEEP_DEPTH_FLOOR = "2023-03-28"   # server-stated history floor (D2c bisect
                                   # confirmed; was assumed 2024-03-08 in D2b)
RTH_START = (9, 30)           # 09:30 America/New_York, DST-aware (was a
RTH_END = (16, 0)             # hardcoded 13:30-20:00Z EDT window; EST days
                              # e.g. 2024-03-04..08 need 14:30-21:00Z)

CALIB_SYMBOLS = ["SPY", "SPX", "QQQ", "IWM"]
# Wide-coverage tiers are PINNED so pull_ids stay stable across runs (real
# t012 order differs from the fallback order the 2026-10-02 sweep was chunked
# with; re-chunking would silently re-buy the same data).
WIDE_GROUPS_60S = [
    ["SPY", "SPX", "QQQ", "IWM", "AAPL"],
    ["AMD", "NVDA", "TSLA", "META", "MSFT"],
    ["GOOGL", "GOOG", "AMZN", "NFLX", "COIN"],
    ["PLTR", "INTC", "MU", "AVGO", "SMCI"],
]  # frozen 2026-10-02; 60s cadence open+close hours
WIDE_EXT_STEP_S = 300          # extended universe sampled at 5-min cadence
TIER1_SET = {s for g in WIDE_GROUPS_60S for s in g}
# t012 first-54 approximation (real list = /Volumes/X10 Pro/leandata/t012_tickers.txt,
# loaded read-only when X10 responds; this fallback keeps pulls unblocked).
LIQUID_FALLBACK = [
    "SPY", "SPX", "QQQ", "IWM", "AAPL", "AMD", "NVDA", "TSLA", "META",
    "MSFT", "GOOGL", "GOOG", "AMZN", "NFLX", "COIN", "PLTR", "INTC", "MU",
    "AVGO", "SMCI",
]
TIER_A_FALLBACK = ["2026-09-28", "2026-09-29", "2026-09-30"]
P0_FRAMES = os.path.join(REPO, "data", "p0", "session_day_frames.json")


# ---------------------------------------------------------------- secrets

def get_key():
    k = (os.environ.get("GAMMASUMMIT_SKYLIT_API_KEY", "")
         or os.environ.get("SKYLIT_API_KEY", ""))
    if not k:
        for p in (os.path.join(REPO, ".env"), os.path.expanduser("~/.hermes/.env")):
            try:
                for line in open(p):
                    line = line.strip()
                    if (line.startswith("SKYLIT_API_KEY=")
                            or line.startswith("GAMMASUMMIT_SKYLIT_API_KEY=")):
                        k = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if k:
                            os.environ["GAMMASUMMIT_SKYLIT_API_KEY"] = k
                            return k
            except OSError:
                pass
    return k


# ---------------------------------------------------------------- roots

def x10_healthy(timeout_s=8):
    """True only when the X10 volume answers a write probe in time.

    Non-blocking by design: the probe runs detached and is polled with a
    deadline; a wedged exFAT/FSKit stack leaves `touch` in uninterruptible
    I/O, so we must never join the probe process (it would hang us too).
    """
    probe = "/Volumes/X10 Pro/.gammasummit_write_probe"
    try:
        p = subprocess.Popen(["touch", probe],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception:
        return False
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if p.poll() is not None:
            ok = (p.returncode == 0)
            if ok:
                try:
                    subprocess.Popen(["rm", "-f", probe],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                except Exception:
                    pass
            return ok
        time.sleep(0.25)
    try:
        p.kill()          # may not die if stuck in D-state; abandon it
    except Exception:
        pass
    return False


def out_root():
    return X10_ROOT if x10_healthy() else STAGING_ROOT


# ---------------------------------------------------------------- universe

def tier_a_days():
    try:
        d = json.load(open(P0_FRAMES))
        days = [f["session_day"] for f in d["frames"]
                if f.get("status", "").startswith("aligned")]
        if days:
            return sorted(set(days))
    except Exception:
        pass
    return list(TIER_A_FALLBACK)


def _guarded(fn, timeout_s=10):
    """Run fn in a daemon thread with a deadline; None if it wedges.

    A thread stuck in uninterruptible FS I/O is abandoned, never joined."""
    import threading
    box = {}
    def _run():
        try:
            box["v"] = fn()
        except Exception:
            box["v"] = None
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout_s)
    return box.get("v")


def liquid_symbols():
    def _read():
        txt = open("/Volumes/X10 Pro/leandata/t012_tickers.txt").read().strip()
        names = [t.strip().upper() for t in txt.split(",") if t.strip()]
        return names if len(names) >= 20 else None
    if x10_healthy():
        names = _guarded(_read, 10)
        if names:
            return names[:54], "t012_tickers.txt[:54]"
    return list(LIQUID_FALLBACK), "fallback_default"


# ---------------------------------------------------------------- http

class RateLimitHit(Exception):
    pass


def api_get(path, params, key, rpm=DEFAULT_RPM):
    """One GET with rate discipline. Returns (payload, headers_lower, spent_source).

    Stops the whole run on the first 429/403 (owner rule: stop-on-first-sign,
    never retry-storm): one cooldown + exponential backoff is allowed, a second
    rate signal aborts via RateLimitHit.
    """
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Authorization": f"Bearer {key}", "Accept-Encoding": "gzip"}
    rate_seen = 0
    for attempt in range(3):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                hdrs = {k.lower(): v for k, v in r.headers.items()}
                return json.loads(raw or b"{}"), hdrs
        except urllib.error.HTTPError as e:
            if e.code in (429, 403):
                rate_seen += 1
                print(f"  RATE SIGNAL HTTP {e.code} on {path} "
                      f"(hit {rate_seen}) — cooldown", flush=True)
                if rate_seen >= 2:
                    raise RateLimitHit(f"HTTP {e.code} twice on {path}")
                wait = min(120.0, 30.0 * (2 ** attempt)) + random.random() * 5
                time.sleep(wait)          # exponential backoff + cooldown
                continue
            if e.code in (500, 502, 503, 504) and attempt < 2:
                wait = min(60.0, 5.0 * (2 ** attempt)) + random.random() * 2
                print(f"  HTTP {e.code}, retry in {wait:.1f}s", flush=True)
                time.sleep(wait)
                continue
            body = e.read()
            if body[:2] == b"\x1f\x8b":
                try:
                    body = gzip.decompress(body)
                except OSError:
                    pass
            raise RuntimeError(f"fatal HTTP {e.code}: "
                               f"{body.decode(errors='replace')[:300]}")
        except (TimeoutError, OSError) as e:
            if attempt < 2:
                time.sleep(min(60.0, 5.0 * (2 ** attempt)) + random.random() * 2)
                continue
            raise
    raise RuntimeError(f"gave up on {path}")


def pace_sleep(rpm):
    base = 60.0 / max(1, rpm)
    time.sleep(base * (0.9 + random.random() * 0.2))   # jitter


def credits_remaining(hdrs):
    for k, v in hdrs.items():
        if k in ("x-credits-remaining", "x-credit-remaining", "credits-remaining"):
            try:
                return int(float(v))
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------- manifest

def manifest_path(root):
    return os.path.join(root, "pull_manifest.jsonl")


def ledger_path(root):
    return os.path.join(root, "credit_ledger.jsonl")


def daily_caps_path(root):
    return os.path.join(root, "state", "daily_caps.json")


def load_manifest(root):
    p = manifest_path(root)
    out = {}
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                out[r["pull_id"]] = r
            except Exception:
                continue
    return out


def append_jsonl(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def load_daily_caps(root, day):
    p = daily_caps_path(root)
    d = {}
    if os.path.exists(p):
        try:
            d = json.load(open(p))
        except Exception:
            d = {}
    return d.get(day, {"requests": 0, "credits": 0})


def save_daily_caps(root, day, rec):
    p = daily_caps_path(root)
    d = {}
    if os.path.exists(p):
        try:
            d = json.load(open(p))
        except Exception:
            d = {}
    d[day] = rec
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, p)


def pull_id_for(endpoint, params, slot=None):
    # NOTE: the slot key is omitted when absent — the hash input must stay
    # byte-identical to pre-slot ids or every archived pull would be re-bought.
    d = {"e": endpoint, "p": params}
    if slot is not None:
        d["s"] = slot
    sig = json.dumps(d, sort_keys=True)
    return hashlib.sha1(sig.encode()).hexdigest()[:12]


# ---------------------------------------------------------------- plan

def utc_ticks(date_str, step_s, window=None):
    """RTH instants for one session day, DST-aware (America/New_York), as
    UTC. EDT days are byte-identical to the old hardcoded 13:30-20:00Z
    window, so archived pull_ids never shift; EST days now map to
    14:30-21:00Z instead of a wrong 1-hour-offset window."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    d = datetime.fromisoformat(date_str).replace(tzinfo=et)
    start = d.replace(hour=RTH_START[0], minute=RTH_START[1],
                      second=0, microsecond=0)
    end = d.replace(hour=RTH_END[0], minute=RTH_END[1],
                    second=0, microsecond=0)
    if window == "open":
        end = start + timedelta(hours=1)
    elif window == "close":
        start = end - timedelta(hours=1)
    out, t = [], start
    while t < end:
        out.append(t.astimezone(timezone.utc))
        t += timedelta(seconds=step_s)
    return out


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def build_plan(batch, days, liq, liq_src, metrics, sweep_days=None):
    """Return ordered list of pull specs (dicts). No API calls, no credits.

    Idempotency: historical/range pull_ids key on params (which carry the
    instant), heatmap pull_ids key on params + slot (live snapshots get fresh
    ids per cadence slot, so re-runs capture new snapshots instead of being
    skipped forever)."""
    specs = []

    def add(ep, params, symbol_key, date_key, note, slot=None, tolerate_4xx=False):
        specs.append({
            "endpoint": ep, "params": params, "batch": batch,
            "symbol": symbol_key, "date": date_key, "note": note,
            "slot": slot, "tolerate_4xx": tolerate_4xx,
            "pull_id": pull_id_for(ep, params, slot),
            "est_credits": COST_TABLE.get(ep, 1),
        })

    def hist_params(symbols, ts, metric):
        return {"symbols": ",".join(symbols), "at": ts, "layout": "matrix",
                "metric": metric, "maxStrikes": "all", "maxExpirations": "all"}

    # extended-universe groups: t012 first-54 minus the pinned tier-1 set,
    # sorted within groups for stable pull_ids across runs
    ext_names = sorted(s for s in liq if s not in TIER1_SET)
    ext_groups = list(chunks(ext_names, MAX_SYMBOLS_PER_CALL))

    if batch in ("probe", "all"):
        now = datetime.now(timezone.utc)
        add("heatmap", {"symbols": ",".join(CALIB_SYMBOLS)},
            "MULTI", now.strftime("%Y-%m-%d"), "probe: live heatmap snapshot")
        probe_day = days[-1]
        t = utc_ticks(probe_day, 300)[2]      # mid-morning instant
        add("historical", hist_params(CALIB_SYMBOLS,
                                      t.strftime("%Y-%m-%dT%H:%M:%SZ"), "gamma"),
            "MULTI", probe_day, "probe: historical matrix frame")
        w0 = utc_ticks(probe_day, 900)[4]
        w1 = w0 + timedelta(minutes=15)
        add("historical/range", {"symbols": ",".join(CALIB_SYMBOLS),
                                 "from": w0.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 "to": w1.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 "metric": "gamma",
                                 "maxStrikes": "all", "maxExpirations": "all"},
            "MULTI", probe_day, "probe: dense 1s range window")
        # history-depth probes: how far back does /v1/historical reach?
        # (2026-10-02 D2b: ladder extended past 2026-06-15 toward 2025;
        #  cluster days double as sweep pull_ids — probing then sweeping
        #  never double-buys. 2026-10-02 D2c: bisect 2023-06/09 added to
        #  narrow the 2023-03 → 2024-03 boundary)
        for depth_day in ("2026-09-15", "2026-08-17", "2026-06-15",
                          "2026-04-15", "2026-02-16", "2025-12-15",
                          "2025-08-17", "2025-04-15", "2025-01-15",
                          "2024-08-05", "2024-03-08", "2023-09-13",
                          "2023-06-13", "2023-03-28", "2023-03-13",
                          "2022-05-12"):
            add("historical",
                hist_params(CALIB_SYMBOLS, f"{depth_day}T14:00:00Z", "gamma"),
                "MULTI", depth_day,
                f"probe: history depth {depth_day}", tolerate_4xx=True)

    if batch in ("historical", "all"):
        # core: full RTH 60s cadence, calibration quartet, all Tier-A days
        for day in days:
            for t in utc_ticks(day, 60):
                ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
                for metric in metrics:
                    add("historical", hist_params(CALIB_SYMBOLS, ts, metric),
                        "MULTI", day,
                        f"historical core 60s RTH metric={metric}")
        # wide tier-1: open+close first/last hour at 60s, pinned 20-name groups
        for day in days:
            for win in ("open", "close"):
                for t in utc_ticks(day, 60, window=win):
                    ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
                    for grp in WIDE_GROUPS_60S:
                        for metric in metrics:
                            add("historical", hist_params(grp, ts, metric),
                                "+".join(grp), day,
                                f"historical wide60 {win} metric={metric}")
        # wide extended: remaining t012 names, open+close hours at 300s
        for day in days:
            for win in ("open", "close"):
                for t in utc_ticks(day, WIDE_EXT_STEP_S, window=win):
                    ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
                    for grp in ext_groups:
                        for metric in metrics:
                            add("historical", hist_params(grp, ts, metric),
                                "+".join(grp), day,
                                f"historical wide-ext {win} metric={metric}")

    if batch in ("range", "all"):
        # dense 1s frames: 15-min windows over full RTH, calibration quartet.
        # DST-aware like utc_ticks: RTH wall-clock in America/New_York, the
        # `from`/`to` params carry UTC instants (EDT days byte-identical to
        # the old hardcoded window, so archived pull_ids never shift).
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        for day in days:
            t = datetime.fromisoformat(day).replace(tzinfo=et).replace(
                hour=RTH_START[0], minute=RTH_START[1], second=0, microsecond=0)
            end = t.replace(hour=RTH_END[0], minute=RTH_END[1])
            while t < end:
                w1 = min(t + timedelta(minutes=15), end)
                add("historical/range",
                    {"symbols": ",".join(CALIB_SYMBOLS),
                     "from": t.astimezone(timezone.utc).strftime(
                         "%Y-%m-%dT%H:%M:%SZ"),
                     "to": w1.astimezone(timezone.utc).strftime(
                         "%Y-%m-%dT%H:%M:%SZ"),
                     "metric": "gamma",
                     "maxStrikes": "all", "maxExpirations": "all"},
                    "MULTI", day, "range dense 1s 15-min window")
                t = w1

    if batch in ("heatmap", "all"):
        # calibration cadence burst: 12 slots at 60s for tier-1 + extended
        # groups (nodeType/value/velocityPct calibration for every name)
        base = datetime.now(timezone.utc).replace(microsecond=0)
        groups = WIDE_GROUPS_60S + ext_groups
        for i in range(12):
            slot = (base + timedelta(seconds=60 * i)).isoformat()
            for grp in groups:
                add("heatmap", {"symbols": ",".join(grp)},
                    "+".join(grp),
                    datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    f"heatmap cadence burst slot {i + 1}/12", slot=slot)
    if batch == "sweep":
        # big-move-day history sweep (D2b, t_a5430ff9): core profile — full
        # RTH 60s cadence, calibration quartet — on ranked high-range days
        # (data/d2b/bigmove_day_rank.csv). 5 cr/call; pull_ids are byte-
        # identical to core pulls, so overlap with Tier-A days is never
        # re-bought.
        for day in (sweep_days or []):
            for t in utc_ticks(day, 60):
                ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
                for metric in metrics:
                    add("historical", hist_params(CALIB_SYMBOLS, ts, metric),
                        "MULTI", day,
                        f"big-move sweep core 60s RTH metric={metric}")
    return specs


# ---------------------------------------------------------------- write

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def response_rows(endpoint, payload):
    """Flatten a response into parquet-able long-format records.

    heatmap:   one row per strike (value + nodeType + velocityPct).
    historical: one row per (strike, expiry) matrix cell + strike-level
                value/nodeType — the per-cell fit target.
    historical/range: one row per (frame, strike) 1s value."""
    rows = []
    try:
        data = payload.get("data", {})
        if endpoint == "heatmap":
            for s in (data.get("symbols") or []):
                for st in (s.get("strikes") or []):
                    rows.append({"symbol": s.get("symbol"),
                                 "asOf": s.get("asOf"), "spot": s.get("spot"),
                                 **{k: v for k, v in st.items()
                                    if not isinstance(v, (dict, list))}})
        elif endpoint == "historical":
            for s in (data.get("symbols") or []):
                exps = s.get("expirations") or []
                meta = {st.get("strike"): st for st in (s.get("strikes") or [])}
                matrix = s.get("matrix") or []
                for i, row in enumerate(matrix):
                    strike = (s.get("strikes") or [])[i].get("strike") \
                        if i < len(s.get("strikes") or []) else None
                    m = meta.get(strike, {})
                    for j, cell in enumerate(row):
                        rows.append({
                            "symbol": s.get("symbol"), "asOf": s.get("asOf"),
                            "spot": s.get("spot"), "strike": strike,
                            "expiry": exps[j] if j < len(exps) else None,
                            "cell_value": cell,
                            "strike_value": m.get("value"),
                            "nodeType": m.get("nodeType"),
                        })
        elif endpoint == "historical/range":
            for s in (data.get("symbols") or []):
                axes = s.get("axes") or [{}]
                strikes = axes[0].get("strikes") or []
                for fr in (s.get("frames") or []):
                    vals = fr.get("values") or []
                    asof = fr.get("asOf")
                    spot = fr.get("spot")
                    for k, v in enumerate(vals):
                        rows.append({"symbol": s.get("symbol"), "asOf": asof,
                                     "spot": spot,
                                     "strike": strikes[k] if k < len(strikes) else None,
                                     "value": v})
    except Exception:
        rows = []
    return rows


def write_pull(root, spec, payload, hdrs, spent, spent_source, remaining):
    day = spec["date"]
    ep_dir = spec["endpoint"].replace("/", "_")
    rel_dir = os.path.join("raw", f"endpoint={ep_dir}",
                           f"symbol={spec['symbol']}", f"date={day}")
    os.makedirs(os.path.join(root, rel_dir), exist_ok=True)
    hhmmss_raw = (spec["params"].get("at") or spec["params"].get("from")
                  or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        hhmmss = datetime.fromisoformat(
            str(hhmmss_raw).replace("Z", "+00:00")).strftime("%H%M%S")
    except ValueError:
        hhmmss = str(hhmmss_raw)[-6:]
    fname = f"{hhmmss}_{spec['pull_id']}.json.gz"
    raw_path = os.path.join(root, rel_dir, fname)
    with gzip.open(raw_path, "wt") as f:
        json.dump(payload, f)

    pq_path = ""
    rows = response_rows(spec["endpoint"], payload)
    if rows:
        try:
            import pandas as pd
            pq_dir = os.path.join(root, "parquet", f"endpoint={ep_dir}",
                                  f"symbol={spec['symbol']}", f"date={day}")
            os.makedirs(pq_dir, exist_ok=True)
            pq_path = os.path.join(pq_dir, fname.replace(".json.gz", ".parquet"))
            pd.DataFrame(rows).to_parquet(pq_path, index=False)
        except Exception as e:
            pq_path = ""
            print(f"  parquet mirror skipped: {e}", flush=True)

    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "pull_id": spec["pull_id"],
        "endpoint": spec["endpoint"],
        "params": spec["params"],
        "slot": spec.get("slot"),
        "batch": spec["batch"],
        "note": spec["note"],
        "raw_file": raw_path,
        "parquet_file": pq_path or None,
        "rows": len(rows),
        "sha256": sha256_file(raw_path),
        "credits_spent": spent,
        "credits_source": spent_source,
        "credits_remaining": remaining,
        "ok": True,
    }
    append_jsonl(manifest_path(root), rec)
    return rec


# ---------------------------------------------------------------- commands

def cmd_plan(args):
    days = tier_a_days()
    liq, liq_src = liquid_symbols()
    metrics = args.metrics.split(",")
    sweep_days = [d for d in (args.sweep_days or "").split(",") if d]
    batches = ["probe", "historical", "range", "heatmap"] \
        if args.batch == "all" else [args.batch]
    root = out_root()
    man = load_manifest(root)
    print(f"root: {root} (X10 {'healthy' if root == X10_ROOT else 'UNAVAILABLE -> staging'})")
    print(f"tier-A days: {days}")
    print(f"liquid names: {len(liq)} from {liq_src}")
    total_calls = total_est = skipped = 0
    for b in batches:
        specs = build_plan(b, days, liq, liq_src, metrics, sweep_days=sweep_days)
        n_skip = sum(1 for s in specs if s["pull_id"] in man)
        est = sum(s["est_credits"] for s in specs if s["pull_id"] not in man)
        print(f"  batch {b}: {len(specs)} pulls ({n_skip} already archived), "
              f"est credits {est}")
        total_calls += len(specs) - n_skip
        total_est += est
        skipped += n_skip
    print(f"TOTAL: {total_calls} new calls, est {total_est} credits "
          f"(reserve floor {RESERVE_FLOOR})")
    print("(dry-run; `pull --execute` spends credits)")
    return 0


def cmd_pull(args):
    key = get_key()
    if not key:
        raise SystemExit("SKYLIT_API_KEY not found (env / gammasummit/.env / ~/.hermes/.env)")
    days = tier_a_days()
    liq, liq_src = liquid_symbols()
    metrics = args.metrics.split(",")
    sweep_days = [d for d in (args.sweep_days or "").split(",") if d]
    batches = ["probe", "historical", "range", "heatmap"] \
        if args.batch == "all" else [args.batch]
    root = out_root()
    man = load_manifest(root)
    print(f"root: {root} | batches: {batches} | days: {days} | rpm: {args.rpm}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = load_daily_caps(root, today)
    run_req = run_credits = done = skipped = 0

    if not args.execute:
        n = sum(len(build_plan(b, days, liq, liq_src, metrics,
                               sweep_days=sweep_days)) for b in batches)
        print(f"(dry-run: {n} pulls would run; pass --execute to spend credits)")
        return 0

    # seed the credit baseline from the ledger so even the first call of this
    # run gets a measured spend (prev_remaining - after)
    prev_remaining = None
    if os.path.exists(ledger_path(root)):
        for line in open(ledger_path(root)):
            try:
                r = json.loads(line)
                if r.get("remaining") is not None:
                    prev_remaining = r["remaining"]
            except Exception:
                pass

    stop = False
    try:
        for b in batches:
            if stop:
                break
            specs = build_plan(b, days, liq, liq_src, metrics,
                               sweep_days=sweep_days)
            for spec in specs:
                if stop:
                    break
                if spec["pull_id"] in man and os.path.exists(
                        man[spec["pull_id"]].get("raw_file", "")):
                    skipped += 1
                    continue
                # budget gates BEFORE the call
                if run_req >= args.max_requests:
                    print(f"HIT per-run request cap {args.max_requests}; stopping")
                    stop = True
                    break
                if run_credits + spec["est_credits"] > args.max_credits:
                    print(f"HIT per-run credit cap {args.max_credits}; stopping")
                    stop = True
                    break
                if daily["requests"] >= DEFAULT_DAILY_MAX_REQUESTS:
                    print(f"HIT daily request cap {DEFAULT_DAILY_MAX_REQUESTS}; stopping")
                    stop = True
                    break
                if daily["credits"] + spec["est_credits"] > DEFAULT_DAILY_MAX_CREDITS:
                    print(f"HIT daily credit cap {DEFAULT_DAILY_MAX_CREDITS}; stopping")
                    stop = True
                    break
                if prev_remaining is not None and \
                        prev_remaining - spec["est_credits"] <= RESERVE_FLOOR:
                    print(f"RESERVE FLOOR {RESERVE_FLOOR} would be crossed "
                          f"(remaining {prev_remaining}); stopping ladder")
                    stop = True
                    break
                before = prev_remaining
                try:
                    payload, hdrs = api_get("/v1/" + spec["endpoint"],
                                            spec["params"], key, rpm=args.rpm)
                except RuntimeError as e:
                    if spec.get("tolerate_4xx"):
                        append_jsonl(ledger_path(root), {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "event": "probe_unavailable",
                            "detail": str(e)[:200],
                            "pull_id": spec["pull_id"]})
                        print(f"  probe unavailable ({spec['note']}): {e}")
                        continue
                    raise
                after = credits_remaining(hdrs)
                spent = None
                source = "table"
                if after is not None and before is not None:
                    spent = before - after
                    if spent < 0:
                        spent = COST_TABLE.get(spec["endpoint"], 1)
                        source = "table_header_out_of_order"
                    else:
                        source = "measured"
                if spent is None:
                    spent = COST_TABLE.get(spec["endpoint"], 1)
                if after is not None:
                    prev_remaining = after
                    if after <= RESERVE_FLOOR:
                        append_jsonl(ledger_path(root), {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "event": "reserve_floor", "remaining": after})
                        print(f"RESERVE FLOOR {RESERVE_FLOOR} reached "
                              f"(remaining {after}); stopping ladder")
                        stop = True
                rec = write_pull(root, spec, payload, hdrs, spent, source, after)
                man[spec["pull_id"]] = rec      # in-run dedupe
                run_req += 1
                run_credits += spent
                daily["requests"] += 1
                daily["credits"] += spent
                save_daily_caps(root, today, daily)
                append_jsonl(ledger_path(root), {
                    "ts": rec["ts"], "endpoint": spec["endpoint"],
                    "pull_id": spec["pull_id"], "spent": spent,
                    "source": source, "remaining": after,
                    "run_requests": run_req, "run_credits": run_credits})
                done += 1
                if done % 25 == 0:
                    print(f"  progress: done={done} skipped={skipped} "
                          f"run_credits={run_credits} remaining={after}", flush=True)
                pace_sleep(args.rpm)
    except RateLimitHit as e:
        append_jsonl(ledger_path(root), {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "rate_limit_incident", "detail": str(e),
            "run_requests": run_req, "run_credits": run_credits})
        print(f"RATE LIMIT INCIDENT — run paused per owner rule: {e}")
        print(f"completed before incident: done={done} skipped={skipped} "
              f"run_credits={run_credits}")
        return 2
    print(f"pull complete: done={done} skipped={skipped} "
          f"run_requests={run_req} run_credits={run_credits}")
    return 0


def cmd_mover(args):
    """Merge staging -> X10 (raw + parquet + manifests) when X10 is healthy."""
    if not x10_healthy(15):
        print("X10 unavailable — nothing moved (retry later)")
        return 1
    if not os.path.isdir(STAGING_ROOT):
        print("no staging dir — nothing to move")
        return 0
    os.makedirs(X10_ROOT, exist_ok=True)
    if not args.execute:
        n = sum(len(fs) for _, _, fs in os.walk(STAGING_ROOT))
        print(f"(dry-run: would rsync {n} staged files -> {X10_ROOT})")
        return 0
    for sub in ("raw", "parquet"):
        src = os.path.join(STAGING_ROOT, sub)
        if os.path.isdir(src):
            subprocess.run(["rsync", "-a", src + "/", os.path.join(X10_ROOT, sub)],
                           check=True)
    # manifests: dedupe merge by pull_id
    for name in ("pull_manifest.jsonl", "credit_ledger.jsonl"):
        s = os.path.join(STAGING_ROOT, name)
        d = os.path.join(X10_ROOT, name)
        recs = {}
        for p in (d, s):
            if os.path.exists(p):
                for line in open(p):
                    line = line.strip()
                    if line:
                        try:
                            r = json.loads(line)
                            recs[str(r.get("pull_id") or r.get("ts")) + str(r.get("endpoint", ""))] = r
                        except Exception:
                            pass
        tmp = d + ".tmp"
        with open(tmp, "w") as f:
            for r in recs.values():
                f.write(json.dumps(r, default=str) + "\n")
        os.replace(tmp, d)
    # daily caps: max-per-day per counter (both sides may have partial days)
    sc = os.path.join(STAGING_ROOT, "state", "daily_caps.json")
    dc = os.path.join(X10_ROOT, "state", "daily_caps.json")
    merged = {}
    for p in (dc, sc):
        if os.path.exists(p):
            try:
                for day, rec in json.load(open(p)).items():
                    cur = merged.setdefault(day, {"requests": 0, "credits": 0})
                    cur["requests"] = max(cur["requests"], rec.get("requests", 0))
                    cur["credits"] = max(cur["credits"], rec.get("credits", 0))
            except Exception:
                pass
    if merged:
        os.makedirs(os.path.dirname(dc), exist_ok=True)
        tmp = dc + ".tmp"
        with open(tmp, "w") as f:
            json.dump(merged, f, indent=1)
        os.replace(tmp, dc)
    print(f"moved + merged -> {X10_ROOT}")
    return 0


def cmd_coverage(args):
    root = out_root()
    man = load_manifest(root)
    ledger = []
    lp = ledger_path(root)
    if os.path.exists(lp):
        for line in open(lp):
            try:
                ledger.append(json.loads(line))
            except Exception:
                pass
    by_ep, by_day, by_sym = {}, {}, {}
    rows_total = 0
    for r in man.values():
        if not r.get("ok"):
            continue
        by_ep[r["endpoint"]] = by_ep.get(r["endpoint"], 0) + 1
        d = str(r.get("params", {}).get("at") or r.get("params", {}).get("from")
                or r.get("ts", ""))[:10]
        by_day[d] = by_day.get(d, 0) + 1
        for s in str(r.get("params", {}).get("symbols", "")).split(","):
            if s:
                by_sym[s] = by_sym.get(s, 0) + 1
        rows_total += int(r.get("rows") or 0)
    spent = sum(int(e.get("spent") or 0) for e in ledger if "spent" in e)
    remaining = next((e.get("remaining") for e in reversed(ledger)
                      if e.get("remaining") is not None), None)
    first = next((e for e in ledger if e.get("remaining") is not None), None)
    # reconciliation: header-balance math is ground truth; the logged sum can
    # understate when dedupe collapses duplicate in-run pulls (44 cr on
    # 2026-10-02 heatmap burst). Show both, never hide the gap.
    spent_measured = None
    spent_open = None
    if first is not None and remaining is not None:
        spent_open = int(first["remaining"]) + int(first.get("spent") or 0)
        spent_measured = spent_open - remaining
    incidents = [e for e in ledger if e.get("event") == "rate_limit_incident"]

    lines = []
    lines.append("# Skylit API archive — coverage + credit ledger")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()} "
                 f"by `scripts/skylit_api_archive.py coverage`.")
    lines.append(f"Archive root (active): `{root}`"
                 + (" — X10 healthy" if root == X10_ROOT
                    else " — X10 UNAVAILABLE, local staging; run `mover --execute` when healthy"))
    lines.append(f"X10 target: `{X10_ROOT}`")
    lines.append("")
    lines.append("## Credit ledger (honest)")
    lines.append("")
    lines.append(f"- Credits spent (logged sum): **{spent}**")
    if spent_measured is not None:
        lines.append(f"- Credits spent (balance math, ground truth): "
                     f"**{spent_measured}** "
                     f"(opening {spent_open} "
                     f"→ remaining {remaining})")
    lines.append(f"- Credits remaining (last measured header): **{remaining}**")
    lines.append(f"- Reserve floor: **{RESERVE_FLOOR}** (ladder stops there)")
    lines.append(f"- Rate-limit incidents: **{len(incidents)}**")
    for e in incidents:
        lines.append(f"  - {e.get('ts')}: {e.get('detail')}")
    lines.append("")
    lines.append("## Pulls by endpoint")
    lines.append("")
    lines.append("| endpoint | pulls | cost/call |")
    lines.append("|---|---|---|")
    for ep in sorted(by_ep):
        lines.append(f"| {ep} | {by_ep[ep]} | {COST_TABLE.get(ep, '?')} cr |")
    lines.append("")
    lines.append("## Coverage by day")
    lines.append("")
    lines.append("| date | pulls |")
    lines.append("|---|---|")
    for d in sorted(by_day):
        lines.append(f"| {d} | {by_day[d]} |")
    lines.append("")
    lines.append("## Coverage by symbol (pulls mentioning symbol)")
    lines.append("")
    lines.append("| symbol | pulls |")
    lines.append("|---|---|")
    for s in sorted(by_sym, key=lambda k: -by_sym[k]):
        lines.append(f"| {s} | {by_sym[s]} |")
    lines.append("")
    lines.append(f"Parquet-mirror rows flattened so far: **{rows_total}**")
    lines.append("")
    lines.append("## Manifest")
    lines.append("")
    lines.append(f"- `pull_manifest.jsonl`: {len(man)} records "
                 "(ts, endpoint, params, credits, rows, sha256) — idempotency key = pull_id")
    lines.append(f"- `credit_ledger.jsonl`: {len(ledger)} records")
    lines.append("- Rate discipline: pacing at <=50% of 120 rpm with jitter; "
                 "stop-on-first-sign on any 429/403; daily caps enforced.")
    lines.append("")
    lines.append("## Storage status")
    lines.append("")
    if root == X10_ROOT:
        lines.append("X10 Pro healthy — archive lives on the external disk.")
    else:
        lines.append("**X10 Pro volume wedged since 2026-10-02 ~09:00 PDT**: all "
                     "exFAT/FSKit I/O hangs (stat/ls/touch unbounded), persists "
                     "across two clean unmount/remount cycles; touch returned "
                     "EINTR. Media- or link-level, needs physical replug or host "
                     "reboot. Pulls are staging locally (same never-lose-pulls "
                     "pattern as `scripts/skylit_re_capture.py`); run "
                     "`python3 scripts/skylit_api_archive.py mover --execute` "
                     "once the volume responds to re-merge everything into "
                     f"`{X10_ROOT}` (raw + parquet + manifests, dedupe by pull_id).")
    lines.append("")
    lines.append("Incident history: 2026-10-02 ~09:00–10:30 PDT the volume wedged "
                 "(all I/O hung; recovered only after clean unmount/remount cycles; "
                 "~30 pulls staged locally first and merged back via `mover` once "
                 "healthy). If I/O hangs again: `diskutil unmount \"X10 Pro\"` then "
                 "`diskutil mount disk4s2`, never force-unmount mid-write.")
    lines.append("")
    lines.append("## API history depth (probed 2026-10-02, D2b + D2c bisect)")
    lines.append("")
    depth = sorted((r for r in man.values()
                    if "history depth" in (r.get("note") or "")),
                   key=lambda r: r.get("params", {}).get("at", ""))
    for r in depth:
        lines.append(f"- {r['params']['at'][:10]}: "
                     f"{int(r.get('rows') or 0):,} matrix rows")
    lines.append("")
    lines.append("Depth boundary (2026-10-02 D2c, refined — supersedes D2b's "
                 "2023-03 → 2024-03 range): the API states the floor directly — "
                 "pre-2023-03-28 timestamps return HTTP 400: \"The 'at' "
                 "timestamp may not be before 2023-03-28, where heatmap history "
                 "begins.\" Bisect probes 2023-09-13 (27,779 rows), 2023-06-13 "
                 "(26,554 rows) and the boundary day 2023-03-28 itself (12,493 "
                 "rows) all return real strike×expiry cells; 2023-03-13 and "
                 "2022-05-12 stay HTTP 400. Every day >= 2023-03-28 is buyable "
                 "at 5 cr/call for sweeps — ~11 months deeper than the D2b "
                 "assumption of 2024-03-08 (boundary-day rows are partial).")
    lines.append("")
    lines.append("## Big-move day sweep (D2b/D2c, ranked by leandata realized range)")
    lines.append("")
    sweep_by_day = {}
    for r in man.values():
        if (r.get("note") or "").startswith("big-move sweep"):
            d = r.get("params", {}).get("at", "")[:10]
            sweep_by_day[d] = sweep_by_day.get(d, 0) + 1
    if sweep_by_day:
        lines.append("Core profile (60s RTH, calibration quartet) per swept "
                     "day. Since D2c the RTH window is DST-aware "
                     "(America/New_York): EDT-day pull_ids are byte-identical "
                     "to D2b's, EST days (2024-03-04..08) now map to "
                     "14:30-21:00Z instead of a 1-hour-offset window:")
        lines.append("")
        lines.append("| swept day | core pulls archived |")
        lines.append("|---|---|")
        for d in sorted(sweep_by_day, key=lambda k: -sweep_by_day[k]):
            lines.append(f"| {d} | {sweep_by_day[d]} |")
        lines.append("")
    core_by_day = {}
    for r in man.values():
        if (r.get("endpoint") == "historical"
                and r.get("params", {}).get("symbols") == ",".join(CALIB_SYMBOLS)
                and r.get("params", {}).get("at")):
            d = r["params"]["at"][:10]
            core_by_day[d] = core_by_day.get(d, 0) + 1
    rank_csv = os.path.join(REPO, "data", "d2b", "bigmove_day_rank.csv")
    queue = []
    if os.path.exists(rank_csv):
        try:
            with open(rank_csv) as fh:
                ranked = list(csv.DictReader(fh))
            buyable = [r for r in ranked if r["date"] >= SWEEP_DEPTH_FLOOR]
            buyable.sort(key=lambda r: -float(r["mean_rth_pct_range"]))
            for r in buyable:
                if core_by_day.get(r["date"], 0) >= 385:
                    continue
                queue.append(r)
                if len(queue) >= 10:
                    break
        except Exception:
            queue = []
    if queue:
        lines.append("Next in ranked queue (unswept, buyable — one day per "
                     "tranche at core profile):")
        lines.append("")
        for r in queue:
            lines.append(f"- {r['date']}: mean RTH range "
                         f"{r['mean_rth_pct_range']}% (n={r['n_tickers']}, "
                         f"core archived {core_by_day.get(r['date'], 0)}/390)")
        lines.append("")
    lines.append(f"Ranking source: `{rank_csv}` "
                 "(scripts/skylit_bigmove_rank.py, leandata stock_1min, "
                 "read-only).")
    body = "\n".join(lines)
    if args.execute:
        os.makedirs(os.path.dirname(COVERAGE_DOC), exist_ok=True)
        with open(COVERAGE_DOC, "w") as f:
            f.write(body + "\n")
        print("written:", COVERAGE_DOC)
    else:
        print(body)
        print("\n(dry-run; `coverage --execute` writes the doc)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["plan", "pull", "mover", "coverage"])
    ap.add_argument("--batch", default="all",
                    choices=["all", "probe", "historical", "range", "heatmap",
                             "sweep"])
    ap.add_argument("--sweep-days", default="",
                    help="comma-separated YYYY-MM-DD days for the big-move "
                         "sweep batch (core profile per day)")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--max-credits", type=int, default=DEFAULT_MAX_CREDITS)
    ap.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    ap.add_argument("--rpm", type=int, default=DEFAULT_RPM)
    ap.add_argument("--metrics", default="gamma")
    args = ap.parse_args()
    if args.rpm > 60:
        raise SystemExit("owner rule: rpm must stay <= 50% of the 120 rpm limit (<=60)")
    return {"plan": cmd_plan, "pull": cmd_pull,
            "mover": cmd_mover, "coverage": cmd_coverage}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
