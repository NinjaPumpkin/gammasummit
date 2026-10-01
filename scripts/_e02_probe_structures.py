#!/usr/bin/env python3
"""Probe shapes of PAIR files, skylit_sameinstant_v2.json, and X10 range captures (read-only)."""
import json, gzip, os, glob

SF = "/Users/admin/Desktop/Github Projects/SignalForge/data"

def walk(o, d=0, maxd=2, limit=12):
    if d > maxd:
        return
    if isinstance(o, dict):
        for k, v in list(o.items())[:limit]:
            if isinstance(v, (dict, list)):
                print("  " * d + f"{k} {type(v).__name__} len={len(v)}")
                walk(v, d + 1, maxd, limit)
            else:
                print("  " * d + f"{k} = {repr(v)[:90]}")
    elif isinstance(o, list) and o:
        print("  " * d + "[0]:")
        walk(o[0], d + 1, maxd, limit)

print("=== PAIR 2026-09-29T140614 ===")
p = json.load(open(f"{SF}/skylit_pairs/PAIR_2026-09-29T140614.131468_0000.json"))
walk(p, maxd=2)

print("\n=== PAIR 2026-09-25T143444 (potentially stale) ===")
p2 = json.load(open(f"{SF}/skylit_pairs/PAIR_2026-09-25T143444.553412_0000.json"))
walk(p2, maxd=1)

print("\n=== skylit_sameinstant_v2.json ===")
d = json.load(open(f"{SF}/skylit_sameinstant_v2.json"))
print(type(d).__name__, len(d) if hasattr(d, "__len__") else "")
if isinstance(d, dict):
    for k, v in list(d.items())[:10]:
        print(" ", k, type(v).__name__, len(v) if hasattr(v, "__len__") else v)
    for k, v in d.items():
        if isinstance(v, list) and v:
            print("--- sample row from", k)
            walk(v[0], maxd=1)
            break
elif isinstance(d, list):
    print("--- sample row")
    walk(d[0], maxd=1)

print("\n=== X10 range dir ===")
rng = "/Volumes/X10 Pro/gammasummit/t3/re/raw/range/gamma"
days = sorted(os.listdir(rng))
print("days:", len(days), days[:3], days[-2:])
d0 = os.path.join(rng, days[-1])
files = sorted(f for f in os.listdir(d0) if not f.startswith("._"))
print("files on last day:", len(files), files[:3])
f0 = os.path.join(d0, files[0])
obj = json.load(gzip.open(f0, "rt"))
print("--- range file keys:", list(obj.keys()))
print("meta:", obj.get("meta"))
print("from/to:", obj.get("from"), obj.get("to"))
for k, v in obj.items():
    if k not in ("meta", "from", "to"):
        print(" ", k, type(v).__name__, len(v) if hasattr(v, "__len__") else v)
syms = obj.get("symbols") or obj.get("data") or {}
if isinstance(syms, dict):
    s0 = next(iter(syms))
    print("symbol", s0, "keys:", list(syms[s0].keys()) if isinstance(syms[s0], dict) else type(syms[s0]))
    sd = syms[s0]
    if isinstance(sd, dict):
        for k, v in sd.items():
            if isinstance(v, list):
                print("  ", k, "list len", len(v))
                if v:
                    print("    [0]:", repr(v[0])[:200])
            else:
                print("  ", k, repr(v)[:120])
