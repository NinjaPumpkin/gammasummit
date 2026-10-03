# Changelog

All notable changes to this project are documented in this file (Keep a
Changelog). Versioning scheme: `docs/build/code-structure-and-release.md` §4 —
SemVer app tags `v0.x` pre-cutover, `v1.0.0` at cutover.

## [Unreleased]

### Added

- E2.4 freshness metric + Uptime Kuma alarms + shadow validation harness
  (ultraplan P2 close-out): `backend/jobs/freshness.py` (per-table/tier
  freshness from payload timestamps + the three operations.md checks —
  `t0_freshness` 15-min market-hours-gated, `downsampler_lag` 30-min,
  `retention_jobs` daily-window via THE audit ledger — plus `--push` beacon to
  Uptime Kuma push monitors and an `--as-of` verification clock), Uptime Kuma
  wiring (`scripts/e24_kuma_admin.py`: 4 push monitors + webhook channel,
  secrets to `.env` only) and `scripts/e24_shadow_validate.py` (the daily
  shadow-validation harness: per-trading-day tier placement + hot-set budget +
  freshness, accumulating E0.2-refit-style). Verified on real UW rows: 5
  trading days (2026-09-25 → 2026-10-01; ~1.55M gamma rows + 64k
  contract_daily rows) through the real pipeline (T1 1,544,780 buckets, T2
  63,652 rows, retention export-first drop of 137 verified Parquet segments /
  1.56M rows to X10) — 5/5 days ✓ at target tiers, hot set 379 MB ≤ 10 GB,
  measurement table in `docs/data/e24-shadow-validation.md`. Deliberate
  staleness drill fired the alarms (3× `[🔴 Down]` webhooks) and cleared them
  (3× `[✅ Up]`) with sink-log evidence. Ops runbook: `docs/ops/operations.md`;
  evidence: `docs/build/e2.4-freshness-shadow.md`.

- E2.3 P2 tier jobs + THE single scheduler (ADR 0007: backend timers, pg_cron
  never installed): `backend/jobs/rollups.py` (downsampler T0→T1 5-min buckets
  with cumulative-counter volume deltas + dedupe; rollups T1→T2 hourly expiry
  GEX + per-strike EOD chains, `net_gex = call − put`, `schema_version=1`),
  `backend/jobs/export_cold.py` (T1/T2→T3 Parquet cold on X10 + rclone B2/R2
  copy, export-first plan → manifest → verify → copy → verified-only drop,
  `--as-of` verification clock, T2 window owner-locked 90–365d), `backend/jobs/
  scheduler.py` (advisory-locked cadence: 5-min/1h/daily + pg_partman
  `run_maintenance()` as owner, audit-logged, `--dry-run` default), pgtap
  single-scheduler guard (`db/tests/0004_*.sql`). Verified end-to-end on real
  UW PHX shadow rows: 9,098 rows reloaded from T3 → 6,940 T1 buckets (volume
  telescoping 0 mismatches) → 4,887 EOD + 40 hourly T2 rows (net law 0
  mismatches) → scheduler export-first drop of T0 (119 verified exports,
  833 KB to X10) → T1/T2 cold export (15 verified exports + 15 rclone
  size-verified copies) → verified-only delete. Hot set measured 11.1 MiB ≤
  10 GB budget. Evidence: `docs/build/e2.3-tier-jobs.md`.

- E2.2 P2 ingest daemon (UW PHX fetchers + T0 writer + pgmq backfill queue):
  `backend/ingest/` (`uw_client.py` rate-law client — ≤50%-of-limit pacing,
  daily cap, cooldown + exponential backoff on any rate signal; `chain_writer/
  spot_writer/flow_writer` PHX→T0 mappers; `fleet.py` daemon + lazy-backfill
  handler), `backend/jobs/backfill.py` (pgmq `backfill` queue worker: ack /
  requeue-with-backoff / dead-letter, poison isolation), `backend/jobs/
  retention.py` (T0 24–48h retention, export-first: plan → Parquet → manifest →
  verify → delete, `--dry-run` default), `db/migrations/
  0005_pgmq_backfill_queue.sql` + pgtap queue regression
  (`db/tests/0003_*.sql`), batch-upsert in `backend/core/db.py`. Verified on
  real UW PHX shadow sessions (rows land in T0; upstream killed mid-run →
  bounded retries → full recovery; queue drained with dead-letters; retention
  deleted 9,098 rows only after 119 verified exports) — evidence in
  `docs/build/e2.2-ingest-shadow.md`.

- E2.1 P1 foundations (ADR 0006): `backend/core` spine (config/errors/
  logging/db — structured JSON logs with secret scrubbing, asyncpg pool with
  bounded retry + jitter), partitioned T0/T1/T2 schema of
  `master-architecture.md` §5 (`db/migrations/0003_partitioned_schema.sql`:
  pg_partman time-RANGE partitions, BRIN + `(ticker, ts DESC)` index law),
  deny-default grants + RLS (`0004_deny_default_grants.sql`: Supabase
  anon-trap default-ACL revokes, three least-privilege app roles), pgtap
  schema invariants + grants regression (`db/tests/`), migration+pgtap runner
  (`scripts/db_tests.py`), Supabase get_advisors gate
  (`scripts/security_advisors_check.py`), CI jobs `db-tests` +
  `supabase-security`.

### Fixed

- `0002_contract_daily_stats.sql`: quoted the reserved word `right` (the file
  was a parse error on every Postgres and had never applied anywhere — probed
  UW PHX read-only 2026-10-02: tables absent).

### Added (E1.x history)

- E1.1 scaffold: code tree (`backend/`, `db/`, `frontend/`, `deploy/`), manifests
  (`pyproject.toml`, root `package.json` workspace, `.env.example` with
  `GAMMASUMMIT_*` placeholders only, `AGENTS.md`), FastAPI app skeleton
  (`/healthz`, `/readyz`), migration lint harness (`scripts/migration_lint.py`),
  Zod<->pydantic single-contract skeleton (`scripts/contract_sync.py`, ADR 0003),
  Vite+React frontend placeholder wired to `frontend/mockups/`, deploy
  placeholders (systemd units, docker compose, VPS release scripts), scaffold
  smoke tests.
