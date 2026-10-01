#!/usr/bin/env python3
"""Probe 4: map range 1s frame values onto matrix grid — figure out what a range 'values' vector is
(per-strike aggregate across expiries? one expiry slice? flattened grid?). Read-only."""
import json, gzip, math

BASE = "/Volumes/X10 Pro/gammasummit/t3/re/raw"

def pearson(a, b):
    n = len(a)
    ma = sum(a) / n; mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0

# matrix file for 09-30 13:30
mfiles = [f for f in sorted(__import__("os").listdir(f"{BASE}/matrix/gamma/2026-09-30")) if f.startswith("1330")]
print("matrix candidates:", mfiles[:5])
m = json.load(gzip.open(f"{BASE}/matrix/gamma/2026-09-30/{mfiles[0]}", "rt"))
print("matrix top keys:", list(m.keys()))
print("meta:", m.get("meta"))
syms = m.get("symbols") or {}
print("symbols:", list(syms.keys()))
s = syms["SPX"]
print("SPX keys:", list(s.keys()))
print("asOf:", s.get("asOf"), "spot:", s.get("spot"))
print("expirations:", s.get("expirations"))
print("strikes type:", type(s.get("strikes")).__name__, end=" ")
st = s.get("strikes")
if isinstance(st, list):
    print("len", len(st), "first", st[:3])
    if st and isinstance(st[0], (list, dict)):
        print("  nested [0]:", repr(st[0])[:200])
cells = s.get("cells")
print("cells type:", type(cells).__name__)
if isinstance(cells, dict):
    ks = list(cells.keys())
    print("n cells", len(ks), "sample keys", ks[:4], "sample val", repr(cells[ks[0]])[:80])
    # check if keys encode strike_expiry
    # build per-expiry series over common strikes
    matrix = s.get("matrix")
    print("matrix present:", matrix is not None)
if isinstance(s.get("matrix"), list):
    mtx = s["matrix"]
    print("matrix dims:", len(mtx), "x", (len(mtx[0]) if mtx else 0))
    print("row0 first 5:", mtx[0][:5])

# range first frame same window
r = json.load(gzip.open(f"{BASE}/range/gamma/2026-09-30/133000.json.gz", "rt"))
sym_r = r["data"]["symbols"][0]
ax = sym_r["axes"][0]
rstrikes = ax["strikes"]; rexps = ax["expirations"]
vals = sym_r["frames"][0]["values"]
print("\nrange: n strikes", len(rstrikes), "n exps", len(rexps), "n vals", len(vals))
print("range exps:", rexps)

# compare per-expiry matrix columns vs range values on shared strikes
if isinstance(s.get("matrix"), list) and isinstance(st, list):
    mstrikes = st  # maybe per-strike flat
    shared = [x for x in rstrikes if x in set(mstrikes)]
    print("shared strikes:", len(shared))
    idx_r = {v: i for i, v in enumerate(rstrikes)}
    idx_m = {v: i for i, v in enumerate(mstrikes)}
    rvec = [vals[idx_r[x]] for x in shared]
    best = []
    for j, e in enumerate(s["expirations"]):
        mvec = [mtx[idx_m[x]][j] for x in shared]
        c = pearson(rvec, mvec)
        best.append((abs(c), c, e))
    best.sort(reverse=True)
    print("top per-expiry corrs:", [(round(c, 3), e) for _, c, e in best[:5]])
    # aggregate candidates
    sums = [sum(mtx[idx_m[x]][j] for j in range(len(s["expirations"]))) for x in shared]
    print("corr(range, sum over exps):", round(pearson(rvec, sums), 4))
    abssums = [sum(abs(mtx[idx_m[x]][j]) for j in range(len(s["expirations"]))) for x in shared]
    print("corr(range, abs-sum):", round(pearson(rvec, abssums), 4))
    print("sample rvec[:5]:", [round(v, 2) for v in rvec[:5]])
    print("sample sums[:5]:", [round(v, 2) for v in sums[:5]])
    # exact equality check: any expiry column identical?
    for j, e in enumerate(s["expirations"]):
        mvec = [mtx[idx_m[x]][j] for x in shared]
        if all(abs(a - b) < 1e-6 for a, b in zip(rvec, mvec)):
            print("EXACT MATCH with expiry", e)
