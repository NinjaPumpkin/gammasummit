-- 0003_partitioned_schema.sql — T0/T1/T2 entities, types, partitioning (card E2.1).
--
-- Entities per docs/architecture/master-architecture.md §5. Types locked:
-- timestamptz, date, bigint, double precision (+ text identifiers, boolean).
-- Indexes: (ticker, timestamp DESC) B-tree + BRIN on ts for append tables.
-- Partitions managed by pg_partman (see registration block at the bottom).
--
-- Expand-only by law (docs/build/code-structure-and-release.md §4): forward
-- migrations, never alter/drop in place while serving.
--
-- Retention law (ultraplan sequencing rule 5 + docs/ops/data-tiering.md):
-- retention jobs ship disabled until export manifests are verified twice.
-- Partman `retention` is therefore left NULL on every parent — partman never
-- drops anything; the manifest-verified retention job (P2, --dry-run default)
-- owns deletion.
--
-- Partitioning decision (ADR 0006): time-range partitions via pg_partman on
-- the time column; per-ticker access served by (ticker, ts DESC) B-trees.
-- pg_partman manages time levels only — a ticker-list level would need a
-- second custom maintenance path (single-scheduler law). Revisit trigger in
-- ADR 0006.
--
-- Apply target: the gammasummit app Postgres (Supabase slim). Test image:
-- public.ecr.aws/supabase/postgres (CI pins the exact tag).

-- ---------------------------------------------------------------------------
-- Extensions. pg_partman is required by this schema. pgaudit backs the audit
-- trail (master-architecture §5/§7) and is required on the Supabase target;
-- on a bare Postgres it degrades with a warning (the audit_log table below is
-- the app-level trail and is always present).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_partman WITH SCHEMA extensions;
EXCEPTION WHEN OTHERS THEN
    CREATE EXTENSION IF NOT EXISTS pg_partman;
END
$$;

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pgaudit WITH SCHEMA extensions;
EXCEPTION WHEN OTHERS THEN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pgaudit;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'pgaudit unavailable: DB-level audit trail off; app audit_log table still enforced';
    END;
END
$$;

-- ---------------------------------------------------------------------------
-- Application roles (deny-default: nothing exists until granted in 0004).
-- LOGIN with no password — credentials are provisioned at deploy time via
-- /etc/gammasummit/env (secrets never in git/chat, never in migrations).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gammasummit_api') THEN
        CREATE ROLE gammasummit_api WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 20;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gammasummit_ingest') THEN
        CREATE ROLE gammasummit_ingest WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 20;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'gammasummit_jobs') THEN
        CREATE ROLE gammasummit_jobs WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 20;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Catalog + policy + ops + product (non-partitioned)
-- ---------------------------------------------------------------------------

-- universe catalog: all UW tickers (~609 today) — data law: ALL tickers.
CREATE TABLE ticker_universe (
    ticker      TEXT        PRIMARY KEY,
    name        TEXT,
    is_active   BOOLEAN     NOT NULL DEFAULT true,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- top-200 LIVE policy: ranked by trailing 20d options volume/OI, recomputed
-- monthly (docs/ops/data-tiering.md "Universe policy"). month = first of month.
CREATE TABLE top200_membership (
    ticker          TEXT        NOT NULL,
    month           DATE        NOT NULL,
    rank            BIGINT      NOT NULL,
    options_volume  BIGINT,
    options_oi      BIGINT,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, month)
);

-- ops: 3-2-1 export manifests. verified_at gates every retention delete
-- (hard rule: retention never deletes un-exported data).
CREATE TABLE export_manifest (
    file_path    TEXT        NOT NULL,
    exported_at  TIMESTAMPTZ NOT NULL,
    tier         TEXT        NOT NULL,
    target       TEXT        NOT NULL,
    sha256       TEXT        NOT NULL,
    byte_size    BIGINT      NOT NULL,
    row_count    BIGINT,
    verified_at  TIMESTAMPTZ,
    PRIMARY KEY (file_path, exported_at)
);

