-- 0001_schema_invariants.sql — pgtap invariants for the P1 schema (card E2.1).
--
-- Asserts the schema law:
--   - every entity of master-architecture.md §5 exists
--   - types locked: timestamptz / date / bigint / double precision (+text/bool)
--   - append tables are RANGE-partitioned and registered with pg_partman
--     (premake children created, retention NULL = partman never drops)
--   - index law: (ticker, ts DESC)-style B-tree + BRIN on the time column
--   - unique indexes include the partition-control column
--   - app_meta.schema_version bumped
--   - RLS enabled on every app table (security.md / master-architecture §7)
--
-- Runs as superuser via scripts/db_tests.py (TAP output).

BEGIN;
-- partman may install into `extensions` (Supabase) or its creation schema
-- (bare installs) — put its schema on the search_path for `part_config` below.
DO $$
BEGIN
    PERFORM set_config(
        'search_path',
        'public,' || (
            SELECT n.nspname
            FROM pg_extension e
            JOIN pg_namespace n ON n.oid = e.extnamespace
            WHERE e.extname = 'pg_partman'
        ),
        true
    );
END
$$;
SELECT plan(9);

-- 1. All migration-created tables exist (0001 + 0002 + 0003).
SELECT is_empty($$
    SELECT expected_name
    FROM (VALUES
        ('app_meta'), ('contract_daily_stats'), ('underlying_daily_stats'),
        ('ticker_universe'), ('top200_membership'), ('export_manifest'),
        ('alert_rule'), ('alert_event'),
        ('gamma_snapshot'), ('spot_tick'), ('flow_print'), ('darkpool_print'),
        ('gamma_bucket_5m'), ('expiry_rollup_hourly'), ('strike_eod'),
        ('king_node_history'), ('audit_log')
    ) AS expected(expected_name)
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables t
        WHERE t.table_schema = 'public' AND t.table_name = expected.expected_name
    )
$$, 'all §5 entities + meta tables exist');

