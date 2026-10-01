#!/usr/bin/env python3
"""Probe 7 (read-only): matrix cell zero/null semantics; UW vs matrix strike-grid overlap;
expiry sets per symbol; PAIR cells shape (23x20?)."""
import json, gzip, os, sys
from collections import Counter
sys.path.insert(0, "/Users/admin/Desktop/Github-Projects/gammasummit/scripts")
from p0_parity_dataset import load_matrix_file

BASE = "/Volumes/X10 Pro/gammasummit/t3/re/raw"
SF = "/Users/admin/Desktop/Github Projects/SignalForge/data"

print("=== matrix raw null/zero semantics 09-30 1330 SPX ===")
raw = json.load(gzip.open(f"{BASE}/matrix/gamma/2026-09-30/133000.json.gz", "rt"))
for sym in raw["data"]["symbols"]:
    if sym["symbol"] != "SPX":
        continue
    kinds = Counter()
    for row in sym["matrix"]:
        for v in row:
            if v is None:
                kinds["null"] += 1
            elif v == 0:
                kinds["zero"] += 1
            else:
                kinds["nonzero"] += 1
    print("cell kinds:", dict(kinds), "dims:", len(sym["matrix"]), "x", len(sym["matrix"][0]))
    print("expirations:", sym["expirations"])

print("\n=== per-symbol expiry sets (matrix) ===")
for sym in raw["data"]["symbols"]:
    print(sym["symbol"], "n exp:", len(sym["expirations"]), "first3:", sym["expirations"][:3],
          "last2:", sym["expirations"][-2:])

print("\n=== UW strike grid vs matrix grid (sameinstant_v2, SPX) ===")
d = json.load(open(f"{SF}/skylit_sameinstant_v2.json"))
rows = d["rows"]
by_ts = {}
for r in rows:
    by_ts.setdefault(r["timestamp"], []).append(r)
ts0 = sorted(by_ts)[0]
rr = by_ts[ts0]
uw_strikes = set(float(r["strike"]) for r in rr)
uw_exps = set(r["expiry_date"] for r in rr)
m = load_matrix_file(f"{BASE}/matrix/gamma/2026-09-28/130800.json.gz") if os.path.exists(
    f"{BASE}/matrix/gamma/2026-09-28/130800.json.gz") else None
print("UW snapshot", ts0, "rows", len(rr), "distinct strikes", len(uw_strikes),
      "distinct exps", len(uw_exps))
if m and "SPX" in m["symbols"]:
    s = m["symbols"]["SPX"]
    m_strikes = set(float(x["strike"]) for x in s["strikes"])
    m_exps = set(s["expirations"])
    print("matrix strikes", len(m_strikes), "expiries", len(m_exps))
    print("strike overlap:", len(uw_strikes & m_strikes),
          "uw-only:", len(uw_strikes - m_strikes), "matrix-only:", len(m_strikes - uw_strikes))
    print("expiry overlap:", sorted(m_exps & uw_exps)[:10], "... n =", len(m_exps & uw_exps),
          "matrix-only exps:", sorted(m_exps - uw_exps))
print("UW sample strikes:", sorted(uw_strikes)[:6], "...", sorted(uw_strikes)[-4:])

print("\n=== PAIR cells shape ===")
p = json.load(open(f"{SF}/skylit_pairs/PAIR_2026-09-29T140614.131468_0000.json"))
cells = p["grid"]["cells"]
keys = [c["key"] for c in cells]
strips = Counter(k.split("_")[0] for k in keys)
exps = Counter(k.split("_")[1] for k in keys)
print("n cells", len(cells), "distinct strikes", len(strips), "distinct exps", len(exps))
print("pair strike sample:", sorted(strips, key=float)[:4], "exp sample:", sorted(exps)[:6])
stars = [c for c in cells if c.get("star")]
print("star cells:", stars[:3])
texts = [c["text"] for c in cells[:8]]
print("cell text sample:", texts)
