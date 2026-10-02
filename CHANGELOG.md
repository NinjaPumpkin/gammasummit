# Changelog

All notable changes to this project are documented in this file (Keep a
Changelog). Versioning scheme: `docs/build/code-structure-and-release.md` §4 —
SemVer app tags `v0.x` pre-cutover, `v1.0.0` at cutover.

## [Unreleased]

### Added

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
