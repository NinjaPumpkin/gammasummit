# leandata inventory — price/realized-vol history source

Source of truth: `/Volumes/X10 Pro/leandata/` (X10 root, NOT under `gammasummit/`).
**READ-ONLY** — never write, move, or delete anything under this path (standing
rule for every card). Cold-tier rclone sync into `/Volumes/X10 Pro/gammasummit/`
is planned in `../architecture/topology-linkage.md` (monthly); this doc only
inventories, it does not copy.

Verified 2026-10-01 by real pyarrow footer reads of every parquet file (scan:
~41.6k files, 0 read errors on real `*.parquet`; macOS `._*` AppleDouble sidecar
files fail footer reads and are junk, see Gotchas). Extraction was still
touching the tree that morning (`parquet/` dir mtime 2026-10-01 09:49), so
counts below are a snapshot, not a ceiling.

Why it matters (from `../architecture/skylit-product-inventory.md`): "leandata
realized" (Tempest realized vol), "leandata history" (IV rank baseline), "leandata
+ our levels" (Atlas charts), and E0.6 accumulation-history features all assume
this multi-year 2020→2026 history.

## Top level

```
/Volumes/X10 Pro/leandata/
├── parquet/                  140G allocated on disk (see "Disk vs payload")
│   ├── .backfill_state.json  extractor checkpoint ledger (3.3 MB, read-only!)
│   ├── .backfill_state.json.lock
│   ├── index_cboe_close/  index_daily/  index_minute/
│   ├── options_eod/  options_minute/
│   └── stock_1min/  stock_daily/
├── supabase_archive/         13G allocated
└── t012_tickers.txt          560-ticker T0/T1/T2 universe (one comma-separated line)
```

Partition map (IMPORTANT — half-Hive):

```
parquet/<dataset>/ticker=<T>/year=<Y>.parquet        # data
parquet/<dataset>/ticker=<T>/year=<Y>.parquet.lock   # extractor lock (empty)
```

`ticker=` is a directory level but `year=` lives in the FILE NAME, so
`pyarrow.dataset` hive partitioning does NOT see `year`. Use
`scripts/read_leandata.py` (derives both from path) or parse paths yourself.

## Datasets (row counts = parquet footer metadata, 2026-10-01)

| dataset | files | rows | logical bytes | tickers | coverage |
|---|---|---|---|---|---|
| stock_daily | 37,159 | 8,532,703 | 0.46 GB | 6,478 | 2016-01-04 → 2026-09-25 |
| stock_1min | 4,311 | 394,803,907 | 6.35 GB | 657 | 2020-01-01 → 2026-09-30 (per-ticker end dates vary) |
| index_minute | 84 | 8,107,670 | ~100 MB | 12 | 2020-01-02 → 2026-09-18 (SPX `ts` min/max; month windows complete through 2026-08) |
| index_daily | 28 | 6,760 | ~0.7 MB | 4 | 2020-01-02 → 2026-09-23 |
| index_cboe_close | 21 | 5,109 | ~0.1 MB | 3 | 2020-01-02 → 2026-09-25 |
| options_minute | 54 | 21,058,870 | ~32 MB | 54 | 2026-09-15T13:30Z → 2026-09-25T20:00Z (fetched_at 2026-09-27) |
| options_eod | 4 | 138,071 | small | 2 | **EXTRACTION IN PROGRESS — thin, see below** |

### stock_daily — 6,478 tickers × year files
Schema: `t: string` (ISO, e.g. `2016-01-04T05:00:00Z`), `o/h/l/c: double`,
`v: int64`, `n: int64` (transaction count), `vw: double` (VWAP), plus a
`ticker` dictionary column in some files.
Rows/ticker ≈ 2,692 (AAPL etc., full history). Year map (tickers per year):
2016–2019: 40 (long-history subset only) → 2020: 4,049 / 2021: 4,752 /
2022: 4,971 / 2023: 5,170 / 2024: 5,485 / 2025: 6,098 / 2026: 6,474.

### stock_1min — 657 tickers
Schema: `t: string` (ISO minute stamps), `o/h/l/c: double`, `v`, `n`, `vw`.
~395M rows total. Full years 2020–2026; per-ticker file present per year
(578 tickers in 2020 → 653 in 2026). Biggest: INTC 2.18M rows, PLTR 1.96M.
Timestamps look UTC-labelled (e.g. `t` max `2026-09-30T23:59:00Z`).

### index_minute — 12 indices
Tickers: DJI, DXY, NDX, RUT, SKEW, SPX, TNX, VIX, VIX3M, VIX6M, VVIX, VXN.
Schema: `ts: string` (`YYYY-MM-DD HH:MM:SS`), `o/h/l/c: double`,
`symbol: string`.
8.1M rows; SPX 680,770 rows, `ts` 2020-01-02 14:31 → 2026-09-18 15:50. Month
windows complete through 2026-08 per `.backfill_state.json` keys (Sept partial).

### index_daily — DJI, NDX, SPX, VIX
Schema: `date: string` (YYYY-MM-DD), `open/high/low/close: double`,
`bars: double` (minute-bars count per day, e.g. 405), `session_start`,
`session_end: string`, `symbol: string`. 1,690 rows/ticker. Ends 2026-09-23
(2-day lag vs index_cboe_close).

