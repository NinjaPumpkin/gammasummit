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

### DuckDB extensions — verdicts (audited vs awesome-duckdb list, 2026-09-30)

**Adopt (core, install in `db/queries/duckdb_setup.sql`):**

| Extension | Job in our stack |
|---|---|
| `parquet` | T3 cold tier read/write — baseline |
| `httpfs` + `aws` | Parquet directly from R2/B2 + credential handling |
| `postgres` | **federation**: join hot Supabase T0/T1 with cold Parquet in ONE query — backtests without export steps; also old-vs-new reconciliation during cutover |
| `sqlite` | read SignalForge legacy `signalforge.db` / `gamma_copilot.db` directly during migration + cold archiving |
| `json` | UW raw API response archives (semi-structured) |
| `arrow` | zero-copy handoff to Python (pandas/polars) in backtests |

**Adopt (community, `INSTALL … FROM community`):**

| Extension | Job |
|---|---|
| `cache_httpfs` | read-cache layer over R2/B2 → less egress + faster repeated backtest scans |
| `cache_prewarm` | preload blocks before scheduled research runs |
| `query_condition_cache` | speed up repeated-query backtest workloads |

**Evaluate later (real value, not v1):**

| Extension | Why wait |
|---|---|
| `ducklake` | lakehouse format w/ ACID + snapshots — could replace hand-rolled export manifests one day; needs a catalog DB; revisit when cold tier > 1 TB |
| `scrooge` | finance-specific aggregations — check maturity before depending on it |
| `stats_duck` | descriptive stats + `VISUALIZE`→Vega-Lite for research reports |
| `httpserver` | DuckDB-over-HTTP — tempting for on-demand research, but = second query surface; violates single-API security model unless strictly internal |

**Rejected:** `vss` (vector search = Open Brain's problem, not market data),
`spatial`/`h3`/`fts`/`elasticsearch`/`prql`/`gpudb` (no current workload; GPU one
is unproven community code).

**Ecosystem picks:** DuckDB GitHub Action (CI analytics tests, free),
[execution plan visualizer](https://db.cs.uni-tuebingen.de/explain/) (debug slow
backtests), book *Local-First Analytics* (partitioning/perf reference).
**Adopt as internal tool: [duck-ui](https://github.com/caioricciuti/duck-ui)**
(MIT) — browser DuckDB workbench: SQL editor, notebooks, charts, all client-side
DuckDB-WASM, zero backend. Use for T3 Parquet research/ad-hoc review without
building a research UI. Security fit: runs in-tab, never becomes a query
surface on our servers. Caveat: WASM memory ceiling (~2–4 GB) — heavy backtests
stay on native DuckDB; day-level Parquet slices fine. Also living proof the
DuckDB-WASM pattern works.
Worth reading: DuckDB-WASM + R2 "query big data for almost free" pattern —
browser-side on-demand history queries with zero backend compute = interesting
experiment for long-tail on-demand tier (market data is shareable; use signed
URLs). Marked experimental, not architecture.

## Supabase supercharge (hot tier)

- Rollups scheduled via `pg_cron` OR backend timers — pick one scheduler, never
  both (double-rollup corruption risk).
- Cache at the edge first (HTTP `Cache-Control` on API aggregate endpoints) —
  no Redis until measured need (ch.09).
- Keep hot set small = the supercharge: T0 24–48h + T1 30d + T2 rollups. A
  5–10 GB database is always snappy.
- VACUUM health via advisors; upsert-heavy writers need autovacuum tuning.

### Postgres extensions — verdicts (catalog verified live on Supabase 2026-09-30)

Available in the hosted catalog (`list_extensions`), picked for our workload:

| Extension | Version | Job in our stack |
|---|---|---|
| `pg_partman` | 5.3.1 | **automates partition management** (time + ID) — our single-table partitioning rule runs itself |
| `pg_cron` | 1.6.4 | schedules rollups in-DB — OR use backend timers, never both |
| `pgmq` | 1.5.1 | lightweight SQS-like queue in Postgres — lazy-backfill job queue option (ch.10) |
| `pg_stat_monitor` | 2.1 | query stats WITH plans + histograms — beats bare `pg_stat_statements` (installed) |
| `index_advisor` | 0.2.0 | query index advisor — suggests before we create |
| `hypopg` | 1.4.1 | **hypothetical indexes** — test index value WITHOUT creating it |
| `pgaudit` | 17.1 | audit logging — feeds the audit-log requirement (`security-future.md`) |
| `pgtap` | 1.2.0 | SQL unit tests in CI — schema invariants as tests |
| `plpgsql_check` | 2.7 | lints plpgsql (RPC functions) |
| `pg_repack` | 1.5.2 | bloat cleanup with minimal locks — upsert storms create dead tuples |
| `pg_prewarm` | 1.2 | prewarm hot tables after restart |
| `moddatetime`/`insert_username` | — | updated_at / updated_by triggers, free |

Not present: **TimescaleDB** — confirms our design choice (native partitioning
+ rollups, no hypertable dependency). `wrappers`/`postgres_fdw` = federation
escape hatch if we ever need cross-DB joins from SQL.

### Live advisor scorecard (knszzlbwlnjjbnrlotib, 2026-09-30) — the cost smoking gun

| Lint | Level | Count | Action |
|---|---|---|---|
| `rls_disabled_in_public` | ERROR | **1,255** | fixed by new-project deny-default (never carried over) |
| `unused_index` | INFO | **2,207** | **write amplification on every upsert** — dropping them = faster writes + less storage + cheaper bill |
| `rls_enabled_no_policy` | INFO | 52 | tidy at migration |
| `multiple_permissive_policies` | WARN | 50 | consolidate in new schema |
| `function_search_path_mutable` | WARN | 20 | pin `search_path` on functions (ch.17) |
| `anon_security_definer_function_executable` | WARN | 2 | **revoke anon EXECUTE now** — live exposure |
| `auth_leaked_password_protection` | WARN | 1 | enable in auth settings |
| `unindexed_foreign_keys` / `no_primary_key` / `duplicate_index` | INFO/WARN | 8/4/3 | schema hygiene |

Run `get_advisors` after every DDL batch (MCP tool) — gate = zero ERROR lints.

### awesome-supabase list — tool verdicts (audited 2026-09-30)

**Adopt:**
- **`supabase-security` linter** (MIT, CLI + GitHub Action) — lints
  `supabase/migrations` for grant/RLS mistakes AND flags the **Oct 30, 2026
  Supabase Data API grants change** — tables without explicit GRANTs change
  exposure behavior. Add to CI for gammasummit AND check SignalForge impact.
- **`backupdrill`** (MIT) — backups to own bucket + **scheduled restore-
  verification drills** → implements the "untested backup is not a backup" rule.
- Crib audit SQL from `supabase-rls-leak-demo` (RLS-disabled + `USING(true)`
  probes) into our CI `has_table_privilege` regression test.

**Evaluate later:** RowShield (outside-in anonymous probe of deployed app —
complement to CI checks), `supabase-plus` (CLI extras), pgflow/Supabase Queues
(= managed alternative to pgmq).

**Rejected:** GuardLayer (Next.js-only, we're Vite), 1bench (paid, MCP+psql
cover it), Nemesis Shield (no Edge Functions in v1), starter kits (we build
our own).

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

- Everything in `docs/ops/security.md` checklist, plus:
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
