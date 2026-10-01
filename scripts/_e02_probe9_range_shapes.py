#!/usr/bin/env python3
"""Probe 9: range file self-consistency — len(axes[].strikes) vs len(frames[].values)
per symbol/window/day; also axes count and frame axis ids."""
import gzip
import json
import os
from collections import Counter, defaultdict

RAW = "/Volumes/X10 Pro/gammasummit/t3/re/raw/range/gamma"
shapes = defaultdict(Counter)
for day in sorted(os.listdir(RAW)):
    if day.startswith("._") or not os.path.isdir(os.path.join(RAW, day)):
        continue
    if day < "2026-09-28":
        continue
    d = os.path.join(RAW, day)
    for fn in sorted(os.listdir(d)):
        if fn.startswith("._") or not fn.endswith(".json.gz"):
            continue
        with gzip.open(os.path.join(d, fn), "rt") as f:
            obj = json.load(f)
        for sym in obj["data"]["symbols"]:
            name = sym["symbol"]
            n_axes = len(sym.get("axes", []))
            strike_lens = tuple(len(a.get("strikes", [])) for a in sym.get("axes", []))
            exp_lens = tuple(len(a.get("expirations", [])) for a in sym.get("axes", []))
            val_lens = Counter()
            ax_ids = Counter()
            for fr in sym.get("frames", []):
                val_lens[len(fr.get("values", []))] += 1
                ax_ids[fr.get("axis")] += 1
            shapes[(day, name)][(n_axes, strike_lens, exp_lens, tuple(sorted(val_lens.items())),
                                 tuple(sorted(ax_ids.items())))] += 1
for k in sorted(shapes):
    for shape, n in shapes[k].items():
        print(k, "files:", n, "-> n_axes/strike_lens/exp_lens/val_lens/axis_ids:", shape)
