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

**2026-10-02 update (D3, `scripts/leandata_extract.py`):** extraction resumed
under a mandated throttle and is closing the t012 coverage gaps into a LOCAL
staging archive (see "Extraction pipeline" below); the X10 drive had a
device-level hang 2026-10-02 08:47–~11:20 (root cause of the two crashed
extractor runs) and recovered after eject/remount — `scripts/leandata_x10_merge.py`
merges staging → X10 when healthy. Live coverage is tracked in
`../../data/leandata-coverage-report.json` (staging) + `leandata-pull-manifest.json`
(requests/caps/incidents).

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

## Extraction provenance (RESOLVED 2026-10-02)

- `parquet/.backfill_state.json` = extractor's checkpoint ledger: keys
  `<dataset>/<ticker>/<start>/<end>` (options_eod adds `<expiry>/<strike>`),
  value `true` when that window landed. Read it to check what's complete.
  `skipped: ...` = permanent skip; `error: ...` = retryable.
- Lock files (`*.parquet.lock`) = per-file extraction locks; empty.
- **Vendor: `https://api.leandata.uk` ("Leandata" IS the vendor — the
  Polygon-style fingerprint below was a red herring; Leandata proxies Alpaca,
  responses carry `x-upstream-provider: alpaca`, paid tier).** Auth:
  `LEANDATA_TOKEN` bearer — value lives ONLY in an untracked `.env.local`
  (`SignalForge/dashboard-next/.env.local`) and is read at runtime; never in
  git/chat. Full API reference (endpoints, quirks, batching, rate behavior):
  `market-data-pipelines/references/leandata-api.md` (Hermes skills).
- **Extractor suite (the code that wrote this tree):** `scripts/leandata_*.py`
  in the **SignalForge repo** (`leandata_backfill.py` main writer +
  `leandata_options_minute.py`, `leandata_options_sweep.py`,
  `leandata_index_extras.py`, `leandata_daily_snapshot.py`). Run read-only;
  the D3 resume wraps them via importlib from
  `gammasummit/scripts/leandata_extract.py` (no SignalForge file modified,
  state-key shapes and parquet writer reused verbatim → byte-compatible
  archives).
- Rate behavior (measured, see leandata-api.md): the binding cap is
  per-user CONCURRENCY = 3 account-wide (no rpm published); `429
  historical_concurrency_limit` beyond that.

## Disk vs payload (matters for cold-tier sync)

`du` reports 154G total but that is exFAT allocation (~1 MB clusters): true
logical payload ≈ 7 GB parquet + 13 GB supabase_archive. Parquet footers
report real sizes. Plan rclone/tiering budgets on logical sizes.

## t012 universe (reconstructed 2026-10-02)

`t012_tickers.txt` (560 names, one comma-separated line, ordered T0,T1,T2)
lived ONLY on X10. Reconstructed from the Supabase `ticker_universe` tier
table (T0=4, T1=50, T2=506 → 560 ✓) and validated against the 2026-10-01
coverage scan: T0+T1 is set-equal to the known 54 options_minute roots ✓, and
the reconstructed missing sets reproduce the D3 gap counts exactly
(stock_daily 38 / stock_1min 128 / options_minute 506 / options_eod 558) ✓.
Durable copies: `../../data/t012_tickers.txt` (same one-line format) and
`../../data/t012_universe.json` (names + tiers). Within-tier order is by
`activity_score` desc — the original file's within-tier order is unknown
(cosmetic: only the T0+T1 vs T2 split is load-bearing).

## Extraction pipeline (2026-10-02, D3 resume)

- Driver: `../../scripts/leandata_extract.py` — wraps the proven SignalForge
  extractor suite (importlib, read-only) with the owner/PM-mandated throttle:
  * **1 in-flight request** (≤50% of the documented account-wide concurrency
    cap of 3) + ≥1.0 s + U(0, 0.5) s jitter between request starts (no rpm
    cap is published — conservative self-imposed spacing);
  * rate signal (429/403/rate-ish body) → exponential cooldown 300→1800 s,
    retry ONCE, **abort the run on the second signal** (stop-on-first-sign,
    never a retry-storm; the vendor scripts' 5×429-retry default is
    overridden); `invalid_token*` never retried;
  * **daily request cap 20,000** (env `LEANDATA_DAILY_CAP`) enforced from
    `leandata-pull-manifest.json`, which counts every request per endpoint
    per day and records incidents — the counter survives restarts;
  * single-instance flock (`.extract.lock`) — two drivers would break the
    ≤50% rule, so a second instance exits.
- Continuation daemon: Hermes cron `leandata-extract-daemon`
  (`23ba92d6e28f`, script-only, every 4 h) runs
  `../../scripts/leandata_daemon_tick.sh`: merge staging → X10 when the
  drive answers, re-derive gap lists, relaunch the driver if idle. When
  coverage is complete the driver is a cheap no-op (state skips).
- Job order: stock_daily gaps → stock_1min gaps (2-symbol monthly batches) →
  options_eod breadth baseline → options_minute T2 grind (8-OCC batches,
  `--max-batches-per-root 12` breadth-first; later passes deepen).
