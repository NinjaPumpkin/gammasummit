#!/usr/bin/env python3
"""skylit_bigmove_rank.py — rank historical days by realized daily range (D2b).

Reads the leandata `stock_1min` Hive dataset (read-only) and ranks every
session day by cross-ticker realized range, so the skylit_api_archive sweep
batch can spend its core-profile budget on the biggest-move days first.

Metric (per ticker-day):
  rth_pct_range  = (max(h) - min(l)) / first(c)  over RTH bars only
  full_pct_range = same over every bar of the day (extended session included)
`stock_1min` timestamps are ET wall-clock labelled with a Z suffix (bars span
04:00-19:59), so RTH is filtered on the 09:30-15:59 label window.

Day score = mean rth_pct_range across tickers (breadth-weighted, robust to a
single gapping name). Output: data/d2b/bigmove_day_rank.csv sorted by date,
top-N ranked table printed to stdout.

Usage:
  python3 scripts/skylit_bigmove_rank.py [--top 40] [--since 2024-01-01]

No API calls, no credits, no writes outside data/d2b/.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from collections import defaultdict

import pyarrow.parquet as pq

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEANDATA = "/Volumes/X10 Pro/leandata/parquet/stock_1min"
T012 = "/Volumes/X10 Pro/leandata/t012_tickers.txt"
OUT_CSV = os.path.join(REPO, "data", "d2b", "bigmove_day_rank.csv")
EXTRA = ["SPY", "QQQ", "IWM", "SPX"]

RTH_LO, RTH_HI = "09:30", "15:59"   # label-clock window, inclusive bounds


def liquid_tickers():
    names = list(EXTRA)
    try:
        txt = open(T012).read().strip()
        names += [t.strip().upper() for t in txt.split(",") if t.strip()]
    except OSError:
        pass
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:58]


def rth_mask(times):
    return [RTH_LO <= t[11:16] <= RTH_HI for t in times]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--since", default="2020-01-01")
    args = ap.parse_args()

    tickers = liquid_tickers()
    per_day = defaultdict(list)          # day -> [rth_pct, ...]
    full_day = defaultdict(list)         # day -> [full_pct, ...]
    files_read = 0
    for tk in tickers:
        pat = os.path.join(LEANDATA, f"ticker={tk}", "year=*.parquet")
        for f in sorted(glob.glob(pat)):
            base = os.path.basename(f)
            if base.startswith("._") or not base.endswith(".parquet"):
                continue
            try:
                t = pq.read_table(f, columns=["t", "h", "l", "c"])
            except Exception as e:
                print(f"  skip {f}: {e}", file=sys.stderr)
                continue
            files_read += 1
            times = t.column("t").to_pylist()
            hi = t.column("h").to_pylist()
            lo = t.column("l").to_pylist()
            cl = t.column("c").to_pylist()
            rth = rth_mask(times)
            day_rows = defaultdict(lambda: [None, None, None, 0,
                                            None, None, None, 0])
            # slots: rth_h, rth_l, rth_c0, rth_n, full_h, full_l, full_c0, full_n
            for i, ts in enumerate(times):
                d = ts[:10]
                if d < args.since:
                    continue
                if hi[i] is None or lo[i] is None or cl[i] is None:
                    continue
                slot = day_rows[d]
                # full session
                if slot[7] == 0:
                    slot[4], slot[5], slot[6] = hi[i], lo[i], cl[i]
                else:
                    slot[4] = hi[i] if slot[4] is None or hi[i] > slot[4] else slot[4]
                    slot[5] = lo[i] if slot[5] is None or lo[i] < slot[5] else slot[5]
                slot[7] += 1
                # RTH only
                if rth[i]:
                    if slot[3] == 0:
                        slot[0], slot[1], slot[2] = hi[i], lo[i], cl[i]
                    else:
                        slot[0] = hi[i] if slot[0] is None or hi[i] > slot[0] else slot[0]
                        slot[1] = lo[i] if slot[1] is None or lo[i] < slot[1] else slot[1]
                    slot[3] += 1
            for d, s in day_rows.items():
                if s[3] and s[2]:
                    per_day[d].append((s[0] - s[1]) / s[2])
                if s[7] and s[6]:
                    full_day[d].append((s[4] - s[5]) / s[6])
        print(f"  {tk}: done ({files_read} files so far)", flush=True)

    rows = []
    for d in sorted(per_day):
        v = per_day[d]
        f = full_day.get(d, [])
        vs = sorted(v)
        med = vs[len(vs) // 2]
        rows.append({"date": d, "n_tickers": len(v),
                     "mean_rth_pct_range": round(100 * sum(v) / len(v), 4),
                     "median_rth_pct_range": round(100 * med, 4),
                     "max_ticker_rth_pct_range": round(100 * max(v), 4),
                     "mean_full_pct_range": round(100 * sum(f) / len(f), 4)
                     if f else ""})
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {OUT_CSV} ({len(rows)} days, {files_read} files read)")

    top = sorted(rows, key=lambda r: -r["mean_rth_pct_range"])[:args.top]
    print(f"\nTOP {len(top)} big-move days (mean RTH pct range across "
          f"{rows[0]['n_tickers'] if rows else '?'}+ tickers):")
    for i, r in enumerate(top, 1):
        print(f"{i:3d}. {r['date']}  mean_rth={r['mean_rth_pct_range']:6.2f}%  "
              f"med={r['median_rth_pct_range']:6.2f}%  "
              f"max={r['max_ticker_rth_pct_range']:6.2f}%  "
              f"n={r['n_tickers']}  full={r['mean_full_pct_range']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
