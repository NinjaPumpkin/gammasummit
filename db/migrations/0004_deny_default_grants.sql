-- 0004_deny_default_grants.sql — deny-default grants + RLS (card E2.1).
--
-- docs/ops/security.md: database grants deny-by-default, service role lives
-- only in server env. SignalForge lesson (measured 2026-09-30): anon SELECT on
-- gamma tables — never again. Supabase default ACLs grant ALL on public tables
-- to anon/authenticated/service_role at CREATE time (verified on
-- public.ecr.aws/supabase/postgres:17.6.1.063), so this migration revokes
-- those both retroactively and for the future, then grants least privilege.
--
-- RLS (master-architecture §7: "deny-default grants, RLS + API double-check"):
-- every app table gets RLS enabled with explicit per-role policies mirroring
-- the grants below — a leaked connection string cannot widen access.
--
-- Roles (created in 0003): gammasummit_api (read-mostly query surface),
-- gammasummit_ingest (UW T0 writes), gammasummit_jobs (rollups/retention/
-- export). Partition DDL (retention) runs as the table owner via the single
-- P2 scheduler — never as an app role.

-- ---------------------------------------------------------------------------
-- 1. Deny future defaults: new objects no longer inherit Supabase's public
--    grants (grantor = the migration role).
-- ---------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM PUBLIC;

DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role', 'pgbouncer']
    LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', role_name);
        END IF;
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 2. Deny existing grants (the anon-trap cleanup) + lock the schema.
-- ---------------------------------------------------------------------------
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role', 'pgbouncer']
    LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA public FROM %I', role_name);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', role_name);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', role_name);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', role_name);
        END IF;
    END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- 3. Least-privilege grants.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO gammasummit_api, gammasummit_ingest, gammasummit_jobs;

-- API: read everything the query surface needs (authz double-checked in the
-- API per security.md — BOLA protection is per-resource at the app layer).
GRANT SELECT ON ticker_universe, top200_membership, export_manifest TO gammasummit_api;
GRANT SELECT ON gamma_snapshot, spot_tick, flow_print, darkpool_print TO gammasummit_api;
GRANT SELECT ON gamma_bucket_5m, expiry_rollup_hourly, strike_eod, king_node_history TO gammasummit_api;
GRANT SELECT ON audit_log TO gammasummit_api;
-- alert rules are user product data: API manages them per-resource.
GRANT SELECT, INSERT, UPDATE, DELETE ON alert_rule, alert_event TO gammasummit_api;

-- Ingest (UW PHX is the ONLY production source): T0 batch-upsert + catalog
-- reads for the fleet scheduler. No T1/T2, no deletes.
GRANT SELECT ON ticker_universe, top200_membership TO gammasummit_ingest;
GRANT SELECT, INSERT, UPDATE ON gamma_snapshot, spot_tick, flow_print, darkpool_print TO gammasummit_ingest;

-- Jobs: read all tiers, write T1/T2 + ops manifests + audit trail. Deletes and
-- partition drops stay with the table owner (manifest-verified retention job).
GRANT SELECT ON ticker_universe, top200_membership, export_manifest, alert_rule, alert_event TO gammasummit_jobs;
GRANT SELECT ON gamma_snapshot, spot_tick, flow_print, darkpool_print TO gammasummit_jobs;
GRANT SELECT, INSERT, UPDATE ON gamma_bucket_5m, expiry_rollup_hourly, strike_eod, king_node_history TO gammasummit_jobs;
GRANT SELECT, INSERT, UPDATE ON export_manifest TO gammasummit_jobs;
GRANT SELECT, INSERT ON audit_log TO gammasummit_jobs;

-- Identity sequences (alert_rule.id, audit_log.seq).
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gammasummit_api, gammasummit_ingest, gammasummit_jobs;

