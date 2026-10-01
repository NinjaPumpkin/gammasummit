#!/usr/bin/env python3
"""Report per-day / per-symbol distribution of cached fit-dataset instants."""
import json
import statistics
from collections import Counter

idx = json.load(open("/Users/admin/Desktop/Github-Projects/gammasummit/data/e02/fit_dataset/index.json"))
c = Counter((e["day"], e["symbol"]) for e in idx["instants"])
days = Counter(e["day"] for e in idx["instants"])
print("per day:", dict(days))
for k in sorted(c):
    print(k, c[k])
dts = sorted(e["dt_s"] for e in idx["instants"])
print("dt_s: median", dts[len(dts) // 2], "p90", dts[int(len(dts) * 0.9)], "max", dts[-1])
