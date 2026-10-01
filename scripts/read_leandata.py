#!/usr/bin/env python3
"""read_leandata.py — READ-ONLY loader for the leandata cold-tier store.

Source of truth: /Volumes/X10 Pro/leandata/  (NEVER write to it — standing rule).

Layout notes (verified 2026-10-01, see docs/data/leandata-inventory.md):
  parquet/<dataset>/ticker=<T>/year=<Y>.parquet   (+ sibling year=<Y>.parquet.lock)
  - "ticker=" is a directory level (Hive-ish), but "year=" lives in the FILE
    NAME, not a directory — pyarrow.dataset hive partitioning will NOT pick up
    year. This loader derives ticker/year from the path manually.
  - Skip macOS junk: files starting with "._" and "*.lock" are not parquet.
  - parquet/.backfill_state.json is the extractor's checkpoint ledger
    (dataset/ticker/date-window -> done). Read it to see extraction coverage;
    it is a ledger, not data.

Datasets + time columns (auto-detected):
  stock_daily, stock_1min    -> t   (ISO strings, UTC-ish)
  index_daily                -> date (string YYYY-MM-DD)
  index_cboe_close           -> date (string)
  index_minute, options_minute -> t (ISO strings); index_minute actually uses
                                "ts" (ISO strings) — auto-detected
  options_eod                -> created / last_trade (strings; no per-row date —
                                use --years / --tickers file selection instead)

Usage:
  python3 scripts/read_leandata.py --summary stock_daily --ticker AAPL
  python3 scripts/read_leandata.py --head options_minute --ticker SPY --limit 5
  python3 scripts/read_leandata.py --csv index_cboe_close --ticker SPX \\
      --since 2026-09-01 --until 2026-09-30 > /tmp/spx_sep.csv

Output goes to stdout only. No writes anywhere except explicitly via shell
redirect. Non-destructive by construction: opened with pq.read_table / ParquetFile.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Iterable, Optional

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

LEANDATA_ROOT = os.environ.get("GAMMASUMMIT_LEANDATA_ROOT", "/Volumes/X10 Pro/leandata")
PARQUET_ROOT = os.path.join(LEANDATA_ROOT, "parquet")

TIME_COLS = ("t", "date", "ts", "created", "last_trade")


def _is_junk(name: str) -> bool:
    return name.startswith("._") or name.endswith(".lock")


def list_files(
    dataset: str,
    tickers: Optional[Iterable[str]] = None,
    years: Optional[Iterable[str]] = None,
) -> list[tuple[str, str, str]]:
    """Return [(path, ticker, year)] for a dataset, sorted. Read-only walk."""
    ds_dir = os.path.join(PARQUET_ROOT, dataset)
    if not os.path.isdir(ds_dir):
        raise SystemExit(f"no such dataset: {ds_dir}")
    want_t = {t.upper() for t in tickers} if tickers else None
    want_y = {str(y) for y in years} if years else None
    out = []
    for dirpath, _dirnames, filenames in os.walk(ds_dir):
        for fn in sorted(filenames):
            if not fn.endswith(".parquet") or _is_junk(fn):
                continue
            m_t = re.search(r"ticker=([^/]+)", dirpath)
            m_y = re.search(r"year=(\d{4})", fn)
            ticker = m_t.group(1) if m_t else ""
            year = m_y.group(1) if m_y else ""
            if want_t and ticker.upper() not in want_t:
                continue
            if want_y and year not in want_y:
                continue
            out.append((os.path.join(dirpath, fn), ticker, year))
    return sorted(out)


def load(
    dataset: str,
    tickers: Optional[Iterable[str]] = None,
    years: Optional[Iterable[str]] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    time_col: Optional[str] = None,
) -> pa.Table:
    """Concatenate matching parquet files into one Arrow table (read-only)."""
    files = list_files(dataset, tickers, years)
    if not files:
        raise SystemExit(f"no files match dataset={dataset} tickers={tickers} years={years}")
    tables = []
    tcol = time_col
    for path, _tk, _yr in files:
        tbl = pq.read_table(path)
        if tcol is None:
            for cand in TIME_COLS:
                if cand in tbl.column_names:
                    tcol = cand
                    break
        if (since or until) and tcol:
            col = tbl[tcol]
            # bare YYYY-MM-DD until bound must include the whole day when the
            # time column carries time-of-day (string compare semantics)
            until_eff = until
            if until and len(until) == 10:
                until_eff = until + "T23:59:59.999999"
            mask = None
            if since:
                mask = pc.greater_equal(col, pa.scalar(since, col.type))
            if until_eff:
                up = pc.less_equal(col, pa.scalar(until_eff, col.type))
                mask = up if mask is None else pc.and_(mask, up)
            tbl = tbl.filter(mask)
        # provenance columns derived from path (files do not carry ticker/year)
        n = tbl.num_rows
        tbl = tbl.append_column("_ticker", pa.array([_tk] * n, pa.string()))
        tbl = tbl.append_column("_year", pa.array([_yr] * n, pa.string()))
        tables.append(tbl)
    return pa.concat_tables(tables, promote_options="permissive")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", help="one of the parquet/<dataset> dirs")
    ap.add_argument("--ticker", action="append", help="filter ticker (repeatable)")
    ap.add_argument("--year", action="append", help="filter year (repeatable)")
    ap.add_argument("--since", help="inclusive lower bound on time col (string compare on ISO)")
    ap.add_argument("--until", help="inclusive upper bound on time col")
    ap.add_argument("--time-col", help="override auto-detected time column")
    ap.add_argument("--limit", type=int, default=10, help="rows for --head (default 10)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--summary", action="store_true", help="row counts + date coverage")
    mode.add_argument("--head", action="store_true", help="first N rows as CSV")
    mode.add_argument("--csv", action="store_true", help="full CSV to stdout")
    mode.add_argument("--files", action="store_true", help="list matching files only")
    args = ap.parse_args()

    if args.files:
        for path, tk, yr in list_files(args.dataset, args.ticker, args.year):
            print(f"{yr}\t{tk}\t{path}")
        return 0

    tbl = load(args.dataset, args.ticker, args.year, args.since, args.until, args.time_col)
    if args.summary:
        tcol = args.time_col or next((c for c in TIME_COLS if c in tbl.column_names), None)
        print(f"dataset={args.dataset} rows={tbl.num_rows} cols={len(tbl.column_names)}")
        print(f"schema: {tbl.schema}")
        if tcol:
            col = tbl[tcol]
            print(f"time col {tcol}: min={pc.min(col).as_py()} max={pc.max(col).as_py()}")
        for prov in ("_ticker", "_year"):
            if prov in tbl.column_names:
                uniq = pc.unique(tbl[prov]).to_pylist()
                print(f"{prov}: {len(uniq)} -> {sorted(uniq)[:20]}")
        return 0

    if args.head:
        tbl = tbl.slice(0, args.limit)
    pacsv.write_csv(tbl, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
