#!/usr/bin/env python3
"""Probe 3: range file symbols list layout; PAIR grid deep; sameinstant_v2 need+rows (read-only)."""
import json, gzip

SF = "/Users/admin/Desktop/Github Projects/SignalForge/data"

print("=== range file symbols layout ===")
f0 = "/Volumes/X10 Pro/gammasummit/t3/re/raw/range/gamma/2026-09-30/133000.json.gz"
obj = json.load(gzip.open(f0, "rt"))
data = obj["data"]
print("from/to:", data["from"], data["to"])
syms = data["symbols"]
for sv in syms[:1]:
    print("symbol entry type", type(sv).__name__, (list(sv.keys()) if isinstance(sv, dict) else sv))
    if isinstance(sv, dict):
        for k, v in sv.items():
            if isinstance(v, list):
                print(" ", k, "list len", len(v))
                if v:
                    it = v[0]
                    if isinstance(it, dict):
                        print("   [0] keys:", list(it.keys()))
                        for kk, vv in it.items():
                            if isinstance(vv, list):
                                print("     ", kk, "list len", len(vv), "[:4]:", repr(vv[:4])[:120])
                            else:
                                print("     ", kk, repr(vv)[:100])
                    else:
                        print("   [0]:", repr(it)[:120])
            elif isinstance(v, dict):
                print(" ", k, "dict:", list(v.keys())[:12])
            else:
                print(" ", k, repr(v)[:100])

print("\n=== PAIR grid deep ===")
p = json.load(open(f"{SF}/skylit_pairs/PAIR_2026-09-29T140614.131468_0000.json"))
g = p["grid"]
print("grid keys:", list(g.keys()))
cells = g["cells"]
print("cells[0..3]:", cells[:3])
print("spotLine[0..2]:", g["spotLine"][:2])
print("n cells", len(cells), "n spotLine", len(g["spotLine"]))

print("\n=== sameinstant_v2 need + rows ===")
d = json.load(open(f"{SF}/skylit_sameinstant_v2.json"))
print("need:", json.dumps(d["need"], indent=1)[:1200])
row = d["rows"][0]
print("row keys:", sorted(row.keys()))
ts = set(); tk = set()
ex = {}
for r in d["rows"]:
    ts.add(r.get("timestamp")); tk.add(r.get("ticker"))
    e = r.get("expiry_date"); ex[e] = ex.get(e, 0) + 1
print("n distinct ts:", len(ts), "tickers:", sorted(tk))
print("ts sample:", sorted(ts)[:3], "...", sorted(ts)[-2:])
print("expiry counts:", dict(sorted(ex.items())[:8]), "... total exp", len(ex))
