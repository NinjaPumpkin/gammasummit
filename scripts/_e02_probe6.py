#!/usr/bin/env python3
"""Probe 6 (read-only):
1. King semantics: is king strike == argmax |strikes.value| ? Also argmax |cell| location?
2. UW cadence re-derivation (PM note #2): full-day DISTINCT timestamp walk on ONE liquid
   strike x expiry in gamma_data_v2 for 2026-09-30, vs manifest-level walk count.
3. Check GAMMASUMMIT_UW_* env presence (never print values) + numpy availability.
"""
import json, os, sys, datetime
sys.path.insert(0, "/Users/admin/Desktop/Github-Projects/gammasummit/scripts")

BASE = "/Volumes/X10 Pro/gammasummit/t3/re/raw"

# ---- 1. king semantics on a few captures
from p0_parity_dataset import load_matrix_file
print("=== king semantics ===")
for day, win in [("2026-09-30", "133000"), ("2026-09-30", "194500"), ("2026-09-29", "150000")]:
    try:
        m = load_matrix_file(f"{BASE}/matrix/gamma/{day}/{win}.json.gz")
    except Exception as e:
        print(day, win, "ERR", e)
        continue
    for sym, s in m["symbols"].items():
        sm = s["strikes"]
        king = [x for x in sm if x.get("nodeType") == "king"]
        arg_st = max(sm, key=lambda x: abs(x["value"]))
        # global argmax |cell|
        gc = max(s["cells"].items(), key=lambda kv: abs(kv[1])) if s["cells"] else None
        ok1 = king and king[0]["strike"] == arg_st["strike"]
        ok2 = king and gc and float(king[0]["strike"]) == gc[0][0]
        print(f"{day} {win} {sym}: king={king[0]['strike'] if king else None} "
              f"argmax|strikes.value|={arg_st['strike']} match={ok1} | "
              f"argmax|cell|={gc[0] if gc else None} match={ok2}")

# ---- 2. UW distinct walk on one liquid strike x expiry
print("\n=== UW strike-level distinct walk 2026-09-30 ===")
uw_url = os.environ.get("GAMMASUMMIT_UW_URL", "")
uw_key = os.environ.get("GAMMASUMMIT_UW_SERVICE_KEY", "")
print("env: GAMMASUMMIT_UW_URL set:", bool(uw_url), "| GAMMASUMMIT_UW_SERVICE_KEY set:", bool(uw_key))
try:
    import numpy  # noqa
    print("numpy:", numpy.__version__)
except ImportError:
    print("numpy: NOT available (stdlib-only harness)")

if uw_url and uw_key:
    from p0_parity_dataset import UWClient
    uw = UWClient()
    lo, hi = "2026-09-30T00:00:00+00:00", "2026-10-01T00:00:00+00:00"
    # pick the most common (strike, expiry) for SPX that day: sample first rows
    rows = uw.q("gamma_data_v2", select="strike,expiry_date", params={
        "ticker": "eq.SPX", "and": f"(timestamp.gte.{lo},timestamp.lt.{hi})"}, limit=2000)
    from collections import Counter
    cnt = Counter((r["strike"], r["expiry_date"]) for r in rows)
    (st, ex), n = cnt.most_common(1)[0]
    print(f"walk target: SPX strike={st} expiry={ex} (sampled {n}/{len(rows)} rows in first page)")
    # distinct timestamp walk on this strike x expiry
    out = []
    cursor = lo
    while True:
        rr = uw.q("gamma_data_v2", select="timestamp", params={
            "ticker": "eq.SPX", "strike": f"eq.{st}", "expiry_date": f"eq.{ex}",
            "and": f"(timestamp.gte.{cursor},timestamp.lt.{hi})"},
            order="timestamp.asc", limit=1)
        if not rr:
            break
        ts = rr[0]["timestamp"]
        if out and ts == out[-1]:
            break
        out.append(ts)
        cursor = ts.replace("+00:00", "+00:00.000001")
        if len(out) > 3000:
            break
    print("strike-level distinct timestamps 09-30:", len(out))
    if out:
        print("first:", out[0], "last:", out[-1])
        # cadence histogram in minutes
        dts = []
        prev = None
        for t in out:
            dt = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
            if prev:
                dts.append((dt - prev).total_seconds())
            prev = dt
        dts.sort()
        import statistics
        print("cadence s: min", dts[0], "median", statistics.median(dts), "max", dts[-1])
        # compare with cached ticker-level walk
        cache = json.load(open("/Users/admin/Desktop/Github-Projects/gammasummit/data/p0/uw_snapshot_cache.json"))
        print("cached ticker-level walk 09-30:", len(cache.get("2026-09-30", [])))
else:
    print("SKIP walk — env not set in this shell")
