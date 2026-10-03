# ADR 0007 — THE single scheduler: backend timers (pg_cron never installed)

Date: 2026-10-02 · Status: accepted · Card: E2.3 (ultraplan P2, WS B)

> Numbering note: card E2.3 asked for "ADR 0005", but 0005 (ops-brain interop)
> and 0006 (partitioned schema) were already accepted — this decision takes
> the next free number, 0007. Nothing was renumbered (ADRs are immutable).

Context: the single-scheduler law (hard rule, docs/build/README.md; repeated
on every card) allows **pg_cron XOR backend timers — NEVER both**. Double
scheduling is a corruption risk (double rollups, racing retention). The choice
was reserved for P2 (E2.2 deliberately shipped pgmq with no timers) and must
now be made and recorded.

## Decision

**Backend timers. `backend/jobs/scheduler.py` is the ONLY scheduler in the
system. pg_cron is never installed** — asserted in CI by
`db/tests/0004_single_scheduler.sql` (pgTAP: `pg_extension` has no `pg_cron`,
no `cron` schema exists).

The scheduler owns the complete tier cadence and nothing else schedules work:

| Cadence | Job | Module |
|---|---|---|
| every 5 min | downsampler T0→T1 (5-min buckets) | `jobs/rollups.py` |
| hourly | rollups T1→T2 (hourly expiry GEX) | `jobs/rollups.py` |
| daily 22:30Z | rollups T1→T2 (per-strike EOD chains) | `jobs/rollups.py` |
| daily 22:45Z | T0 24–48h retention (export-first drop) | `jobs/retention.py` |
| daily 23:00Z | T1/T2 → T3 cold export + manifest-verified drop | `jobs/export_cold.py` |
| hourly | pg_partman `run_maintenance()` (partition DDL) | scheduler |

## Consequences

1. **Why not pg_cron:** every P2 job is Python (Parquet write, sha256
   manifest verify, rclone copy, delete gating). pg_cron schedules SQL only,
   so a pg_cron path would need shell/`pg_net` bridges — i.e. a second
   execution path = the second scheduler the law forbids. One Python daemon
   with in-process timers keeps one code path, one lock, one audit trail.
2. **One instance:** a Postgres advisory lock (`pg_try_advisory_lock`, session
   scoped on a dedicated connection — `core/db.py Database.session()`) makes a
   second scheduler exit without running anything.
3. **Partition DDL is owner-only** (0004): `run_maintenance()` runs over a
   separate owner DSN (`GAMMASUMMIT_DB_OWNER_URL`). App roles never create or
   drop partitions. Retention deletes run over the same owner DSN (the jobs
   role holds no DELETE on tier tables).
4. **Audit:** every applied run lands in `audit_log` (actor
   `jobs:scheduler`); dry-run performs ZERO writes, including audit rows.
5. **Dry-run is the default** everywhere (`--execute` to apply) — the hard
   rule survives into production: the systemd unit runs
   `python -m backend.jobs.scheduler --execute --loop` explicitly.
6. **Revisit triggers:** job volume outgrows one process (shard by job, keep
   one lock domain), or Supabase mandates in-DB scheduling (then flip to
   pg_cron wholesale and DELETE this daemon — never run both).
