-- 0002_grants_regression.sql — deny-default grants regression (card E2.1).
--
-- The SignalForge lesson (2026-09-30: anon SELECT on gamma tables) becomes a
-- hard CI gate: nothing may be readable by PUBLIC/anon/authenticated/
-- service_role/pgbouncer, every app role holds EXACTLY its allowlisted
-- privileges (docs/ops/security.md deny-by-default), and every granted pair is
-- mirrored by an RLS policy (master-architecture §7 double-check).
--
-- Runs as superuser via scripts/db_tests.py (TAP output).

BEGIN;
SELECT plan(11);

-- 1. No table-level privileges for PUBLIC or Supabase platform roles on any
--    migration-created object (pgtap fixture objects are test-harness noise).
SELECT is_empty($$
    SELECT tp.grantee, tp.table_name, tp.privilege_type
    FROM information_schema.table_privileges tp
    WHERE tp.table_schema = 'public'
      AND tp.grantee IN ('PUBLIC', 'anon', 'authenticated', 'service_role', 'pgbouncer')
      AND tp.table_name IN (
        'app_meta', 'contract_daily_stats', 'underlying_daily_stats',
        'ticker_universe', 'top200_membership', 'export_manifest',
        'alert_rule', 'alert_event',
        'gamma_snapshot', 'spot_tick', 'flow_print', 'darkpool_print',
        'gamma_bucket_5m', 'expiry_rollup_hourly', 'strike_eod',
        'king_node_history', 'audit_log'
      )
$$, 'deny-default: no table privileges for PUBLIC/platform roles');

-- 2. No schema USAGE for PUBLIC or Supabase platform roles.
SELECT is_empty($$
    SELECT role_name
    FROM (VALUES ('anon'), ('authenticated'), ('service_role'), ('pgbouncer'))
        AS expected(role_name)
    WHERE has_schema_privilege(role_name, 'public', 'USAGE')
    UNION ALL
    SELECT 'PUBLIC'
    FROM pg_namespace n
    CROSS JOIN LATERAL aclexplode(n.nspacl) acl
    WHERE n.nspname = 'public' AND acl.grantee = 0
$$, 'deny-default: no schema USAGE for PUBLIC/platform roles');

-- 3. No sequence privileges for PUBLIC or Supabase platform roles (identity
--    sequences of alert_rule / audit_log).
SELECT is_empty($$
    SELECT r.rolname, c.relname
    FROM pg_roles r
    JOIN pg_class c ON c.relkind = 'S'
    JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    WHERE r.rolname IN ('anon', 'authenticated', 'service_role', 'pgbouncer')
      AND (c.relname LIKE 'alert_rule_%' OR c.relname LIKE 'audit_log_%')
      AND (
          has_sequence_privilege(r.rolname, c.oid, 'USAGE')
          OR has_sequence_privilege(r.rolname, c.oid, 'SELECT')
          OR has_sequence_privilege(r.rolname, c.oid, 'UPDATE')
      )
$$, 'deny-default: no sequence privileges for platform roles');

-- 4. gammasummit_api exact matrix (read surface + alert CRUD).
SELECT is_empty($$
    WITH expected(table_name, privilege_type) AS (VALUES
        ('ticker_universe', 'SELECT'),
        ('top200_membership', 'SELECT'),
        ('export_manifest', 'SELECT'),
        ('gamma_snapshot', 'SELECT'),
        ('spot_tick', 'SELECT'),
        ('flow_print', 'SELECT'),
        ('darkpool_print', 'SELECT'),
        ('gamma_bucket_5m', 'SELECT'),
        ('expiry_rollup_hourly', 'SELECT'),
        ('strike_eod', 'SELECT'),
        ('king_node_history', 'SELECT'),
        ('audit_log', 'SELECT'),
        ('alert_rule', 'SELECT'),
        ('alert_rule', 'INSERT'),
        ('alert_rule', 'UPDATE'),
        ('alert_rule', 'DELETE'),
        ('alert_event', 'SELECT'),
        ('alert_event', 'INSERT'),
        ('alert_event', 'UPDATE'),
        ('alert_event', 'DELETE')
    )
    SELECT expected.table_name, expected.privilege_type
    FROM expected
    FULL JOIN (
        SELECT tp.table_name, tp.privilege_type
        FROM information_schema.table_privileges tp
        WHERE tp.table_schema = 'public' AND tp.grantee = 'gammasummit_api'
    ) actual USING (table_name, privilege_type)
    WHERE expected.table_name IS NULL OR actual.table_name IS NULL
$$, 'gammasummit_api holds exactly its allowlisted privileges');

