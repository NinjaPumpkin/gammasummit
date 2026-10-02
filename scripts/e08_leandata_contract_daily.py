#!/usr/bin/env python3
"""E0.8 — per-contract daily aggregates from the leandata RE reference archive.

READ-ONLY against /Volumes/X10 Pro/leandata (never writes there). Emits one
unified dataset to data/e08/leandata_contract_daily.parquet with the
ContractStats-style row shape (docs/re/skylit-docs bulk contract stats) where
the source supports it:

  source       'eod'    <- options_eod full EOD chain quotes (SPY/QQQ, thin windows)
               'minute' <- options_minute minute bars aggregated to day (54 tickers)
  ticker       underlying
  occ          canonical bare OCC symbol (e.g. SPY261001C00761000)
  expiry, right (C/P), date (ISO trade date)
  volume, trade_count, premium, close_price, bid, ask
  oi, prev_oi, bid_volume, ask_volume, mid_volume  -> NULL in leandata (no OI /
               no execution-side split in either source; honest gap)

Premium proxies (documented, not vendor premium):
  eod:     close * volume * 100, fallback mid((bid+ask)/2) when close==0 & vol>0
  minute:  sum over minute bars of v * c * 100 (zero-price bars skipped for px)

Usage:
  python3 scripts/e08_leandata_contract_daily.py            # build + report
  python3 scripts/e08_leandata_contract_daily.py --out data/e08/leandata_contract_daily.parquet
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEANDATA = "/Volumes/X10 Pro/leandata/parquet"
OUT_DEFAULT = os.path.join(ROOT, "data", "e08", "leandata_contract_daily.parquet")

UNIFIED_COLS = [
    "source", "ticker", "occ", "expiry", "right", "date",
    "volume", "trade_count", "premium", "close_price", "bid", "ask",
    "oi", "prev_oi", "bid_volume", "ask_volume", "mid_volume",
]


def occ_symbol(ticker: str, expiry: str, right: str, strike) -> str:
    """Bare OCC: {ticker}{YYMMDD}{C|P}{strike*1000:08d}."""
    ymd = expiry.replace("-", "")[2:]  # YYMMDD
    r = "C" if str(right).upper().startswith("C") else "P"
    return f"{ticker}{ymd}{r}{int(round(float(strike) * 1000)):08d}"


def _files(dataset: str) -> list[str]:
    pats = glob.glob(os.path.join(LEANDATA, dataset, "ticker=*", "*.parquet"))
    return sorted(f for f in pats if not os.path.basename(f).startswith("._"))


def build_eod() -> tuple[pd.DataFrame, dict]:
    frames, rep = [], {"files": 0, "rows_raw": 0}
    for f in _files("options_eod"):
        df = pq.read_table(f, columns=[
            "expiration", "strike", "right", "created", "volume", "count",
            "close", "bid", "ask"]).to_pandas()
        rep["files"] += 1
        rep["rows_raw"] += len(df)
        tk = f.split("ticker=")[1].split("/")[0]
        df["ticker"] = tk
        df["date"] = df["created"].astype(str).str[:10]
        df["right"] = df["right"].astype(str).str.upper().str[0]  # CALL/PUT -> C/P
        vol = df["volume"].astype(float)
        px = df["close"].astype(float)
        mid = (df["bid"].astype(float) + df["ask"].astype(float)) / 2.0
        use_mid = (px <= 0) & (vol > 0)
        px_eff = px.where(~use_mid, mid)
        out = pd.DataFrame({
            "source": "eod",
            "ticker": df["ticker"],
            "occ": [occ_symbol(t, e, r, s) for t, e, r, s in
                    zip(df["ticker"], df["expiration"], df["right"], df["strike"])],
            "expiry": df["expiration"].astype(str).str[:10],
            "right": df["right"],
            "date": df["date"],
            "volume": vol,
            "trade_count": df["count"].astype(float),
            "premium": px_eff * vol * 100.0,
            "close_price": px_eff,
            "bid": df["bid"].astype(float),
            "ask": df["ask"].astype(float),
        })
        frames.append(out)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()), rep


def build_minute() -> tuple[pd.DataFrame, dict]:
    frames, rep = [], {"files": 0, "rows_raw": 0}
    for f in _files("options_minute"):
        df = pq.read_table(f, columns=["occ", "expiry", "right", "t", "c", "v", "n"]).to_pandas()
        rep["files"] += 1
        rep["rows_raw"] += len(df)
        tk = f.split("ticker=")[1].split("/")[0]
        df["ticker"] = tk
        df["date"] = df["t"].astype(str).str[:10]
        df["right"] = df["right"].astype(str).str.upper().str[0]
        v = df["v"].astype(float)
        c = df["c"].astype(float)
        df["_prem"] = v * c * 100.0
        df["_pxnum"] = v * c.where(c > 0, 0.0)
        g = df.groupby(["ticker", "occ", "expiry", "right", "date"], sort=False)
        agg = g.agg(volume=("v", "sum"), trade_count=("n", "sum"), premium=("_prem", "sum"),
                    vol_px=("_pxnum", "sum")).reset_index()
        agg["close_price"] = (agg["vol_px"] / agg["volume"].where(agg["volume"] > 0)).fillna(0.0)
        agg = agg.drop(columns=["vol_px"])
        agg["source"] = "minute"
        agg["bid"] = None
        agg["ask"] = None
        frames.append(agg)
    out = (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())
    return out, rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args()

    if not os.path.isdir(LEANDATA):
        raise SystemExit(f"leandata archive not mounted: {LEANDATA}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    report = {"leandata_root": LEANDATA, "read_only": True}

    eod, rep_eod = build_eod()
    report["eod"] = {**rep_eod, "rows_out": len(eod),
                     "tickers": sorted(eod["ticker"].unique()) if len(eod) else [],
                     "date_min": eod["date"].min() if len(eod) else None,
                     "date_max": eod["date"].max() if len(eod) else None}
    minute, rep_min = build_minute()
    report["minute"] = {**rep_min, "rows_out": len(minute),
                        "n_tickers": int(minute["ticker"].nunique()) if len(minute) else 0,
                        "date_min": minute["date"].min() if len(minute) else None,
                        "date_max": minute["date"].max() if len(minute) else None}

    both = pd.concat([eod, minute], ignore_index=True)
    for c in ("oi", "prev_oi", "bid_volume", "ask_volume", "mid_volume"):
        both[c] = None
    both = both[UNIFIED_COLS]
    table = pa.Table.from_pandas(both, preserve_index=False)
    pq.write_table(table, args.out)

    fn_rep = os.path.join(os.path.dirname(args.out), "leandata_contract_daily_report.json")
    with open(fn_rep, "w") as f:
        json.dump(report, f, indent=1)

    print(json.dumps(report, indent=1))
    print(f"wrote {args.out} rows={len(both)}")
    print(f"wrote {fn_rep}")


if __name__ == "__main__":
    main()
