#!/usr/bin/env python3
"""Probe 5: identify range frame semantics vs matrix grid + matrix strikes[].value semantics.
Hypotheses tested per strike s at t:
  H1 values[s] == matrix[s][e] for some expiry e (exact per-expiry slice)
  H2 values[s] == sum_e matrix[s][e]
  H3 values[s] == strikes[s].value  (per-strike aggregate in matrix record)
  H4 values[s] == max_e |matrix[s][e]| (or signed argmax)
Read-only."""
import json, gzip, math, os, sys
sys.path.insert(0, "/Users/admin/Desktop/Github-Projects/gammasummit/scripts")
from p0_parity_dataset import load_matrix_file, load_range_file

BASE = "/Volumes/X10 Pro/gammasummit/t3/re/raw"

def pearson(a, b):
    n = len(a)
    ma = sum(a) / n; mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else 0.0

day = "2026-09-30"
m = load_matrix_file(f"{BASE}/matrix/gamma/{day}/133000.json.gz")
s = m["symbols"]["SPX"]
print("asOf:", s["asOf"], "spot:", s["spot"])
exps = s["expirations"]
print("expirations:", exps)
strikes_meta = s["strikes"]
print("n strike records:", len(strikes_meta), "sample:", strikes_meta[0])
cells = s["cells"]
print("n non-empty cells:", len(cells))

r = load_range_file(f"{BASE}/range/gamma/{day}/133000.json.gz")
rs = r["symbols"]["SPX"]
ax = rs["axes"][0]
rstrikes = ax["strikes"]; rexps = ax["expirations"]
f0 = rs["frames"][0]
vals = f0["values"]
print("\nrange frame asOf:", f0["asOf"], "spot:", f0["spot"], "n vals:", len(vals))
print("range strikes[:4]:", rstrikes[:4], "range exps:", rexps)
print("range exps == matrix exps:", rexps == exps)

# rebuild raw matrix grid from loader cells
mst = [float(x["strike"]) for x in strikes_meta]
grid = {}
for (st, e), v in cells.items():
    grid[(st, e)] = v

shared = [x for x in rstrikes if float(x) in set(mst)]
print("shared strikes:", len(shared), "of range", len(rstrikes), "matrix", len(mst))
ir = {float(v): i for i, v in enumerate(rstrikes)}
im = {v: i for i, v in enumerate(mst)}
rvec = [vals[ir[float(x)]] for x in shared]

# H1: per-expiry columns
best = []
for j, e in enumerate(exps):
    mvec = [grid.get((float(x), e), 0.0) for x in shared]
    c = pearson(rvec, mvec)
    exact = all(abs(a - b) < 1e-6 for a, b in zip(rvec, mvec))
    best.append((abs(c), c, e, exact))
best.sort(reverse=True)
print("H1 top per-expiry corr:", [(round(c, 4), e, ex) for _, c, e, ex in best[:5]])

# H2: sums
sums = [sum(grid.get((float(x), e), 0.0) for e in exps) for x in shared]
print("H2 corr(sum_e):", round(pearson(rvec, sums), 4),
      "exact:", all(abs(a - b) < 1e-6 for a, b in zip(rvec, sums)))
abss = [sum(abs(grid.get((float(x), e), 0.0)) for e in exps) for x in shared]
print("H2b corr(abs-sum):", round(pearson(rvec, abss), 4))

# H3: matrix strikes[].value
svec = [strikes_meta[im[float(x)]]["value"] for x in shared]
print("H3 corr(strikes.value):", round(pearson(rvec, svec), 4),
      "exact:", all(abs(a - b) < 1e-6 for a, b in zip(rvec, svec)))
print("   sample strikes.value[:5]:", [round(v, 3) for v in svec[:5]])
print("   sample range vals[:5]:  ", [round(v, 3) for v in rvec[:5]])
print("   sample sums[:5]:        ", [round(v, 3) for v in sums[:5]])

# H4: signed argmax |cell| per strike
argm = []
for x in shared:
    cand = [(abs(grid.get((float(x), e), 0.0)), grid.get((float(x), e), 0.0)) for e in exps]
    argm.append(max(cand)[1] if cand else 0.0)
print("H4 corr(signed argmax|cell|):", round(pearson(rvec, argm), 4))

# what IS strikes.value? compare to sum / abs-argmax etc.
print("\n--- strikes.value semantics ---")
print("corr(strikes.value, sum_e):", round(pearson(svec, sums), 4))
print("corr(strikes.value, abs-sum):", round(pearson(svec, abss), 4))
print("corr(strikes.value, signed-argmax):", round(pearson(svec, argm), 4))
# per-strike: is strikes.value == sum over exps exactly?
n_exact_sum = sum(1 for x in shared if abs(strikes_meta[im[float(x)]]["value"] - sum(grid.get((float(x), e), 0.0) for e in exps)) < 1e-6)
print("strikes.value == sum_e exact count:", n_exact_sum, "/", len(shared))
# nodeType on strikes: king location
kings = [(x["strike"], x["value"], x["nodeType"]) for x in strikes_meta if x.get("nodeType") == "king"]
print("king records:", kings)
nt = {}
for x in strikes_meta:
    nt[x.get("nodeType")] = nt.get(x.get("nodeType"), 0) + 1
print("nodeType census this capture:", nt)
# range frame2 time delta
f1 = rs["frames"][1]
print("\nframe[1] asOf:", f1["asOf"], "-> cadence ~", f1["asOf"], f0["asOf"])
