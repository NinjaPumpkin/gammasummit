# ADR 0006 — Partitioned schema, deny-default grants, backend/core spine (P1)

Date: 2026-10-02 · Status: accepted · Card: E2.1 (ultraplan P1, WS B)

Context: P1 foundations — `backend/core` spine + `db/migrations` entities of
`master-architecture.md` §5 + pgtap invariants + CI security gates. Verified on
`public.ecr.aws/supabase/postgres:17.6.1.063` (PG 17.6, the Supabase extension
set: pg_partman 5.3.1, pgaudit, pgtap, pgmq).

## Decisions

1. **Schema lands in `0003_partitioned_schema.sql` + `0004_deny_default_grants.sql`.**
   Ultrapan's "db/migrations/0001" is phase language: the `NNNN_` uniqueness +
   forward-only law (code-structure §4) wins — 0001/0002 already exist and are
   applied-history, so the schema continues at 0003. Same for the ADR number:
   ultraplan says "ADR 0004 records schema" but `0004_cdc_rejected.md` holds
   that slot, and `0005_ops_brain_interop.md` (same day) took 0005 → this ADR
   is 0006 (P2's ADR takes the next free number).

2. **Partitioning: time-RANGE via pg_partman, not ticker-list subpartitioning.**
   §5 says "ticker list + ts range" for `gamma_snapshot`; implemented as
   RANGE(ts) with `(ticker, ts DESC)` B-tree + BRIN(ts). Rationale: pg_partman
   manages time/id levels only — a ticker-LIST level (609 tickers, monthly
   churn) needs custom partition maintenance = a second scheduled mechanism,
   violating the single-scheduler law. Access-path parity is served by the
   B-tree; retention drops whole day/month partitions. Intervals: daily for
   T0 + T1 (`gamma_snapshot`, `spot_tick`, `flow_print`, `gamma_bucket_5m`),
   monthly for T2 + audit (`expiry_rollup_hourly`, `strike_eod`,
   `darkpool_print`, `king_node_history`, `audit_log`), premake 4 + default
   partition. **Revisit triggers** (any one): a single day-partition exceeds
   ~5 GB steady state; per-ticker erase/retention is required; measured
   pruning shows ticker scans reading > 25% of a day partition.

3. **Partman never drops anything.** `part_config.retention` stays NULL on
   every parent (asserted by pgtap). Deletion belongs to the manifest-verified
   retention job (P2, `--dry-run` default, ships disabled until export
   manifests verify twice — ultraplan sequencing rule 5).
   `run_maintenance()` has exactly ONE caller: the P2 scheduler decision
   (pg_cron XOR backend timers — never both). The partman background worker is
   not loaded.

4. **Deny-default grants + RLS, Supabase-defaults explicitly revoked.**
   Verified: the Supabase image grants ALL on public tables to
   anon/authenticated/service_role via default ACLs at CREATE time (the exact
   SignalForge anon-SELECT failure). 0004 revokes those defaults for the
   migration role and retroactively on all objects, then grants least
   privilege to three LOGIN roles created without passwords (credentials
   provisioned at deploy time, never in git/chat):
   - `gammasummit_api` — SELECT everywhere + alert_rule/alert_event CRUD
   - `gammasummit_ingest` — T0 INSERT/UPDATE/SELECT + catalog SELECT (UW PHX
     is the only production source)
   - `gammasummit_jobs` — SELECT everywhere + T1/T2/manifest/audit writes;
     no DELETE anywhere (partition drops run as table owner)
   RLS is enabled on all 17 public tables with per-role policies mirroring the
   grants ("deny-default grants, RLS + API double-check", master-architecture
   §7); `app_meta` + the 0002 RE-staging tables carry RLS with no policies
   (owner/service-role only). Grants + RLS coherence are CI-enforced by
   `db/tests/0002_grants_regression.sql`.

5. **Types locked** per §5 (timestamptz, date, bigint, double precision +
   text identifiers/boolean), CI-enforced by pgtap. The 0002 RE-staging tables
   predate the lock (NUMERIC/CHAR) and stay as they are — they are not §5
   entities. `right` is a reserved word: `flow_print` uses `opt_right`; 0002's
   column is the quoted `"right"` (keeps the e08 payload key working).

6. **0002 was fixed in place (allowed because it never applied anywhere).**
   The unquoted `right` made `0002_contract_daily_stats.sql` a parse error on
   every Postgres; probed UW PHX PostgREST read-only on 2026-10-02: both
   tables absent (PGRST205). Zero applied state ⇒ no history to preserve; a
   fix-forward migration would be theater. If a DB with partial 0002 state
   ever surfaces (raw-psql autocommit), reconcile it explicitly before use.

7. **`backend/core` owns the boring spine** (config/errors/logging/db) per
   ultraplan P1 + the E2.1 card, reconciling code-structure §1 "core is pure":
   the pure-calc modules (`exposure.py`, `nodes.py`, …) keep the no-DB/no-env
   law; the spine modules are infrastructure (pydantic-settings, asyncpg,
   stdlib logging) imported by everyone. `api/deps.py` re-exports `Settings`.
   Logging is structured JSON with request-id + payload-ts context and
   secret-scrubbing in the formatter (tokens/DSNs never reach journald).

8. **`get_advisors` gate.** The literal call is a Supabase Management API read
   against a hosted project; the app Postgres is not provisioned yet, so it
   cannot run today. Encoded as `scripts/security_advisors_check.py` (runs the
   real `advisors/security` + `advisors/performance` calls, fails on ERROR the
   moment `SUPABASE_ACCESS_TOKEN` + `GAMMASUMMIT_SUPABASE_PROJECT_REF` exist;
   SKIPS loudly otherwise — never claims clean). CI's `supabase-security` job
   runs it plus `supabase db lint -s public --level error --fail-on error`
   (zero-ERROR verified on the pinned image; note CLI 2.95.4 `db lint` is the
   typing linter and needs `PGSSLMODE=disable` for non-TLS test DBs).

9. **CI additions** (`.github/workflows/ci.yml`, on top of E1.2's five jobs):
   `db-tests` (migrations apply clean on empty DB + pgtap schema invariants +
   grants regression via `scripts/db_tests.py`) and `supabase-security` (lint
   + advisors gate), both against the pinned Supabase Postgres image.

## Consequences

- T0 24–48h retention is a partition drop after manifest verification — cheap
  and safe; hot DB size stays bounded (NFR §10 ≤ 10 GB).
- Every future table must ship with: type-law columns, partman registration
  (if append), grants + RLS policies in the same migration, and pgtap
  expectations updated — CI enforces all four.
- `scripts/db_tests.py` is the one entry point for migration + pgtap runs
  (local + CI); it wraps each migration in its own transaction (a failed file
  leaves zero partial state).

## Rejected

- Ticker-LIST first-level partitioning: unmaintainable with pg_partman alone
  (see decision 2).
- Editing 0002's types to satisfy the type lock: RE-staging schema, not worth
  churn with e08 tooling written against it.
- Putting RLS off "until the API lands": the SignalForge anon-SELECT class of
  bug is exactly what deny-default + RLS-at-DDL-time prevents.
