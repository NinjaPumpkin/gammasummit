-- 0005_pgmq_backfill_queue.sql — pgmq lazy-backfill queue (card E2.2).
--
-- master-architecture.md §4: `lazy_backfill` (on-demand via pgmq) fills T0
-- gaps for the long tail (docs/ops/data-tiering.md "lazy backfill", API
-- trigger in §6 `/jobs/backfill`). The queue is TRANSPORT ONLY — no timers are
-- created here (single-scheduler law: the P2 tiering scheduler stays pg_cron
-- XOR backend timers, never both, and is the only scheduler in the system;
-- queue consumption is worker-driven polling in backend/jobs/backfill.py).
--
-- Message contract (backend/jobs/backfill.py is the only producer/consumer):
--   {"ticker": "SPY", "dataset": "gamma_chain|spot|flow|dark_pool",
--    "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD",
--    "reason": "...", "requested_by": "...", "queued_at": "<ISO ts>"}
-- Exhausted / poisoned messages dead-letter into pgmq.a_backfill.
--
-- pgmq 1.5.1 (ships in the pinned test image public.ecr.aws/supabase/
-- postgres:17.6.1.063 and on managed Supabase): trusted extension
-- (superuser = false), non-relocatable schema `pgmq`; queue tables
-- pgmq.q_backfill / pgmq.a_backfill keyed by msg_id (identity).

CREATE EXTENSION IF NOT EXISTS pgmq;

-- pgmq.create() is not idempotent — guard on the queue's table existing.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'pgmq' AND table_name = 'q_backfill'
    ) THEN
        PERFORM pgmq.create('backfill');
    END IF;
END
$$;

-- Deny-default (0004 law, least privilege). pgmq's functions are SECURITY
-- INVOKER, so these table grants ARE the access boundary. Roles come from
-- 0003: gammasummit_ingest enqueues (fleet gap detection), gammasummit_jobs
-- consumes/acks/dead-letters (backfill worker). RLS is intentionally NOT
-- enabled on extension-owned queue tables (they live outside the exposed
-- `public` schema; 0004's advisor gate covers exposed tables only).
GRANT USAGE ON SCHEMA pgmq TO gammasummit_ingest, gammasummit_jobs;
GRANT INSERT ON pgmq.q_backfill TO gammasummit_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA pgmq TO gammasummit_ingest, gammasummit_jobs;
GRANT SELECT, INSERT, UPDATE, DELETE ON pgmq.q_backfill TO gammasummit_jobs;
GRANT SELECT, INSERT ON pgmq.a_backfill TO gammasummit_jobs;