-- product (v2 alerts; schema ships now — expand-first).
CREATE TABLE alert_rule (
    id          BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_ref    TEXT        NOT NULL,
    name        TEXT        NOT NULL,
    ticker      TEXT,
    metric      TEXT        NOT NULL,
    operator    TEXT        NOT NULL,
    threshold   DOUBLE PRECISION NOT NULL,
    channel     TEXT        NOT NULL,
    enabled     BOOLEAN     NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alert_event (
    alert_rule_id  BIGINT      NOT NULL REFERENCES alert_rule(id),
    ts             TIMESTAMPTZ NOT NULL,
    ticker         TEXT,
    value          DOUBLE PRECISION,
    message        TEXT,
    delivered      BOOLEAN     NOT NULL DEFAULT false,
    PRIMARY KEY (alert_rule_id, ts)
);

-- ---------------------------------------------------------------------------
-- T0 raw (retention 24–48h after manifest-verified export)
-- ---------------------------------------------------------------------------

-- grain: ticker,strike,expiry,ts — one strike cell per side split (the
-- within-expiry net_gex = call_gex − put_gex of the value model).
CREATE TABLE gamma_snapshot (
    ticker         TEXT        NOT NULL,
    expiry         DATE        NOT NULL,
    strike         DOUBLE PRECISION NOT NULL,
    ts             TIMESTAMPTZ NOT NULL,
    spot           DOUBLE PRECISION,
    call_oi        BIGINT,
    put_oi         BIGINT,
    call_volume    BIGINT,
    put_volume     BIGINT,
    call_bid       DOUBLE PRECISION,
    call_ask       DOUBLE PRECISION,
    put_bid        DOUBLE PRECISION,
    put_ask        DOUBLE PRECISION,
    call_iv        DOUBLE PRECISION,
    put_iv         DOUBLE PRECISION,
    call_delta     DOUBLE PRECISION,
    put_delta      DOUBLE PRECISION,
    call_gamma     DOUBLE PRECISION,
    put_gamma      DOUBLE PRECISION,
    call_vega      DOUBLE PRECISION,
    put_vega       DOUBLE PRECISION,
    call_theta     DOUBLE PRECISION,
    put_theta      DOUBLE PRECISION,
    source         TEXT        NOT NULL,
    PRIMARY KEY (ticker, expiry, strike, ts)
) PARTITION BY RANGE (ts);

CREATE TABLE spot_tick (
    ticker  TEXT        NOT NULL,
    ts      TIMESTAMPTZ NOT NULL,
    seq     BIGINT      NOT NULL DEFAULT 0,
    price   DOUBLE PRECISION NOT NULL,
    size    BIGINT,
    source  TEXT        NOT NULL,
    PRIMARY KEY (ticker, ts, seq)
) PARTITION BY RANGE (ts);

CREATE TABLE flow_print (
    occ         TEXT        NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    seq         BIGINT      NOT NULL DEFAULT 0,
    ticker      TEXT        NOT NULL,
    expiry      DATE        NOT NULL,
    strike      DOUBLE PRECISION NOT NULL,
    opt_right   TEXT        NOT NULL CHECK (opt_right IN ('C', 'P')),  -- contract right (C/P);
                                            -- `right` itself is a reserved word
    price       DOUBLE PRECISION NOT NULL,
    size        BIGINT      NOT NULL,
    premium     DOUBLE PRECISION,
    side        TEXT,
    bid         DOUBLE PRECISION,
    ask         DOUBLE PRECISION,
    spot        DOUBLE PRECISION,
    is_sweep    BOOLEAN     NOT NULL DEFAULT false,
    is_multileg BOOLEAN     NOT NULL DEFAULT false,
    source      TEXT        NOT NULL,
    PRIMARY KEY (occ, ts, seq)
) PARTITION BY RANGE (ts);

CREATE TABLE darkpool_print (
    ticker   TEXT        NOT NULL,
    ts       TIMESTAMPTZ NOT NULL,
    seq      BIGINT      NOT NULL DEFAULT 0,
    price    DOUBLE PRECISION NOT NULL,
    size     BIGINT      NOT NULL,
    premium  DOUBLE PRECISION,
    venue    TEXT,
    source   TEXT        NOT NULL,
    PRIMARY KEY (ticker, ts, seq)
) PARTITION BY RANGE (ts);

-- ---------------------------------------------------------------------------
-- T1 5-min buckets (retention 30d)
-- ---------------------------------------------------------------------------

CREATE TABLE gamma_bucket_5m (
    ticker          TEXT        NOT NULL,
    expiry          DATE        NOT NULL,
    strike          DOUBLE PRECISION NOT NULL,
    bucket          TIMESTAMPTZ NOT NULL,
    call_oi_first   BIGINT,
    call_oi_last    BIGINT,
    put_oi_first    BIGINT,
    put_oi_last     BIGINT,
    call_volume     BIGINT,
    put_volume      BIGINT,
    call_gamma_avg  DOUBLE PRECISION,
    put_gamma_avg   DOUBLE PRECISION,
    call_iv_avg     DOUBLE PRECISION,
    put_iv_avg      DOUBLE PRECISION,
    spot_close      DOUBLE PRECISION,
    samples         BIGINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (ticker, expiry, strike, bucket)
) PARTITION BY RANGE (bucket);

-- ---------------------------------------------------------------------------
-- T2 rollups (retention 90d–1yr). schema_version = rollup-calc version —
-- backfill invalidates only its own version (code-structure §4).
-- ---------------------------------------------------------------------------

CREATE TABLE expiry_rollup_hourly (
    ticker        TEXT        NOT NULL,
    expiry        DATE        NOT NULL,
    hour          TIMESTAMPTZ NOT NULL,
    call_gex      DOUBLE PRECISION,
    put_gex       DOUBLE PRECISION,
    net_gex       DOUBLE PRECISION,
    call_vex      DOUBLE PRECISION,
    put_vex       DOUBLE PRECISION,
    net_vex       DOUBLE PRECISION,
    spot_open     DOUBLE PRECISION,
    spot_close    DOUBLE PRECISION,
    schema_version BIGINT     NOT NULL DEFAULT 1,
    PRIMARY KEY (ticker, expiry, hour)
) PARTITION BY RANGE (hour);

CREATE TABLE strike_eod (
    ticker      TEXT        NOT NULL,
    expiry      DATE        NOT NULL,
    strike      DOUBLE PRECISION NOT NULL,
    day         DATE        NOT NULL,
    call_oi     BIGINT,
    put_oi      BIGINT,
    call_volume BIGINT,
    put_volume  BIGINT,
    call_gex    DOUBLE PRECISION,
    put_gex     DOUBLE PRECISION,
    net_gex     DOUBLE PRECISION,
    spot_close  DOUBLE PRECISION,
    schema_version BIGINT   NOT NULL DEFAULT 1,
    PRIMARY KEY (ticker, expiry, strike, day)
) PARTITION BY RANGE (day);

CREATE TABLE king_node_history (
    ticker    TEXT        NOT NULL,
    node      TEXT        NOT NULL,
    ts        TIMESTAMPTZ NOT NULL,
    node_tier TEXT        NOT NULL,
    strike    DOUBLE PRECISION,
    value     DOUBLE PRECISION,
    spot      DOUBLE PRECISION,
    source    TEXT        NOT NULL,
    PRIMARY KEY (ticker, node, ts)
) PARTITION BY RANGE (ts);

-- security: app-level audit trail (auth events, admin actions). pgaudit covers
-- the DB-level trail into the server log (master-architecture §5).
CREATE TABLE audit_log (
    seq     BIGINT      GENERATED ALWAYS AS IDENTITY,
    actor   TEXT        NOT NULL,
    ts      TIMESTAMPTZ NOT NULL,
    action  TEXT        NOT NULL,
    target  TEXT,
    detail  TEXT,
    PRIMARY KEY (actor, ts, seq)
) PARTITION BY RANGE (ts);

-- ---------------------------------------------------------------------------
-- Index law: (ticker, timestamp DESC) B-tree + BRIN on ts for append tables.
-- spot_tick / darkpool_print carry the law in their PKs (ticker, ts, …).
-- ---------------------------------------------------------------------------
CREATE INDEX idx_gamma_snapshot_ticker_ts ON gamma_snapshot (ticker, ts DESC);
CREATE INDEX idx_gamma_snapshot_brin_ts ON gamma_snapshot USING brin (ts);
CREATE INDEX idx_spot_tick_brin_ts ON spot_tick USING brin (ts);
CREATE INDEX idx_flow_print_ticker_ts ON flow_print (ticker, ts DESC);
CREATE INDEX idx_flow_print_brin_ts ON flow_print USING brin (ts);
CREATE INDEX idx_darkpool_print_brin_ts ON darkpool_print USING brin (ts);
CREATE INDEX idx_gamma_bucket_5m_ticker_bucket ON gamma_bucket_5m (ticker, bucket DESC);
CREATE INDEX idx_gamma_bucket_5m_brin_bucket ON gamma_bucket_5m USING brin (bucket);
CREATE INDEX idx_expiry_rollup_hourly_ticker_hour ON expiry_rollup_hourly (ticker, hour DESC);
CREATE INDEX idx_expiry_rollup_hourly_brin_hour ON expiry_rollup_hourly USING brin (hour);
CREATE INDEX idx_strike_eod_ticker_day ON strike_eod (ticker, day DESC);
CREATE INDEX idx_strike_eod_brin_day ON strike_eod USING brin (day);
CREATE INDEX idx_king_node_history_ticker_ts ON king_node_history (ticker, ts DESC);
CREATE INDEX idx_king_node_history_brin_ts ON king_node_history USING brin (ts);
CREATE INDEX idx_audit_log_brin_ts ON audit_log USING brin (ts);

-- ---------------------------------------------------------------------------
-- pg_partman registration. Extension schema resolved dynamically (platform
-- installs into `extensions`, bare installs into their creation schema).
-- p_automatic_maintenance = 'on' means run_maintenance() processes these when
-- called — the single scheduler chosen in P2 (pg_cron XOR backend timers,
-- never both) is the only caller. retention stays NULL: partman never drops.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    partman_schema text;
    parent record;
BEGIN
    SELECT n.nspname INTO partman_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'pg_partman';
    IF partman_schema IS NULL THEN
        RAISE EXCEPTION 'pg_partman extension missing — 0003 requires it';
    END IF;

    FOR parent IN
        SELECT * FROM (VALUES
            ('public.gamma_snapshot',         'ts',    '1 day'),
            ('public.spot_tick',              'ts',    '1 day'),
            ('public.flow_print',             'ts',    '1 day'),
            ('public.gamma_bucket_5m',        'bucket', '1 day'),
            ('public.expiry_rollup_hourly',   'hour',  '1 month'),
            ('public.strike_eod',             'day',   '1 month'),
            ('public.darkpool_print',         'ts',    '1 month'),
            ('public.king_node_history',      'ts',    '1 month'),
            ('public.audit_log',              'ts',    '1 month')
        ) AS t(parent_table, control_col, part_interval)
    LOOP
        EXECUTE format(
            'SELECT %I.create_parent(p_parent_table => %L, p_control => %L, '
            || 'p_type => ''range'', p_interval => %L, p_premake => 4, '
            || 'p_default_table => true, p_automatic_maintenance => ''on'')',
            partman_schema, parent.parent_table, parent.control_col, parent.part_interval
        );
    END LOOP;
END
$$;

-- Schema marker (0001_app_meta.sql) — T2 tables carry their own
-- schema_version column for rollup invalidation; this one tracks the DDL set.
UPDATE app_meta SET value = '2', updated_at = now() WHERE key = 'schema_version';
