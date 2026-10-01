#!/usr/bin/env python3
"""skylit_re_capture.py — RE campaign capture pipeline (2026-09-30).

Pulls /v1/historical?layout=matrix (per-strike x per-expiry value grid +
nodeType) at a fixed cadence for one or more symbols, plus optional
/v1/historical/range 1s netted frames for dynamics. Idempotent (skips
existing files), paced, credit-aware.

Usage:
  python3 scripts/skylit_re_capture.py matrix --symbols SPX,SPY,QQQ,IWM \
      --date 2026-09-30 --step 60 --metrics gamma,vanna
  python3 scripts/skylit_re_capture.py range --symbols SPX,SPY,QQQ,IWM \
      --date 2026-09-30
Env: SKYLIT_API_KEY (see gammasummit/.env). Output:
  <out>/<metric>/<date>/<HHMMSS>.json.gz  + <out>/capture_manifest.jsonl
"""
import argparse, gzip, json, os, random, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timedelta, timezone

API = "https://api.skylit.ai"
X10_ROOT = "/Volumes/X10 Pro/gammasummit/t3/re/raw"
LOCAL_STAGING = "/Users/admin/Desktop/Github Projects/gammasummit/data/re-staging"
RTH_START = (13, 30)   # 9:30 ET
RTH_END = (20, 0)      # 16:00 ET


def out_root():
    """X10 when mounted, local staging otherwise (never lose captures to an
    unplugged disk). Staged files are rsync'd to X10 by the mover below."""
    if os.path.isdir("/Volumes/X10 Pro"):
        return X10_ROOT
    return LOCAL_STAGING


def get_key():
    k = os.environ.get("SKYLIT_API_KEY", "")
    if not k:
        for p in ("/Users/admin/Desktop/Github Projects/gammasummit/.env", os.path.expanduser("~/.hermes/.env")):
            try:
                for line in open(p):
                    if line.startswith("SKYLIT_API_KEY="):
                        k = line.split("=", 1)[1].strip()
                        if k:
                            os.environ["SKYLIT_API_KEY"] = k
                            return k
            except OSError:
                pass
    return k


def api_get(path, params, key, max_attempts=5):
    url = API + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(max_attempts):
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {key}",
            "Accept-Encoding": "gzip",
        })
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                    raw = gzip.decompress(raw)
                return json.loads(raw), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                wait = float(e.headers.get("Retry-After", 0) or 0) or min(30, 2 ** attempt) + random.random()
                print(f"  HTTP {e.code}, retry in {wait:.1f}s", flush=True)
                time.sleep(wait)
                continue
            body = e.read().decode(errors="replace")[:300]
            raise SystemExit(f"fatal HTTP {e.code}: {body}")
        except (TimeoutError, OSError) as e:
            time.sleep(min(30, 2 ** attempt) + random.random())
    raise SystemExit(f"gave up on {path}")


def day_window(date_str, step, metrics):
    d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    start = d.replace(hour=RTH_START[0], minute=RTH_START[1])
    end = d.replace(hour=RTH_END[0], minute=RTH_END[1])
    ticks = []
    t = start
    while t <= end:
        ticks.append(t)
        t += timedelta(seconds=step)
    return ticks


def out_path(root, kind, metric, date_str, t):
    return os.path.join(root, kind, metric, date_str, t.strftime("%H%M%S") + ".json.gz")

def run_matrix(args, key):
    metrics = args.metrics.split(",")
    ticks = day_window(args.date, args.step, metrics)
    os.makedirs(out_root(), exist_ok=True)
    man = open(os.path.join(out_root(), "capture_manifest.jsonl"), "a")
    done = skipped = 0
    for t in ticks:
        ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        for metric in metrics:
            p = out_path(out_root(), "matrix", metric, args.date, t)
            if os.path.exists(p):
                skipped += 1
                continue
            params = {"symbols": args.symbols, "at": ts, "layout": "matrix",
                      "metric": metric, "maxStrikes": "all", "maxExpirations": "all"}
            body, hdrs = api_get("/v1/historical", params, key)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with gzip.open(p, "wt") as f:
                json.dump(body, f)
            cred = hdrs.get("X-Credits-Remaining", "?")
            man.write(json.dumps({"t": ts, "metric": metric, "file": p,
                                  "credits_remaining": cred}) + "\n")
            man.flush()
            done += 1
            if done % 20 == 0:
                print(f"  {args.date} {ts} {metric}: done={done} skipped={skipped} credits_left={cred}", flush=True)
        # pace ~<=100 rpm
        time.sleep(max(0.0, 60.0 / min(args.rpm, 100) - 0.05))
    print(f"matrix {args.date}: done={done} skipped={skipped}")


def run_range(args, key):
    d = datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
    man = open(os.path.join(out_root(), "capture_manifest.jsonl"), "a")
    t = d.replace(hour=RTH_START[0], minute=RTH_START[1])
    end = d.replace(hour=RTH_END[0], minute=RTH_END[1])
    done = skipped = 0
    while t < end:
        w_end = min(t + timedelta(minutes=15), end)
        p = out_path(out_root(), "range", "gamma", args.date, t)
        if os.path.exists(p):
            skipped += 1
        else:
            params = {"symbols": args.symbols,
                      "from": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "to": w_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "metric": "gamma", "maxStrikes": "all", "maxExpirations": "all"}
            body, hdrs = api_get("/v1/historical/range", params, key)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with gzip.open(p, "wt") as f:
                json.dump(body, f)
            cred = hdrs.get("X-Credits-Remaining", "?")
            man.write(json.dumps({"t": t.isoformat(), "kind": "range", "file": p,
                                  "credits_remaining": cred}) + "\n")
            man.flush()
            done += 1
            print(f"  range {t} credits_left={cred}", flush=True)
        t = w_end
        time.sleep(1.0)
    print(f"range {args.date}: done={done} skipped={skipped}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["matrix", "range"])
    ap.add_argument("--symbols", default="SPX,SPY,QQQ,IWM")
    ap.add_argument("--date", required=True)
    ap.add_argument("--step", type=int, default=60, help="seconds between matrix calls")
    ap.add_argument("--metrics", default="gamma")
    ap.add_argument("--rpm", type=int, default=90)
    args = ap.parse_args()
    key = get_key()
    if not key:
        raise SystemExit("SKYLIT_API_KEY not found (gammasummit/.env or ~/.hermes/.env)")
    if args.mode == "matrix":
        run_matrix(args, key)
    else:
        run_range(args, key)


if __name__ == "__main__":
    main()