- The 2-symbol batching for stock bars and 8-OCC batching for option minute
  bars are load-bearing (3+ symbols silently collapse to 1000-row paginated
  mode; see leandata-api.md quirks).

## Coverage gaps & honest budgets (as of 2026-10-02)

**Checkpoint 2026-10-02 ~13:45 PT** (staging `../../data/leandata-parquet`,
full machine-readable snapshot `../../data/leandata-coverage-report.json`):

| dataset | staging tickers | files | rows | status |
|---|---|---|---|---|
| stock_daily | 35 | 362 | 88,164 | **38-gap CLOSED** (38/38 terminal state keys) |
| stock_1min | 2 | 8 | 976,907 | grinding (PCG/TQQQ partial; 126 names queued) |
| options_eod | 10 | 10 | 1,694 | breadth baseline in progress (9 roots done @ ~75 s/root) |
| options_minute | 0 | 0 | 0 | queued (card-priority order: breadth first) |

Requests today 1,650 · 0 rate signals · 0 incidents (manifest).

Gap lists are regenerated from the live X10 tree into `data/missing_<ds>.txt`
by `leandata_x10_merge.py --derive-only` (authoritative). What is achievable
at ≤50%-of-limit pacing (~1 call / 1.3 s ≈ 2700 calls/h, 20k/day cap):

| work | calls | verdict |
|---|---|---|
| stock_daily 38 gaps | ~110 (paginated) | **done in staging 2026-10-02** (35 fetched, 2 index-routed, 1 vendor `archive_miss` = RUTW) |
| stock_1min 128 gaps | **~1e5 pages, not ~5.2k** — the 2-symbol batch still paginates at ~1000 rows/page for liquid pairs (measured ~30 pages per pair-month, e.g. PCG+TQQQ), so 64 pairs × 81 months × ~30 pages ≈ 1.5e5 | **multi-day at the 20k/day cap** (≈5–8 days) — daemon-owned, measured not estimated |
| options_eod breadth baseline (558 roots × 1 monthly expiry × 7 strikes × 1 ≤21d chunk + spot/chain discovery) | ~5k | feasible within ~1 day of budget |
| options_eod DEPTH (full strike bands × all expiries × history) | ~1e6+ | **NOT attempted** — months of wall-clock at compliant pacing; documented, not fabricated |
| options_minute T2 (506 roots, nearest-2 expiries, full tape per contract) | ~13k+ (page counts to be measured as it runs) | multi-day at cap; daemon grinds it |

Call-page reality (measured 2026-10-02): `/v1/history/bars` pages at ~1000
rows and the 2-symbol "full month in one response" quirk does NOT hold for
all pairs — budget at page level, never at window level.

**Progress checkpoint 2026-10-02 ~11:55 PT** (D3b verification pass):

- **X10 merge EXECUTED 11:47 PT** (pgrep-gated: extractor idle): 409 files
  copied staging→X10, 424 state-ledger keys unioned. Row-dedup verified on
  22 sample parquet footers before/after — identical row counts (only diff =
  output line ordering). Post-merge derive vs t012: `stock_daily` 38→**3**,
  `stock_1min` 128→**126**, `options_eod` 558→**519**, `options_minute` 506.
- Residual `stock_daily` 3 = **SPX, VIX** (index roots — real data lives in
  `index_daily`) + **RUTW** (vendor `archive_miss`): 38/38 terminal state
  keys, unbackfillable in `stock_daily` by definition. Honest remainder.
- **Depth-integrity patch** (`scripts/leandata_extract.py`, throttle
  UNCHANGED per owner hard rule):
  1. grind-list guard — tickers the pipeline started but has not finished
     stay on the grind list even after a merge makes them 'present' in X10
     (the merge-time re-derived gap lists are breadth-based and previously
     truncated in-progress depth silently). Proven live at relaunch:
     `grind-list stock_1min: +2 in-progress tickers kept`,
     `grind-list options_eod: +1 in-progress tickers kept`.
  2. stock_1min breadth anchors (2026-06, 2025-06, 2024-06 month windows,
     exact `months()` key shapes) land one month per ticker BEFORE the full
     depth pass — so X10 ticker-presence (the `missing → 0` metric) closes
     within the first ~2k calls of the stock_1min job instead of after all
     64 pairs' full 81-month depth (~1.5e5 pages).
  Offline verification: 13/13 guard cases + anchor⊂depth key-set equality.
  Residual risk (accepted, documented): a ticker hard-killed mid-window
  before any state key is written can lose tail months once merged — ~1
  ticker-window per hard kill, tracked via the state ledger.

The full-history options_eod sweep (the `leandata_options_sweep.py` shape:
every weekday × ±8 strikes × 3 chunks per root) is the known unreachable
item: it is call-volume-bound, not quota-blocked. The breadth baseline gives
every t012 root a real EOD window now; depth accrues via the daemon and any
future budget increase (a documented vendor concurrency raise would change
this table).

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
