-- 0003_pgmq_backfill_queue.sql — pgmq lazy-backfill queue regression (card E2.2).
--
-- Deny-default law for the queue (0004 pattern): nothing for PUBLIC or the
-- Supabase platform roles, ingest may only enqueue, jobs owns consume/ack/
-- dead-letter. The queue is transport only — no scheduler objects exist
-- (single-scheduler law, master-architecture §4).
--
-- Runs as superuser via scripts/db_tests.py (TAP output).

BEGIN;
SELECT plan(13);

-- 1-3. Queue exists: extension + both queue tables (live + dead-letter).
SELECT has_extension('pgmq', 'pgmq extension installed');
SELECT has_table('pgmq', 'q_backfill', 'live queue table exists');
SELECT has_table('pgmq', 'a_backfill', 'dead-letter archive table exists');

-- 4. Deny-default: no queue-table privileges for PUBLIC or Supabase platform
--    roles (the SignalForge anon-SELECT lesson, queue-shaped).
SELECT is_empty($$
    SELECT tp.grantee, tp.table_name, tp.privilege_type
    FROM information_schema.table_privileges tp
    WHERE tp.table_schema = 'pgmq'
      AND tp.table_name IN ('q_backfill', 'a_backfill')
      AND tp.grantee IN ('PUBLIC', 'anon', 'authenticated', 'service_role', 'pgbouncer')
$$, 'deny-default: no queue privileges for PUBLIC/platform roles');

-- 5-7. Ingest enqueues only.
SELECT ok(has_table_privilege('gammasummit_ingest', 'pgmq.q_backfill', 'INSERT'),
    'ingest can enqueue backfill requests');
SELECT ok(NOT has_table_privilege('gammasummit_ingest', 'pgmq.q_backfill', 'DELETE'),
    'ingest cannot consume/delete queue messages');
SELECT ok(NOT has_table_privilege('gammasummit_ingest', 'pgmq.a_backfill', 'SELECT'),
    'ingest cannot read the dead-letter archive');

-- 8-11. Jobs consume + ack + enqueue the live queue.
SELECT ok(has_table_privilege('gammasummit_jobs', 'pgmq.q_backfill', 'SELECT'),
    'jobs can read queue messages');
SELECT ok(has_table_privilege('gammasummit_jobs', 'pgmq.q_backfill', 'UPDATE'),
    'jobs can set visibility timeouts');
SELECT ok(has_table_privilege('gammasummit_jobs', 'pgmq.q_backfill', 'DELETE'),
    'jobs can ack (delete) finished messages');
SELECT ok(has_table_privilege('gammasummit_jobs', 'pgmq.q_backfill', 'INSERT'),
    'jobs can enqueue follow-up gap fills');

-- 12-13. Jobs own the dead-letter archive.
SELECT ok(has_table_privilege('gammasummit_jobs', 'pgmq.a_backfill', 'SELECT'),
    'jobs can inspect dead-lettered messages');
SELECT ok(has_table_privilege('gammasummit_jobs', 'pgmq.a_backfill', 'INSERT'),
    'jobs can dead-letter exhausted messages');

SELECT * FROM finish();
ROLLBACK;
