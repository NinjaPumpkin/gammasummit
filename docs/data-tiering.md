# Data Tiering

Owner-locked 2026-09-30. Raw retention tightened to 24–48h same day ("use as
little overhead as possible").

## Tiers

| Tier | Content | Retention | Store | Consumers |
|------|---------|-----------|-------|-----------|
| T0 | raw full-cadence snapshots (top-200 live tickers) | **24–48h** | Postgres | live view, intraday scrub, downsampler input |
| T1 | 5-min per-strike/expiry buckets + per-strike EOD | 30d | Postgres | dashboards, charts |
| T2 | hourly rollups + EOD chains (OI, volume, GEX per strike per day) | 90d–1yr | Postgres | history charts, on-demand queries |
| T3 | full-fidelity raw, Parquet | indefinite | external disk + B2/R2 copy | DuckDB backtests / research |

## Why the raw tier is tiny

Measured (2026-09-30, SignalForge production): ~3–6 GB/day raw universe-wide,
SPX alone 1.0–1.5M rows/day. 30d raw ≈ 100–250 GB = unaffordable and
unnecessary: intraday chart scrubbing only needs the current + previous
session. Everything else is answerable from buckets and rollups.

## Jobs (all in `backend/jobs/`, idempotent + retryable)

| Job | Trigger | Action |
|-----|---------|--------|
| downsampler | continuous / every 5 min | T0 → T1 buckets (dedupe unchanged strikes) |
| rollups | hourly + EOD | T1 → T2 hourly and per-strike EOD |
| retention | daily | T0 rows older than 48h → Parquet export → delete (export-first!) |
| export | daily | Parquet files → external disk + B2/R2 sync (3-2-1) |
| lazy backfill | on-demand (API trigger) | fetch + write T0/T1 for long-tail ticker, cache 24h |

## Universe policy

- Collect: all tickers available from Unusual Whales (~609 today).
- **Top 200 LIVE**: intraday T0/T1. Ranked by trailing 20d options volume/OI,
  recomputed monthly (1st of month).
- **Long tail**: T2 EOD always maintained; intraday only via lazy backfill.

## Rules

- Rollups recomputable from T0 (within 48h) or T3 (after export). Never a
  third source of truth.
- No dashboard/API query may scan raw T0 across more than one ticker.
- Retention never deletes un-exported data. Verified export manifest before
  delete (per `docs/operations.md`).
