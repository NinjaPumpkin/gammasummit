# GammaSummit Architecture

## Data flow

```
UW / PHX / IBKR
      │
      ▼
ingest daemon (VPS systemd gammasummit-ingest)
      │
      ├─► T0 raw snapshots (Postgres, 24–48h) ──retention job──► Parquet export
      │                                                          │
      ├─► downsampler job ──► T1 5-min buckets (30d)             │
      │        │                                                ▼
      │        └─► rollup jobs ──► T2 hourly+EOD (90d–1yr)  external disk
      │                                │                     (+ B2/R2 copy)
      │                                │                          │
      │                                │                          ▼
      │                                │                    DuckDB (backtests,
      │                                │                    on-demand research)
      ▼                                ▼
   API layer (VPS) ◄── reads T0/T1/T2 + cache
      │
      ▼
   frontend ──► API only, never the database directly

lazy path: user opens long-tail ticker
      → API enqueues backfill job → result cached 24h
```

## Components

| Component | Responsibility | Runs on |
|-----------|----------------|---------|
| ingest daemon | fetch + write T0, trigger downsampling | VPS (systemd) |
| job workers | downsampler, rollups, retention/export, lazy backfill | VPS |
| API | authenticated read surface + job triggers | VPS (docker) |
| Postgres (Supabase) | T0/T1/T2 only — small, hot, indexed | Supabase |
| cold storage | Parquet archive | external disk + B2/R2 |
| DuckDB | analytics over Parquet | wherever a researcher runs |
| frontend | dashboard UI | static hosting / VPS |

## Storage design rules

- One table per entity, partitioned by ticker (list) + time (range).
- `timestamptz` and `date` types — never text timestamps.
- Composite indexes `(ticker, timestamp DESC)` on time-series tables.
- Rollups are append-only, recomputable from T0 while T0 exists; after that,
  recompute only from T3 (rare, expensive, deliberate).
- No view or query in the request path may scan raw T0 tables for >1 ticker.

## Security model (summary — full spec: `docs/ops/security.md`)

- Frontend → API → database. The database has no public read surface.
- Deny-by-default grants; service credentials live only in server env.
- Rate limiting + security headers at the API edge.
- Input validation on every parameter (tickers, dates, ranges).

## Technology choices (locked)

| Concern | Choice | Why |
|---------|--------|-----|
| Hot DB | Postgres via Supabase (slim) | managed backups, small hot set keeps it cheap |
| Cold format | Parquet | columnar, portable, DuckDB-native |
| Cold analytics | DuckDB | 10–100× faster than Postgres for backtests |
| Language | Python 3.10 | VPS constraint; re-check when VPS changes |
| API | FastAPI (planned) | async, OpenAPI from code (ch.25) |
| Jobs | in-process queue + cron/systemd timers | no broker until proven needed (ch.10) |
| Realtime | SSE/WebSocket via API | subscriptions only for live session (ch.24) |

## Non-goals (v1)

- No multi-region, no microservices, no message broker, no Kubernetes.
- No commercial data redistribution (owner decision 2026-07-27, inherited).
- No 5,900-symbol capacity design — universe = what UW provides (~609).