-- 5. gammasummit_ingest exact matrix (UW T0 writes + catalog reads).
SELECT is_empty($$
    WITH expected(table_name, privilege_type) AS (VALUES
        ('ticker_universe', 'SELECT'),
        ('top200_membership', 'SELECT'),
        ('gamma_snapshot', 'SELECT'),
        ('gamma_snapshot', 'INSERT'),
        ('gamma_snapshot', 'UPDATE'),
        ('spot_tick', 'SELECT'),
        ('spot_tick', 'INSERT'),
        ('spot_tick', 'UPDATE'),
        ('flow_print', 'SELECT'),
        ('flow_print', 'INSERT'),
        ('flow_print', 'UPDATE'),
        ('darkpool_print', 'SELECT'),
        ('darkpool_print', 'INSERT'),
        ('darkpool_print', 'UPDATE')
    )
    SELECT expected.table_name, expected.privilege_type
    FROM expected
    FULL JOIN (
        SELECT tp.table_name, tp.privilege_type
        FROM information_schema.table_privileges tp
        WHERE tp.table_schema = 'public' AND tp.grantee = 'gammasummit_ingest'
    ) actual USING (table_name, privilege_type)
    WHERE expected.table_name IS NULL OR actual.table_name IS NULL
$$, 'gammasummit_ingest holds exactly its allowlisted privileges');

-- 6. gammasummit_jobs exact matrix (T1/T2 writers + ops manifests + audit).
SELECT is_empty($$
    WITH expected(table_name, privilege_type) AS (VALUES
        ('ticker_universe', 'SELECT'),
        ('top200_membership', 'SELECT'),
        ('alert_rule', 'SELECT'),
        ('alert_event', 'SELECT'),
        ('gamma_snapshot', 'SELECT'),
        ('spot_tick', 'SELECT'),
        ('flow_print', 'SELECT'),
        ('darkpool_print', 'SELECT'),
        ('gamma_bucket_5m', 'SELECT'),
        ('gamma_bucket_5m', 'INSERT'),
        ('gamma_bucket_5m', 'UPDATE'),
        ('expiry_rollup_hourly', 'SELECT'),
        ('expiry_rollup_hourly', 'INSERT'),
        ('expiry_rollup_hourly', 'UPDATE'),
        ('strike_eod', 'SELECT'),
        ('strike_eod', 'INSERT'),
        ('strike_eod', 'UPDATE'),
        ('king_node_history', 'SELECT'),
        ('king_node_history', 'INSERT'),
        ('king_node_history', 'UPDATE'),
        ('export_manifest', 'SELECT'),
        ('export_manifest', 'INSERT'),
        ('export_manifest', 'UPDATE'),
        ('audit_log', 'SELECT'),
        ('audit_log', 'INSERT')
    )
    SELECT expected.table_name, expected.privilege_type
    FROM expected
    FULL JOIN (
        SELECT tp.table_name, tp.privilege_type
        FROM information_schema.table_privileges tp
        WHERE tp.table_schema = 'public' AND tp.grantee = 'gammasummit_jobs'
    ) actual USING (table_name, privilege_type)
    WHERE expected.table_name IS NULL OR actual.table_name IS NULL
$$, 'gammasummit_jobs holds exactly its allowlisted privileges');

-- 7. RLS double-check: every granted (role, table) pair has a policy that
--    names the role (grants alone are not the only layer).
SELECT is_empty($$
    SELECT tp.grantee, tp.table_name
    FROM information_schema.table_privileges tp
    WHERE tp.table_schema = 'public'
      AND tp.grantee IN ('gammasummit_api', 'gammasummit_ingest', 'gammasummit_jobs')
      AND NOT EXISTS (
        SELECT 1 FROM pg_policies pol
        WHERE pol.schemaname = 'public'
          AND pol.tablename = tp.table_name
          AND (
              tp.grantee::name = ANY (pol.roles)
              OR 'public'::name = ANY (pol.roles)
          )
      )
    GROUP BY tp.grantee, tp.table_name
$$, 'every granted (role, table) pair is mirrored by an RLS policy');

-- 8-10. Functional probes (privilege checks, no data needed).
SELECT ok(
    has_table_privilege('gammasummit_api', 'public.gamma_snapshot', 'SELECT')
    AND NOT has_table_privilege('gammasummit_api', 'public.gamma_snapshot', 'INSERT'),
    'api reads T0 but cannot write it'
);
SELECT ok(
    has_table_privilege('gammasummit_ingest', 'public.gamma_snapshot', 'INSERT')
    AND NOT has_table_privilege('gammasummit_ingest', 'public.gamma_snapshot', 'DELETE'),
    'ingest batch-upserts T0 but cannot delete it'
);
SELECT ok(
    has_table_privilege('gammasummit_jobs', 'public.strike_eod', 'INSERT')
    AND NOT has_table_privilege('gammasummit_jobs', 'public.strike_eod', 'DELETE')
    AND NOT has_table_privilege('gammasummit_jobs', 'public.gamma_snapshot', 'INSERT'),
    'jobs writes T2, cannot delete, and never writes raw T0'
);

-- 11. No DDL for app roles (schema CREATE revoked — deny-default schema law).
SELECT is_empty($$
    SELECT role_name
    FROM (VALUES ('gammasummit_api'), ('gammasummit_ingest'), ('gammasummit_jobs'))
        AS expected(role_name)
    WHERE has_schema_privilege(role_name, 'public', 'CREATE')
$$, 'app roles cannot create objects in public');

SELECT * FROM finish();
ROLLBACK;