### index_cboe_close — settlement-quality closes: SPX, VIX, VIX3M
Schema: `date: string`, `close: double`, `open/high/low` present but
null-typed (close-only data). SPX 2020-01-02 → 2026-09-25 (1,692 rows);
VIX 1,725; VIX3M 1,692. Use for "our levels" / settlement-grade series.

### options_minute — 54 tickers, 2026 only (so far)
Tickers = exactly the first 54 entries of `t012_tickers.txt` (IWM, QQQ, SPX,
SPY, AAPL, AMD, …) — verified set-equal.
Schema: `occ: string` (OCC option symbol), `expiry: string`, `right: C/P`,
`t: string` (minute), `o/h/l/c: double`, `v: double`, `n: double`,
`fetched_at: string`. Top rows: SPX 3.03M, SPY 2.30M, QQQ 2.03M.

### options_eod — ⚠ EXTRACTION IN PROGRESS, thin coverage
Schema: `symbol, expiration, strike, right, created, last_trade, open, high,
low, close, volume, count, bid_size, bid_exchange, bid, bid_condition,
ask_size, ask_exchange, ask, ask_condition` (+ `ticker` dict col).
Full EOD chain quotes — the richest options schema here — but coverage is
currently a sliver:
- SPY: 137,461 rows in 3 year-files (2022, 2024, 2026); `created` spans
  2021-11-22 → 2026-09-24 but concentrated on a few expiry/strike windows
  (`.backfill_state.json` shows done windows like
  `options_eod/SPY/2026-09-25/760.0/2026-09-01/2026-09-24` — per
  expiry+strike month windows).
- QQQ: 610 rows, ONE window (2024-02-20 → 2024-04-19).
Do NOT treat as a complete EOD history yet; re-inventory when extraction stops.

## supabase_archive/ (SignalForge Supabase exports, gz CSV + SQL)

| file | rows (from .export_done.json) | bytes |
|---|---|---|
| phx_news.csv.gz | 471,133 | 218 MB |
| phx_analyst_ratings.csv.gz | 472,694 | 204 MB |
| phx_insider_trades.csv.gz | 426,995 | 4.1 GB |
| vexatrader_data_2026-09-25.sql.gz | — | **52 bytes — truncated/placeholder, unusable** |
| *.gen1 | same row counts as final | older/larger generation copies (dedupe candidates) |
| .phx_insider_trades.csv.gz.offset-era-partial | — | 3.9 GB partial-era artifact |
| .export_done.json / .shrink_gate.json | — | provenance: verified_at 2026-09-29T02:46:25Z, phx_cutoff 2026-08-30T02:46:25Z, live-vs-gz candidate counts matched (426,302 / 470,293 / 471,854) |

## Extraction provenance

- `parquet/.backfill_state.json` = extractor's checkpoint ledger: keys
  `<dataset>/<ticker>/<start>/<end>` (options_eod adds `<expiry>/<strike>`),
  value `true` when that window landed. Read it to check what's complete.
- Lock files (`*.parquet.lock`) = per-file extraction locks; empty.
- **Vendor/API: NOT recorded anywhere on disk** (no scripts, README, or logs
  live in or near the tree). Schema fingerprint HYPOTHESIS (unconfirmed):
  `o/h/l/c/v/n/vw` aggregates with ISO `t` strings strongly resemble
  Polygon.io-style bars, and `occ` symbology + `fetched_at` suggests a pull
  from an options data API — treat as a lead, not fact, until the owner names
  the vendor. No credentials needed for reading the local store; if a
  vendor API is later onboarded, keys go in `GAMMASUMMIT_*` env vars only.

## Disk vs payload (matters for cold-tier sync)

`du` reports 154G total but that is exFAT allocation (~1 MB clusters): true
logical payload ≈ 7 GB parquet + 13 GB supabase_archive. Parquet footers
report real sizes. Plan rclone/tiering budgets on logical sizes.

## Gotchas

- macOS junk everywhere: `._*` AppleDouble sidecars (4 KB, NOT parquet —
  skip or footer reads fail) and `._*.lock`. Filter: `not name.startswith("._")`.
- Type drift across years (use permissive concat):
  `options_eod.strike` is `int64` in QQQ/2024-era files but `double` in SPY
  files; `stock_1min` `v`/`n` vary int64 vs double across files. Cast on load.
- `index_cboe_close` `open/high/low` are null-typed columns — read `close` only.
- `t012_tickers.txt` is ONE comma-separated line (560 tickers), not
  newline-delimited.
- Timestamps are strings in every dataset (no timestamp-typed columns); string
  comparison works for ISO forms but mind the `+05:00/-04:00` offsets in
  `options_eod.created`/`last_trade`.

## Reading the data

`scripts/read_leandata.py` — read-only loader (pyarrow), path-derived
ticker/year, filters, CSV/summary output. Examples:

```
python3 scripts/read_leandata.py --summary stock_daily --ticker AAPL
python3 scripts/read_leandata.py --summary index_cboe_close --ticker SPX
python3 scripts/read_leandata.py --csv stock_1min --ticker NVDA --year 2026 \
    --since 2026-09-25 --until 2026-09-30 > /tmp/nvda.csv
python3 scripts/read_leandata.py --files options_eod --ticker SPY
```

Root override: `GAMMASUMMIT_LEANDATA_ROOT` (default `/Volumes/X10 Pro/leandata`).