-- ---------------------------------------------------------------------------
-- 4. RLS enabled everywhere + explicit per-role policies (mirror of step 3).
-- ---------------------------------------------------------------------------
ALTER TABLE ticker_universe ENABLE ROW LEVEL SECURITY;
ALTER TABLE top200_membership ENABLE ROW LEVEL SECURITY;
ALTER TABLE export_manifest ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_rule ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE gamma_snapshot ENABLE ROW LEVEL SECURITY;
ALTER TABLE spot_tick ENABLE ROW LEVEL SECURITY;
ALTER TABLE flow_print ENABLE ROW LEVEL SECURITY;
ALTER TABLE darkpool_print ENABLE ROW LEVEL SECURITY;
ALTER TABLE gamma_bucket_5m ENABLE ROW LEVEL SECURITY;
ALTER TABLE expiry_rollup_hourly ENABLE ROW LEVEL SECURITY;
ALTER TABLE strike_eod ENABLE ROW LEVEL SECURITY;
ALTER TABLE king_node_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
-- 0001/0002 tables: RLS on, no policies = strictly owner/service-role access
-- (advisors flag any public table without RLS; e08 PostgREST writes use the
-- service role which bypasses RLS by design).
ALTER TABLE app_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE contract_daily_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE underlying_daily_stats ENABLE ROW LEVEL SECURITY;

-- API read policy (all app tables).
CREATE POLICY api_select ON ticker_universe FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON top200_membership FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON export_manifest FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON gamma_snapshot FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON spot_tick FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON flow_print FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON darkpool_print FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON gamma_bucket_5m FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON expiry_rollup_hourly FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON strike_eod FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON king_node_history FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_select ON audit_log FOR SELECT TO gammasummit_api USING (true);
CREATE POLICY api_all ON alert_rule FOR ALL TO gammasummit_api USING (true) WITH CHECK (true);
CREATE POLICY api_all ON alert_event FOR ALL TO gammasummit_api USING (true) WITH CHECK (true);

-- Ingest: T0 writes + catalog reads.
CREATE POLICY ingest_all ON gamma_snapshot FOR ALL TO gammasummit_ingest USING (true) WITH CHECK (true);
CREATE POLICY ingest_all ON spot_tick FOR ALL TO gammasummit_ingest USING (true) WITH CHECK (true);
CREATE POLICY ingest_all ON flow_print FOR ALL TO gammasummit_ingest USING (true) WITH CHECK (true);
CREATE POLICY ingest_all ON darkpool_print FOR ALL TO gammasummit_ingest USING (true) WITH CHECK (true);
CREATE POLICY ingest_select ON ticker_universe FOR SELECT TO gammasummit_ingest USING (true);
CREATE POLICY ingest_select ON top200_membership FOR SELECT TO gammasummit_ingest USING (true);

-- Jobs: reads everywhere, writes to T1/T2 + ops + audit.
CREATE POLICY jobs_select ON ticker_universe FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_select ON top200_membership FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_select ON alert_rule FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_select ON alert_event FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_select ON gamma_snapshot FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_select ON spot_tick FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_select ON flow_print FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_select ON darkpool_print FOR SELECT TO gammasummit_jobs USING (true);
CREATE POLICY jobs_all ON gamma_bucket_5m FOR ALL TO gammasummit_jobs USING (true) WITH CHECK (true);
CREATE POLICY jobs_all ON expiry_rollup_hourly FOR ALL TO gammasummit_jobs USING (true) WITH CHECK (true);
CREATE POLICY jobs_all ON strike_eod FOR ALL TO gammasummit_jobs USING (true) WITH CHECK (true);
CREATE POLICY jobs_all ON king_node_history FOR ALL TO gammasummit_jobs USING (true) WITH CHECK (true);
CREATE POLICY jobs_all ON export_manifest FOR ALL TO gammasummit_jobs USING (true) WITH CHECK (true);
CREATE POLICY jobs_insert ON audit_log FOR INSERT TO gammasummit_jobs WITH CHECK (true);
CREATE POLICY jobs_select ON audit_log FOR SELECT TO gammasummit_jobs USING (true);
