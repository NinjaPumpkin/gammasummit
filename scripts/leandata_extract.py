#!/usr/bin/env python3
"""leandata_extract.py — throttled leandata extraction driver (gammasummit, D3).

PROVENANCE: wraps the proven SignalForge extractor suite READ-ONLY via
importlib (scripts/leandata_backfill.py + scripts/leandata_options_minute.py
in the SignalForge repo). No SignalForge file is modified or copied; the
state-key shapes and parquet writer are reused verbatim so the staging
archive stays byte-compatible with the X10 archive
(<dataset>/ticker=XX/year=YYYY.parquet, zstd, .backfill_state.json ledger).

WHY THIS EXISTS (owner + PM rules, 2026-10-02): the extractor suite had no
global throttle; the vendor's only documented cap is per-user CONCURRENCY
(3 account-wide, measured: 3 in-flight never 429, 8 mostly 429). This driver
adds the mandated throttle layer BEFORE any resume:

  * pacing: 1 in-flight request (<= 50% of the documented 3) and >= 1.0 s
    + U(0, 0.5) s jitter between request starts (no rpm is published, so a
    conservative self-imposed spacing applies);
  * rate signals (HTTP 429/403 or any 'rate'/'concurrency' error body):
    exponential cooldown 300 s x 2^(n-1) (cap 1800 s), retry ONCE after the
    cooldown, ABORT the whole run on the second signal — stop-on-first-sign,
    never a retry-storm;
  * daily request cap (default 20000, LEANDATA_DAILY_CAP): counted per
    calendar day in docs/data/leandata-pull-manifest.json, run stops cleanly
    at the cap; the counter survives restarts within the same day;
  * auth errors (invalid_token*) are never retried;
  * every request + incident is recorded in the pull manifest.

ARCHIVE: extraction writes to a LOCAL staging archive (data/leandata-parquet)
by default because the X10 Pro drive is device-unresponsive (2026-10-02;
raw /dev reads hang even unmounted). Layout identical to the X10 tree, so
the staging tree merges into /Volumes/X10 Pro/leandata/parquet later with a
plain per-file copy + state-key union (write_parquet dedupes rows, so the
merge is idempotent). Pass --archive to retarget once X10 is healthy.

Universe: t012_tickers.txt lived ONLY on X10. This driver reconstructs the
560-name T0/T1/T2 universe from the Supabase ticker_universe tier table and
validates it against the 2026-10-01 coverage scan (missing counts must be
exactly 38 / 128 / 506 / 558 per dataset — they match).

Usage:
  LEANDATA_TOKEN is read at runtime from SignalForge dashboard-next/.env.local
  (never printed, never written to git). Examples:

    python3 scripts/leandata_extract.py --max-requests 5 --jobs stock_daily
    python3 scripts/leandata_extract.py
    python3 scripts/leandata_extract.py --jobs options_minute --max-requests 3000

Jobs run in order: stock_daily gaps -> stock_1min gaps (pair-batched) ->
options_eod breadth baseline -> options_minute grind (T2, activity order).
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SF_ROOT = "/Users/admin/Desktop/Github Projects/SignalForge"
SF_SCRIPTS = os.path.join(SF_ROOT, "scripts")
TOKEN_FILE = os.path.join(SF_ROOT, "dashboard-next", ".env.local")
SCAN_JSON = ("/Users/admin/hermes/profiles/gammasummit-research/cache/scratch/"
             "leandata_scan.json")
T012_JSON = os.path.join(REPO, "data", "t012_universe.json")
MANIFEST = os.path.join(REPO, "docs", "data", "leandata-pull-manifest.json")
COVERAGE_REPORT = os.path.join(REPO, "data", "leandata-coverage-report.json")

# throttle config (owner/PM rules 2026-10-02)
MIN_INTERVAL = float(os.environ.get("LEANDATA_MIN_INTERVAL", "1.0"))
JITTER_MAX = float(os.environ.get("LEANDATA_JITTER_MAX", "0.5"))
DAILY_CAP = int(os.environ.get("LEANDATA_DAILY_CAP", "20000"))
COOLDOWN_BASE = 300.0
COOLDOWN_CAP = 1800.0

STOCK_DAILY_RANGE = ("2016-01-01", "2026-09-30")
STOCK_1MIN_RANGE = ("2020-01-01", "2026-09-30")
OPTIONS_MINUTE_RANGE = ("2025-01-01", "2027-01-31")  # wide: tape is full per call
OPTIONS_EOD_EXPIRY = "2026-09-18"   # most recent monthly (3rd Fri) with EOD rows
OPTIONS_EOD_WINDOW = ("2026-08-29", "2026-09-18")  # <=21-day chunk, pre-expiry
OPTIONS_EOD_SPOT_WINDOW = ("2026-08-01", "2026-10-02")
# stock_1min breadth anchors: one month per ticker FIRST so every name lands
# a file early (X10 'missing -> 0' is ticker-presence), then the depth pass
# fills history (already-done month keys are skipped). Windows must match
# SignalForge months() keys exactly (start=1st, end=last day of month).
STOCK_1MIN_ANCHORS = [("2026-06-01", "2026-06-30"),
                      ("2025-06-01", "2025-06-30"),
                      ("2024-06-01", "2024-06-30")]
OPTIONS_EOD_STRIKES_AROUND_SPOT = 3


class ThrottleAbort(BaseException):
    """Run must stop NOW (second rate signal, or daily cap). BaseException so
    the wrapped scripts' `except Exception` fail-soft handlers cannot swallow
    it mid-loop and keep firing calls."""


# --------------------------------------------------------------- token/env

def load_env() -> None:
    """Read LEANDATA_TOKEN (and SUPABASE_*) from the untracked .env.local."""
    if not os.environ.get("LEANDATA_TOKEN"):
        with open(TOKEN_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("LEANDATA_TOKEN="):
                    os.environ["LEANDATA_TOKEN"] = line.split("=", 1)[1].strip()
                    break
    if not os.environ.get("LEANDATA_TOKEN"):
        raise SystemExit("LEANDATA_TOKEN not found in env or " + TOKEN_FILE)
    os.environ.setdefault("LEANDATA_ARCHIVE_DIR", os.path.join(REPO, "data", "leandata-parquet"))


# --------------------------------------------------------------- manifest

class Manifest:
    def __init__(self, path: str):
        self.path = path
        self.lock = threading.Lock()
        today = datetime.date.today().isoformat()
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get("date") != today:
                d = {}
        except Exception:
            d = {}
        self.d = {
            "date": today,
            "cap": DAILY_CAP,
            "requests": int(d.get("requests", 0)),
            "by_endpoint": d.get("by_endpoint", {}),
            "incidents": d.get("incidents", []),
            "jobs": d.get("jobs", {}),
            "started_at": d.get("started_at") or datetime.datetime.now().isoformat(),
            "policy": {
                "max_inflight": 1,
                "documented_concurrency_cap": 3,
                "min_interval_s": MIN_INTERVAL,
                "jitter_max_s": JITTER_MAX,
                "daily_cap": DAILY_CAP,
                "cooldown_s": f"{COOLDOWN_BASE}..{COOLDOWN_CAP} exp on rate signal",
                "abort_on": "second 429/403 rate signal, or daily cap",
            },
        }
        self.save()

    def save(self) -> None:
        self.d["updated_at"] = datetime.datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.d, f, indent=1)
        os.replace(tmp, self.path)

    def count_request(self, endpoint: str) -> None:
        with self.lock:
            self.d["requests"] += 1
            ep = endpoint.split("?")[0]
            self.d["by_endpoint"][ep] = self.d["by_endpoint"].get(ep, 0) + 1
            if self.d["requests"] % 25 == 0:
                self.save()

    def incident(self, kind: str, detail: str) -> None:
        with self.lock:
            self.d["incidents"].append({
                "ts": datetime.datetime.now().isoformat(),
                "kind": kind, "detail": detail[:300],
            })
            self.save()

    def job(self, name: str, **kv) -> None:
        with self.lock:
            self.d["jobs"].setdefault(name, {}).update(kv)
            self.save()


# --------------------------------------------------------------- throttle

class Throttle:
    def __init__(self, mf: Manifest):
        self.mf = mf
        self.lock = threading.Lock()
        self.next_free = 0.0
        self.rate_signals = 0
        self.run0 = mf.d["requests"]
        self.max_run = 0  # 0 = only the daily cap binds

    def over_run_budget(self) -> bool:
        return bool(self.max_run) and (self.mf.d["requests"] - self.run0 >= self.max_run)

    def wait_slot(self) -> None:
        with self.lock:
            now = time.monotonic()
            gap = MIN_INTERVAL + random.uniform(0, JITTER_MAX)
            start = max(now, self.next_free)
            self.next_free = start + gap
        delay = start - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def rate_signal(self, detail: str) -> None:
        self.rate_signals += 1
        self.mf.incident("rate_signal", detail)
        if self.rate_signals >= 2:
            self.mf.incident("abort", "second rate signal — stopping run")
            raise ThrottleAbort("second rate signal — aborting run")
        cool = min(COOLDOWN_BASE * (2 ** (self.rate_signals - 1)), COOLDOWN_CAP)
        print(f"[throttle] RATE SIGNAL: {detail[:120]} — cooldown {cool:.0f}s "
              f"(1/2 before abort)", flush=True)
        time.sleep(cool)


def make_throttled_call(mod, throttle: Throttle, mf: Manifest):
    """Replacement for leandata_backfill.call with the mandated throttle.

    Keeps the original signature. Retry policy OVERRIDES the original
    (which retried 429 up to 5x — a retry-storm risk):
      * 429/403 or rate-ish body -> throttle.rate_signal (cooldown, then ONE
        retry; second signal aborts the run);
      * 408/5xx/timeout -> bounded 3 attempts, exp backoff <= 16 s;
      * other HTTP errors -> RuntimeError('HTTP <code> <path>: <body>')
        exactly like the original (callers rely on 'archive_miss' etc.);
      * invalid_token* -> never retried.
    """
    def call(method: str, path: str, body=None, params=None, attempts=5):
        url = "https://api.leandata.uk" + path + \
            (("?" + urllib.parse.urlencode(params)) if params else "")
        token = os.environ["LEANDATA_TOKEN"]
        i = 0
        while True:
            if throttle.over_run_budget():
                raise ThrottleAbort("run request budget reached")
            if mf.d["requests"] >= DAILY_CAP:
                mf.incident("daily_cap", "daily request cap reached — stopping run")
                raise ThrottleAbort("daily request cap reached")
            throttle.wait_slot()
            mf.count_request(path)
            req = urllib.request.Request(url, method=method, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"})
            data = json.dumps(body).encode() if body else None
            try:
                with urllib.request.urlopen(req, data=data, timeout=90) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                body_txt = e.read().decode()[:300]
                if "invalid_token" in body_txt:
                    raise RuntimeError(f"HTTP {e.code} {path}: {body_txt}") from e
                rateish = (e.code in (429, 403)) or any(
                    s in body_txt.lower()
                    for s in ("rate", "concurrency", "budget_exceeded"))
                if rateish:
                    throttle.rate_signal(f"HTTP {e.code} {path}: {body_txt}")
                    continue  # single retry after cooldown (2nd signal aborts)
                if e.code in (408, 500, 502, 503, 504) and i < 2:
                    i += 1
                    time.sleep(min(2 ** i, 16))
                    continue
                raise RuntimeError(f"HTTP {e.code} {path}: {body_txt}") from e
            except (TimeoutError, OSError) as e:
                if i < 2:
                    i += 1
                    time.sleep(min(2 ** i, 16))
                    continue
                raise RuntimeError(f"network {path}: {e}") from e
    return call


# --------------------------------------------------------------- universe

def load_missing() -> dict[str, list[str]]:
    """missing[dataset] = t012 names absent from the archive.

    Sources in priority order:
      1. data/missing_<dataset>.txt (re-derived lists, e.g. from an X10 dir
         listing at merge time) — one ticker per line;
      2. the 2026-10-01 coverage scan (leandata_scan.json) when present —
         the authoritative pre-hang snapshot;
      3. validated derivations (no scan available):
         options_minute  = T2 tier (54 T0+T1 = first-54 of t012 are archived,
                           set-verified against the scan);
         options_eod     = t012 minus {SPY, QQQ} (only 2 ticker dirs exist,
                           documented in docs/data/leandata-inventory.md);
         stock_daily     = [] (the 38-name gap was closed in staging on
                           2026-10-02 — state ledger holds all 38 terminal);
         stock_1min      = [] and BLOCKED: the 128-name gap list required the
                           X10 directory listing (or the pruned scan JSON);
                           re-derive via data/missing_stock_1min.txt once X10
                           responds — never guess the names.
    """
    t012d = json.load(open(T012_JSON))
    t012, tiers = t012d["t012"], t012d.get("tier_order") or []
    missing: dict[str, list[str]] = {}
    for ds in ("stock_daily", "stock_1min", "options_minute", "options_eod"):
        override = os.path.join(REPO, "data", f"missing_{ds}.txt")
        if os.path.exists(override):
            with open(override) as f:
                missing[ds] = [ln.strip().upper() for ln in f if ln.strip()]
            continue
        if os.path.exists(SCAN_JSON):
            scan = json.load(open(SCAN_JSON))
            present = set(scan["datasets"][ds]["tickers"])
            missing[ds] = [t for t in t012 if t not in present]
            continue
        if ds == "options_minute":
            missing[ds] = [t for t, tr in zip(t012, tiers) if tr == "T2"]
        elif ds == "options_eod":
            missing[ds] = [t for t in t012 if t not in ("SPY", "QQQ")]
        else:
            missing[ds] = []
    return missing


def partial_not_terminal(ds: str, t: str, st: dict, mod) -> bool:
    """True when this pipeline STARTED ticker t for ds but has not reached a
    terminal state. Such tickers must stay on the grind list even after a
    merge makes them 'present' in X10 — otherwise the merge-time re-derived
    gap lists silently truncate in-progress depth (a ticker dropped after its
    first merged file would never pull the rest of its history)."""
    if f"{ds}/{t}" not in st and not any(k.startswith(f"{ds}/{t}/") for k in st):
        return False  # never touched by this pipeline — X10 gap list decides
    if ds == "stock_daily":
        return not mod.state_done(
            st.get(f"stock_daily/{t}/{STOCK_DAILY_RANGE[0]}/{STOCK_DAILY_RANGE[1]}"))
    if ds == "stock_1min":
        return not all(mod.state_done(st.get(f"stock_1min/{t}/{ms}/{me}"))
                       for ms, me in mod.months(STOCK_1MIN_RANGE[0],
                                                STOCK_1MIN_RANGE[1]))
    if ds == "options_eod":
        return not mod.state_done(st.get(f"options_eod/{t}/breadth-v1"))
    if ds == "options_minute":
        return not mod.state_done(st.get(f"options_minute/{t}"))
    return False


# --------------------------------------------------------------- jobs

def job_stock_daily(mod, missing):
    st = mod.state_load()
    mod.job_stock_daily(missing, STOCK_DAILY_RANGE[0], STOCK_DAILY_RANGE[1], st)


def job_stock_1min(mod, missing):
    st = mod.state_load()
    # breadth-first: one anchor month per ticker (still file-less) so every
    # name lands in the tree early, THEN the full depth pass — the anchor
    # month keys are identical to the full pass's month keys, so done months
    # are skipped and nothing is fetched twice
    staging = os.environ["LEANDATA_ARCHIVE_DIR"]
    for ws, we in STOCK_1MIN_ANCHORS:
        todo = [t for t in missing
                if not os.path.isdir(
                    os.path.join(staging, "stock_1min", f"ticker={t}"))]
        if not todo:
            break
        print(f"stock_1min anchor {ws}: {len(todo)} tickers without files",
              flush=True)
        mod.job_stock_1min_pairs(todo, ws, we, st)
    mod.job_stock_1min_pairs(missing, STOCK_1MIN_RANGE[0], STOCK_1MIN_RANGE[1], st)


def job_options_eod_breadth(mod, opt_min, mf, missing):
    """Breadth-first baseline: every missing root gets one REAL monthly-expiry
    EOD window (7 chain strikes around spot, one <=21-day pre-expiry chunk).

    Depth sweeps for remaining (expiry, strike, window) grids are budgeted in
    the pull manifest / inventory doc — the full sweep is ~1e6+ calls and is
    NOT attempted here. State keys reuse the proven job_options_eod shape
    'options_eod/<root>/<expiry>/<strike>/<start>/<end>'.
    """
    st = mod.state_load()
    expiry, (ws, we) = OPTIONS_EOD_EXPIRY, OPTIONS_EOD_WINDOW
    for root in missing:
        root_key = f"options_eod/{root}/breadth-v1"
        if mod.state_done(st.get(root_key)):
            continue
        if root in mod.INDEX_SYMBOLS:
            st[root_key] = "skipped: index root (options/eod archive is equity-only)"
            mod.state_save(st)
            continue
        try:
            d = mod.call("GET", "/v1/history/bars", params={
                "symbol": root, "timeframe": "1Day",
                "start": OPTIONS_EOD_SPOT_WINDOW[0], "end": OPTIONS_EOD_SPOT_WINDOW[1]})
            rows = [r for r in (d.get("bars", {}).get(root) or [])
                    if float(r.get("v") or 0) > 0]
            if not rows:
                st[root_key] = "skipped: no daily bars (unknown root)"
                mod.state_save(st)
                continue
            spot = float(rows[-1]["c"])
        except ThrottleAbort:
            raise
        except Exception as e:  # noqa: BLE001
            st[root_key] = f"error: spot {str(e)[:120]}"
            mod.state_save(st)
            continue
        try:
            chain = opt_min.fetch_contracts(root)  # proven stall-guarded parser
            # strike grid from the OCC symbol suffix: OCC = root+YYMMDD+C/P+
            # strike*1000 zero-padded 8 (proven format) — robust to the
            # contracts payload's strike FIELD name, which is not 'strike'
            strikes = sorted({int(sym[-8:]) / 1000
                              for sym in (str(c.get("symbol") or "").upper()
                                          for c in chain)
                              if len(sym) >= 8 and sym[-8:].isdigit()})
            if not strikes:
                st[root_key] = "skipped: no chains"
                mod.state_save(st)
                continue
        except ThrottleAbort:
            raise
        except Exception as e:  # noqa: BLE001
            st[root_key] = f"error: chain {str(e)[:120]}"
            mod.state_save(st)
            continue
        nearest = min(strikes, key=lambda s: abs(s - spot))
        lo = strikes.index(nearest) - OPTIONS_EOD_STRIKES_AROUND_SPOT
        hi = strikes.index(nearest) + OPTIONS_EOD_STRIKES_AROUND_SPOT + 1
        grid = strikes[max(0, lo):hi]
        fetched = 0
        for strike in grid:
            key = f"options_eod/{root}/{expiry}/{strike}/{ws}/{we}"
            if mod.state_done(st.get(key)):
                continue
            try:
                d = mod.call("GET", "/v1/options/eod", params={
                    "root": root, "expiration": expiry, "strike": str(strike),
                    "start": ws, "end": we})
                rows = d.get("data", [])
                if rows:
                    mod.write_parquet(rows, "options_eod", root, int(ws[:4]))
                st[key] = True
                fetched += len(rows)
            except ThrottleAbort:
                raise
            except Exception as e:  # noqa: BLE001
                st[key] = f"error: {str(e)[:120]}"
            mod.state_save(st)
        st[root_key] = True
        mod.state_save(st)
        print(f"options_eod {root}: spot={spot} grid={grid} rows={fetched}", flush=True)


def job_options_minute(mod, mf, missing, max_batches_per_root: int):
    """Grind the T2 gap (506 roots) in t012/activity order via the proven
    leandata_options_minute pipeline (contracts discovery + 8-OCC batches)."""
    st = mod.state_load()
    for root in missing:
        try:
            calls, rows = mod.job_options_minute(
                root, OPTIONS_MINUTE_RANGE[0], OPTIONS_MINUTE_RANGE[1],
                10, st, max_batches=max_batches_per_root, workers=1)
            # 0 batch calls after successful discovery = every batch key for
            # this root is already done — mark the root terminal so future
            # passes skip the 1-2 discovery calls too
            if calls == 0 and not str(st.get(f"options_minute/{root}", "")).startswith("error"):
                st[f"options_minute/{root}"] = True
                mod.state_save(st)
        except ThrottleAbort:
            raise
        except Exception as e:  # noqa: BLE001 — one bad root must not kill the grind
            print(f"options_minute {root}: RUNNER ERROR {str(e)[:160]}", flush=True)


# --------------------------------------------------------------- coverage

def coverage_report(staging: str) -> dict:
    import pyarrow.parquet as pq
    out = {}
    for ds in ("stock_daily", "stock_1min", "options_minute", "options_eod"):
        base = os.path.join(staging, ds)
        tickers, files, rows = [], 0, 0
        if os.path.isdir(base):
            for ent in sorted(os.listdir(base)):
                if not ent.startswith("ticker="):
                    continue
                tickers.append(ent.split("=", 1)[1])
                tdir = os.path.join(base, ent)
                for fn in sorted(os.listdir(tdir)):
                    if fn.endswith(".parquet") and not fn.startswith("._"):
                        files += 1
                        rows += pq.read_metadata(os.path.join(tdir, fn)).num_rows
        out[ds] = {"tickers": len(tickers), "files": files, "rows": rows,
                   "names": tickers}
    return out


# --------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", default="all",
                    help="comma list of stock_daily,stock_1min,options_eod,"
                         "options_minute (default all, in priority order)")
    ap.add_argument("--max-requests", type=int, default=0,
                    help="stop after N requests this run (0 = only daily cap)")
    ap.add_argument("--max-batches-per-root", type=int, default=0,
                    help="options_minute: cap batch calls per root (0 = uncapped)")
    args = ap.parse_args()

    load_env()
    staging = os.environ["LEANDATA_ARCHIVE_DIR"]
    os.makedirs(staging, exist_ok=True)

    # single-instance gate: the throttle budget is PER-PROCESS and the
    # vendor cap is ACCOUNT-wide — two concurrent drivers would break the
    # <=50%-of-limit rule
    import fcntl
    lock_f = open(os.path.join(staging, ".extract.lock"), "a+")
    try:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another leandata_extract run holds the lock — exiting")
        return 3

    sys.path.insert(0, SF_SCRIPTS)
    spec = importlib.util.spec_from_file_location(
        "leandata_backfill", os.path.join(SF_SCRIPTS, "leandata_backfill.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["leandata_backfill"] = mod
    spec.loader.exec_module(mod)
    spec2 = importlib.util.spec_from_file_location(
        "leandata_options_minute", os.path.join(SF_SCRIPTS, "leandata_options_minute.py"))
    opt_min = importlib.util.module_from_spec(spec2)
    sys.modules["leandata_options_minute"] = opt_min
    spec2.loader.exec_module(opt_min)
    # keep every filesystem touch LOCAL — X10 is device-dead (glob would hang)
    opt_min.TICKERS_FILE = os.path.join(REPO, "data", "t012_tickers.txt")
    opt_min.OPTIONS_EOD_DIR = os.path.join(staging, "options_eod")

    mf = Manifest(MANIFEST)
    throttle = Throttle(mf)
    throttle.max_run = args.max_requests
    mod.call = make_throttled_call(mod, throttle, mf)
    opt_min.call = mod.call  # sibling bound `call` at import — rebind

    missing = load_missing()
    # depth-integrity guard: tickers this pipeline started but has not finished
    # stay on the grind list even when a merge made them 'present' in X10
    # (re-derived gap lists are breadth-based and would truncate their depth)
    st_chk = mod.state_load()
    t012_all = json.load(open(T012_JSON))["t012"]
    for ds in list(missing):
        have = set(missing[ds])
        extra = [t for t in t012_all
                 if t not in have and partial_not_terminal(ds, t, st_chk, mod)]
        if extra:
            missing[ds] = list(missing[ds]) + extra
            print(f"grind-list {ds}: +{len(extra)} in-progress tickers kept "
                  f"(state ledger not terminal)", flush=True)
    print("archive (staging):", staging)
    for ds, names in missing.items():
        print(f"missing[{ds}] = {len(names)}")

    run0 = mf.d["requests"]
    # card priority (D3): options_eod + options_minute "feed RE + backtests
    # hardest" — breadth baseline before the long stock_1min grind
    order = ["options_eod", "options_minute", "stock_1min", "stock_daily"]
    wanted = [j.strip() for j in args.jobs.split(",") if j.strip()]
    todo = [j for j in order if "all" in wanted or j in wanted]

    try:
        for job in todo:
            if args.max_requests and mf.d["requests"] - run0 >= args.max_requests:
                print("run request budget reached — stopping")
                break
            mf.job(job, started_at=datetime.datetime.now().isoformat())
            print(f"=== job {job} ===", flush=True)
            if job == "stock_daily":
                job_stock_daily(mod, missing["stock_daily"])
            elif job == "stock_1min":
                job_stock_1min(mod, missing["stock_1min"])
            elif job == "options_eod":
                job_options_eod_breadth(mod, opt_min, mf, missing["options_eod"])
            elif job == "options_minute":
                job_options_minute(mod, mf, missing["options_minute"],
                                   args.max_batches_per_root)
            mf.job(job, finished_at=datetime.datetime.now().isoformat(),
                   requests_so_far=mf.d["requests"] - run0)
    except ThrottleAbort as e:
        print(f"ABORT: {e}", flush=True)
        mf.job("_aborted", reason=str(e),
               at=datetime.datetime.now().isoformat())
    finally:
        if mf.d["requests"] - run0 >= DAILY_CAP:
            print("daily request cap reached", flush=True)
        mf.save()

    cov = coverage_report(staging)
    with open(COVERAGE_REPORT, "w") as f:
        json.dump({"generated_at": datetime.datetime.now().isoformat(),
                   "archive": staging, "datasets": cov,
                   "requests_this_run": mf.d["requests"] - run0,
                   "requests_today": mf.d["requests"]}, f, indent=1)
    for ds, c in cov.items():
        print(f"staging {ds}: tickers={c['tickers']} files={c['files']} rows={c['rows']}")
    print("requests this run:", mf.d["requests"] - run0,
          "| today:", mf.d["requests"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
