# Risks, Pitfalls, and Toolkit — pre-build ultra-think

Problems we can anticipate now, how we avoid each, and the open-source tool
that does the job. Lean rule: a tool enters only if it replaces custom code or
a past failure.

## Data pipeline risks

| Risk (we've hit or will hit) | Avoidance | Tool |
|---|---|---|
| UW rate limits / API budget burn | request budgets + circuit breaker + backoff w/ jitter (ch.10/12) | `tenacity` |
| Backfill double-writes / duplicates | conflict-key idempotent upserts (already the SignalForge pattern) | `asyncpg` + ON CONFLICT |
| **Timezone/DTE bugs** (hit in SignalForge: "DTE tz" fix) | store `timestamptz` UTC, compute DTE in ET **in code**, never in SQL | tests incl. half-days/holidays |
| Weekend/backfill spike double-counting (open question 09-26/27) | downsampler dedupes on (ticker, strike, expiry, bucket) | unique keys |
| Retention deletes un-exported data | manifest-verified export-first (operations.md) | checksum manifests |
| Stale rollups unnoticed | freshness metric = deep health check + alert | Uptime Kuma (self-host, OSS) |

## Database efficiency

| Technique | Effect | Where |
|---|---|---|
| BRIN index on `timestamp` (append-only tables) | tiny index, fast range scans on T0/T1 | Supabase Postgres |
| B-tree `(ticker, timestamp DESC)` | point lookups + series reads | all tier tables |
| Partial indexes `WHERE ticker = ANY(top200)` | smaller, faster for live set | T1 |
| `pg_stat_statements` | find real slow queries | built-in |
| Supabase Advisors (index/RLS/perf) | free audit before we guess | `supabase` MCP `get_advisors` |
| Limit realtime publication to live tables | less replication overhead | Supabase config |
| Transaction pooling (Supavisor) | connection limits never bite | Supabase |
| Upsert storm dead-tuple monitoring | bloat before it hurts (`n_dead_tup`) | `pg_stat_user_tables` |
| Column order: wide/variable last | cheaper row reads | schema design |

## DuckDB supercharge (cold tier)

| Technique | Effect |
|---|---|
| `httpfs` extension | query Parquet directly from R2/B2 — no download step |
| Hive partitioning `ticker=X/date=Y/` | partition pruning per query |
| **Sort Parquet by (ticker, timestamp)** | zonemap pruning = skip irrelevant row groups (10–100× on selective queries) |
| zstd compression (default level) | ~4× smaller than gzip, faster reads |
| Column projections only, never `SELECT *` | columnar engine loves narrow reads |
| `PRAGMA threads / memory_limit` | bounded runs on shared machines |
| Repeated backtests | persistent `.duckdb` file w/ materialized views |
| `ANALYZE` after bulk loads | better plans |

## Supabase supercharge (hot tier)

- Rollups scheduled via `pg_cron` OR backend timers — pick one scheduler, never
  both (double-rollup corruption risk).
- Cache at the edge first (HTTP `Cache-Control` on API aggregate endpoints) —
  no Redis until measured need (ch.09).
- Keep hot set small = the supercharge: T0 24–48h + T1 30d + T2 rollups. A
  5–10 GB database is always snappy.
- VACUUM health via advisors; upsert-heavy writers need autovacuum tuning.

## Backend hardening (before first endpoint)

- Fail-fast config validation at startup (pydantic-settings), 3.10-compatible
- Global error handler; errors never leak internals (ch.12)
- Structured logging (`structlog`) + Prometheus `/metrics` (ch.15)
- Graceful shutdown: finish batch on SIGTERM (ch.16)
- OpenAPI-first: `api_spec.yaml` generated from code (ch.25)
- Deep health = data freshness, not process liveness (ch.12)
- Dependency pinning + lockfile; minimal set

## Frontend hardening

- Vite + React SPA (lean; no SSR needed behind auth) — ADR 0003
- TanStack Query: cache + stale-while-revalidate + background refetch
- TradingView **lightweight-charts** (Apache-2.0) for time series; custom SVG
  for GEX profile / heat grid; TanStack Table + virtualization for MEATSEEKER
- Zod validation shared with OpenAPI-generated types
- MSW (Mock Service Worker) = the ADR 0002 mock mode
- Storybook for widget review; Playwright for E2E smoke

## Security hardening (ch.17 + 04)

- Everything in `docs/security.md` checklist, plus:
- CSP + strict CORS; rate limiting at edge; CSRF strategy chosen with auth mode
- **gitleaks** pre-commit + CI (the `.env` incident class: never again)
- **Semgrep** CI rules; **Trivy** container scan; Dependabot/Renovate updates
- Non-root containers; read-only FS where possible
- Supabase grants deny-by-default verified in CI (query `has_table_privilege`
  as a test — a regression is a build failure)

## Monitoring (all OSS, runs on VPS)

| Need | Tool |
|---|---|
| uptime + freshness alerts | Uptime Kuma |
| error tracking | GlitchTip (SOS Sentry-compatible) |
| logs/metrics | journald + Prometheus + Grafana (optional at first) |

## Explicit non-tools (rejected for v1)

- Kafka/message broker (roadmap had a KAFKA-ADOPTION plan — not needed with
  one writer + scheduled jobs; revisit only on multi-writer fan-in)
- dbt/airflow for rollups — jobs are simple SQL; heavyweight DAG tools add ops
- Redis — cache at edge + small hot set first
- Kubernetes — systemd + docker on one VPS
