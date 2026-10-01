#!/usr/bin/env python3
"""Probe 2: deeper structure of range file data, PAIR grid cells/spotLine, sameinstant_v2 need+row keys (read-only)."""
import json, gzip, os

SF = "/Users/admin/Desktop/Github Projects/SignalForge/data"

print("=== range file data structure ===")
f0 = "/Volumes/X10 Pro/gammasummit/t3/re/raw/range/gamma/2026-09-30/133000.json.gz"
obj = json.load(gzip.open(f0, "rt"))
data = obj["data"]
print("data keys:", list(data.keys()))
for k, v in data.items():
    print(" ", k, type(v).__name__, (list(v.keys()) if isinstance(v, dict) else (len(v) if hasattr(v, "__len__") else v)))
syms = data.get("symbols") or {}
if not syms and isinstance(data, dict):
    # maybe keyed by symbol directly
    for k, v in data.items():
        if isinstance(v, dict) and ("axes" in v or "frames" in v):
            syms = data
            break
for sk, sv in list(syms.items())[:1]:
    print("symbol", sk)
    if isinstance(sv, dict):
        for k, v in sv.items():
            if isinstance(v, list):
                print("  ", k, "list len", len(v))
                if v:
                    it = v[0]
                    print("    [0] type", type(it).__name__)
                    if isinstance(it, dict):
                        for kk, vv in it.items():
                            print("      ", kk, type(vv).__name__, (len(vv) if hasattr(vv, "__len__") and not isinstance(vv, (int, float)) else vv) if not isinstance(vv, (dict,)) else list(vv.keys()))
                            if isinstance(vv, list) and vv:
                                print("        [0]:", repr(vv[0])[:120])
                    elif isinstance(it, (int, float)):
                        print("       values[:5]:", v[:5])
            elif isinstance(v, dict):
                print("  ", k, "dict keys:", list(v.keys())[:10])
            else:
                print("  ", k, repr(v)[:100])

print("\n=== PAIR grid deep ===")
p = json.load(open(f"{SF}/skylit_pairs/PAIR_2026-09-29T140614.131468_0000.json"))
g = p["grid"]
print("grid keys:", list(g.keys()))
cells = g["cells"]
print("cells[0..3]:")
for c in cells[:4]:
    print("  ", c)
print("spotLine[0..2]:")
for s in g["spotLine"][:3]:
    print("  ", s)
print("n cells", len(cells), "n spotLine", len(g["spotLine"]))

print("\n=== sameinstant_v2 need + row keys ===")
d = json.load(open(f"{SF}/skylit_sameinstant_v2.json"))
print("need:", json.dumps(d["need"], indent=1)[:1500])
row = d["rows"][0]
print("row keys:", sorted(row.keys()))
# find distinct timestamps + tickers + expiries
ts = set(); tk = set(); ex = set()
for r in d["rows"][:20000]:
    ts.add(r.get("timestamp")); tk.add(r.get("ticker")); ex.add(r.get("expiry_date"))
print("sample scan of first 20000 rows: n_ts", len(ts), "tickers", sorted(tk), "n_expiry", len(ex))
print("ts sample:", sorted(ts)[:3], "...", sorted(ts)[-2:])
