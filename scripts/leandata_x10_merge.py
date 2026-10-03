#!/usr/bin/env python3
"""leandata_x10_merge.py — merge the local staging archive back into X10.

The 2026-10-02 extraction wrote to the LOCAL staging archive
(data/leandata-parquet) because the X10 Pro drive was device-unresponsive
(raw /dev reads hang). When the drive is healthy again (physical replug),
this script:

  1. checks X10 responsiveness with a bounded probe (never hangs the shell);
  2. copies every staging parquet file into the X10 tree
     (/Volumes/X10 Pro/leandata/parquet/<dataset>/ticker=XX/year=YYYY.parquet),
     merging rows when a destination file already exists (concat +
     exact-duplicate drop + stable time sort — same semantics as the
     extractor's write_parquet), under per-file advisory locks;
  3. unions the .backfill_state.json ledgers (dest |= src; keys are
     dataset/window shaped and independent jobs may hold disjoint keys);
  4. re-derives the per-dataset missing ticker lists vs the t012 universe
     from the LIVE X10 directory listing and writes data/missing_<ds>.txt
     (this is the authoritative gap list — incl. the stock_1min 128-name
     gap whose list was lost when the coverage scan was scratch-pruned);
  5. never deletes, never moves, never touches supabase_archive/.

Standing rules: --dry-run default, --execute to apply. The X10 leandata tree
is otherwise read-only for every other card — THIS script is the sanctioned
writer for extraction output only (D3 task t_427942b6).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

X10 = "/Volumes/X10 Pro/leandata/parquet"
STAGING = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "leandata-parquet")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T012 = os.path.join(REPO, "data", "t012_universe.json")
DATASETS = ("stock_daily", "stock_1min", "options_minute", "options_eod")


def probe_x10(timeout_s: float = 20.0) -> bool:
    """True when the X10 tree answers a directory listing quickly."""
    import subprocess
    try:
        r = subprocess.run([sys.executable, "-c",
                            f"import os; os.listdir({X10!r})"],
                           capture_output=True, timeout=timeout_s)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def merge_parquet(src: str, dst: str, dry_run: bool) -> str:
    """'copied' | 'merged' | 'would-copy' | 'would-merge'."""
    import fcntl
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not os.path.exists(dst):
        if dry_run:
            return "would-copy"
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return "copied"
    # an existing destination that is newer and at least as large has already
    # been merged/copied past this source — skip so repeat ticks stay cheap
    sst, dstt = os.stat(src), os.stat(dst)
    if dstt.st_mtime >= sst.st_mtime and dstt.st_size >= sst.st_size:
        return "skip-present"
    if dry_run:
        return "would-merge"
    with open(dst + ".lock", "a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        a = pq.read_table(dst).to_pandas()
        b = pq.read_table(src).to_pandas()
        df = pd.concat([a, b], ignore_index=True).drop_duplicates(keep="first")
        sort_col = next((c for c in ("t", "created", "last_trade")
                         if c in df.columns), None)
        if sort_col is not None:
            df = df.sort_values(sort_col, kind="stable")
        t = pa.Table.from_pandas(df, schema=None, preserve_index=False)
        pq.write_table(t.combine_chunks(), dst, compression="zstd")
        fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    return "merged"


def merge_state(dry_run: bool) -> tuple[int, int]:
    sp = os.path.join(STAGING, ".backfill_state.json")
    dp = os.path.join(X10, ".backfill_state.json")
    src = json.load(open(sp)) if os.path.exists(sp) else {}
    dst = json.load(open(dp)) if os.path.exists(dp) else {}
    new = {k: v for k, v in src.items() if k not in dst}
    if not dry_run and new:
        dst.update(src)
        tmp = dp + ".tmp"
        with open(tmp, "w") as f:
            json.dump(dst, f)
        os.replace(tmp, dp)
    return len(src), len(new)


def derive_missing(dry_run: bool) -> dict[str, int]:
    t012 = json.load(open(T012))["t012"]
    out = {}
    for ds in DATASETS:
        base = os.path.join(X10, ds)
        present = set()
        if os.path.isdir(base):
            present = {ent.split("=", 1)[1] for ent in os.listdir(base)
                       if ent.startswith("ticker=")}
        missing = [t for t in t012 if t not in present]
        out[ds] = len(missing)
        path = os.path.join(REPO, "data", f"missing_{ds}.txt")
        if dry_run:
            print(f"[dry-run] would write {path}: {len(missing)} tickers")
        else:
            with open(path, "w") as f:
                f.write("\n".join(missing) + "\n")
        print(f"{ds}: present={len(present)} missing_t012={len(missing)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true",
                    help="actually merge + write (default is dry-run)")
    ap.add_argument("--derive-only", action="store_true",
                    help="only re-derive data/missing_*.txt from the live X10 "
                         "tree (read-only) — no file/state merge")
    args = ap.parse_args()
    dry_run = not args.execute

    if not probe_x10():
        print("X10 NOT RESPONSIVE — fix the drive (physical replug / power) "
              "and retry. Nothing done.")
        return 2

    if args.derive_only:
        derive_missing(dry_run)
        return 0

    counts: dict[str, int] = {}
    for ds in DATASETS:
        sbase = os.path.join(STAGING, ds)
        if not os.path.isdir(sbase):
            continue
        for ent in sorted(os.listdir(sbase)):
            if not ent.startswith("ticker="):
                continue
            tdir = os.path.join(sbase, ent)
            for fn in sorted(os.listdir(tdir)):
                if not fn.endswith(".parquet") or fn.startswith("._"):
                    continue
                src = os.path.join(tdir, fn)
                dst = os.path.join(X10, ds, ent, fn)
                res = merge_parquet(src, dst, dry_run)
                counts[res] = counts.get(res, 0) + 1
    print("file actions:", counts)

    n_src, n_new = merge_state(dry_run)
    print(f"state: src_keys={n_src} new_for_x10={n_new}")

    derive_missing(dry_run)
    print("DRY-RUN complete — nothing written." if dry_run else "MERGE complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
