-- 0004_single_scheduler.sql — ONE-scheduler law regression (card E2.3, ADR 0007).
--
-- Hard rule (docs/build/README.md): pg_cron XOR backend timers — NEVER both.
-- GammaSummit runs backend timers (backend/jobs/scheduler.py is the only
-- scheduler); pg_cron must therefore NEVER be installed in this database, and
-- the tier jobs keep their owner-locked delete path (0004 grants: jobs role
-- holds no DELETE — manifest-verified retention deletes run as the table owner
-- via the single scheduler).
--
-- Runs as superuser via scripts/db_tests.py (TAP output).

BEGIN;
SELECT plan(4);

-- 1. pg_cron is NOT installed. A second scheduler may never appear — if this
--    fails, someone installed pg_cron and the single-scheduler law is broken.
SELECT ok(
    NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'),
    'single-scheduler law: pg_cron NOT installed (backend timers only)'
);

-- 2. No cron schema at all (not even an unconfigured pg_cron).
SELECT ok(
    NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'cron'),
    'single-scheduler law: no cron schema'
);

-- 3. Tier deletes stay owner-only: gammasummit_jobs holds NO DELETE on any
--    T0/T1/T2 table (manifest-verified retention runs as the table owner).
SELECT is_empty($$
    SELECT table_name, privilege_type
    FROM information_schema.table_privileges
    WHERE grantee = 'gammasummit_jobs'
      AND privilege_type = 'DELETE'
      AND table_name IN (
        'gamma_snapshot', 'spot_tick', 'flow_print', 'darkpool_print',
        'gamma_bucket_5m', 'expiry_rollup_hourly', 'strike_eod',
        'king_node_history'
      )
$$, 'jobs role holds no DELETE on tier tables (owner-only retention)');

-- 4. The scheduler's audit ledger is writable by the jobs role (every
--    scheduled run lands in audit_log, docs/ops/operations.md).
SELECT ok(
    has_table_privilege('gammasummit_jobs', 'audit_log', 'INSERT')
    AND has_table_privilege('gammasummit_jobs', 'audit_log', 'SELECT'),
    'jobs role can write the scheduler audit ledger'
);

SELECT * FROM finish();
ROLLBACK;