-- (App-object scope: every assertion below filters to the migration-created
-- names — pgtap's own fixture objects in public are test-harness noise.)

-- 2. Type law over every column of the §5 app tables (0002 RE-staging tables
--    predate the type lock and stay as they are — ADR 0006).
SELECT is_empty($$
    SELECT c.table_name, c.column_name, c.udt_name
    FROM information_schema.columns c
    WHERE c.table_schema = 'public'
      AND c.table_name IN (
        'app_meta',
        'ticker_universe', 'top200_membership', 'export_manifest',
        'alert_rule', 'alert_event',
        'gamma_snapshot', 'spot_tick', 'flow_print', 'darkpool_print',
        'gamma_bucket_5m', 'expiry_rollup_hourly', 'strike_eod',
        'king_node_history', 'audit_log'
      )
      AND c.udt_name NOT IN ('text', 'date', 'timestamptz', 'int8', 'float8', 'bool')
$$, 'column types stay inside the locked type set');

-- 3. Append tables are range-partitioned.
SELECT is_empty($$
    SELECT expected_name
    FROM (VALUES
        ('gamma_snapshot'), ('spot_tick'), ('flow_print'), ('darkpool_print'),
        ('gamma_bucket_5m'), ('expiry_rollup_hourly'), ('strike_eod'),
        ('king_node_history'), ('audit_log')
    ) AS expected(expected_name)
    WHERE NOT EXISTS (
        SELECT 1 FROM pg_partitioned_table p
        JOIN pg_class c ON c.oid = p.partrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = expected.expected_name
          AND p.partstrat = 'r'
    )
$$, 'all 9 append tables are RANGE-partitioned');

-- 4. pg_partman registration: right control column, right interval, and
--    retention NULL (partman must never drop — retention job owns deletion).
SELECT is_empty($$
    SELECT expected.parent_table
    FROM (VALUES
        ('public.gamma_snapshot',       'ts',     '1 day'),
        ('public.spot_tick',            'ts',     '1 day'),
        ('public.flow_print',           'ts',     '1 day'),
        ('public.gamma_bucket_5m',      'bucket', '1 day'),
        ('public.expiry_rollup_hourly', 'hour',   '1 month'),
        ('public.strike_eod',           'day',    '1 month'),
        ('public.darkpool_print',       'ts',     '1 month'),
        ('public.king_node_history',    'ts',     '1 month'),
        ('public.audit_log',            'ts',     '1 month')
    ) AS expected(parent_table, control_col, part_interval)
    WHERE NOT EXISTS (
        SELECT 1
        FROM part_config pc
        WHERE pc.parent_table = expected.parent_table
          AND pc.partition_type = 'range'
          AND pc.control = expected.control_col
          AND pc.partition_interval::interval = expected.part_interval::interval
          AND pc.retention IS NULL
    )
$$, 'partman registered per parent with retention disabled');

-- 5. Premake children actually exist (create_parent did real work).
SELECT is_empty($$
    SELECT expected_name
    FROM (VALUES
        ('gamma_snapshot'), ('spot_tick'), ('flow_print'), ('darkpool_print'),
        ('gamma_bucket_5m'), ('expiry_rollup_hourly'), ('strike_eod'),
        ('king_node_history'), ('audit_log')
    ) AS expected(expected_name)
    WHERE (
        SELECT count(*) FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhparent
        WHERE c.relname = expected.expected_name
    ) < 5
$$, 'each parent has premake + default children');

-- 6. Index law: deterministic names, right method (spot_tick / darkpool_print
--    carry the (ticker, ts) B-tree in their PKs).
SELECT is_empty($$
    SELECT expected.index_name
    FROM (VALUES
        ('idx_gamma_snapshot_ticker_ts',            'btree'),
        ('idx_gamma_snapshot_brin_ts',              'brin'),
        ('idx_spot_tick_brin_ts',                   'brin'),
        ('idx_flow_print_ticker_ts',                'btree'),
        ('idx_flow_print_brin_ts',                  'brin'),
        ('idx_darkpool_print_brin_ts',              'brin'),
        ('idx_gamma_bucket_5m_ticker_bucket',       'btree'),
        ('idx_gamma_bucket_5m_brin_bucket',         'brin'),
        ('idx_expiry_rollup_hourly_ticker_hour',    'btree'),
        ('idx_expiry_rollup_hourly_brin_hour',      'brin'),
        ('idx_strike_eod_ticker_day',               'btree'),
        ('idx_strike_eod_brin_day',                 'brin'),
        ('idx_king_node_history_ticker_ts',         'btree'),
        ('idx_king_node_history_brin_ts',           'brin'),
        ('idx_audit_log_brin_ts',                   'brin')
    ) AS expected(index_name, method_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM pg_class ic
        JOIN pg_index i ON i.indexrelid = ic.oid
        JOIN pg_am am ON am.oid = ic.relam
        WHERE ic.relname = expected.index_name
          AND am.amname = expected.method_name
    )
$$, 'B-tree + BRIN index law holds with stable names');

-- 7. Unique indexes (PKs) include the partition-control column.
SELECT is_empty($$
    SELECT parents.parent_table
    FROM (VALUES
        ('gamma_snapshot',       'ts'),
        ('spot_tick',            'ts'),
        ('flow_print',           'ts'),
        ('darkpool_print',       'ts'),
        ('gamma_bucket_5m',      'bucket'),
        ('expiry_rollup_hourly', 'hour'),
        ('strike_eod',           'day'),
        ('king_node_history',    'ts'),
        ('audit_log',            'ts')
    ) AS parents(parent_table, control_col)
    WHERE NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_index i ON i.indrelid = c.oid AND i.indisunique
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = parents.control_col
        WHERE c.relname = parents.parent_table
          AND array_position(
              ('{' || replace(i.indkey::text, ' ', ',') || '}')::smallint[],
              a.attnum
          ) IS NOT NULL
    )
$$, 'every unique index covers the partition-control column');

-- 8. schema_version marker bumped by 0003.
SELECT is(
    (SELECT value FROM public.app_meta WHERE key = 'schema_version'),
    '2',
    'app_meta.schema_version tracks the current DDL set'
);

-- 9. RLS enabled on every public table (deny-default + API double-check law;
--    app_meta + 0002 tables carry RLS with no policies = owner-only).
SELECT is_empty($$
    SELECT expected_name
    FROM (VALUES
        ('app_meta'), ('contract_daily_stats'), ('underlying_daily_stats'),
        ('ticker_universe'), ('top200_membership'), ('export_manifest'),
        ('alert_rule'), ('alert_event'),
        ('gamma_snapshot'), ('spot_tick'), ('flow_print'), ('darkpool_print'),
        ('gamma_bucket_5m'), ('expiry_rollup_hourly'), ('strike_eod'),
        ('king_node_history'), ('audit_log')
    ) AS expected(expected_name)
    WHERE NOT EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = expected.expected_name
          AND c.relrowsecurity
    )
$$, 'RLS enabled on all 17 public tables');

SELECT * FROM finish();
ROLLBACK;
