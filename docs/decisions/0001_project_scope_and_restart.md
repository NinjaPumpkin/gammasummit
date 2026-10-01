# 0001 — Project restart, scope, and data tiers

Date: 2026-09-30 · Status: accepted

## Context

SignalForge/GammaSummit production runs on Supabase (38 GB measured, growing
3–6 GB/day raw) with per-ticker tables, text timestamps, and anon-readable
grants. The bill scales with history; the schema has anti-patterns that are
expensive to retrofit in place. Owner wants a clean, meticulous foundation
rather than repeated retrofitting.

## Decisions

1. **New project** `~/Desktop/Github-Projects/gammasummit` is the canonical
   build going forward. Code developed from scratch; SignalForge logic re-derived
   deliberately via `docs/ops/migration-from-signalforge.md`. SignalForge stays
   production until measured cutover.
2. **Data tiers:** T0 raw 24–48h → T1 5-min buckets 30d → T2 rollups 90d–1yr →
   T3 Parquet cold (external disk + B2/R2). Owner tightened raw to 24–48h for
   minimum overhead (supersedes the 72h figure in earlier planning docs).
3. **Universe:** all UW tickers (~609) collected; top-200 live by trailing 20d
   options volume/OI (monthly refresh); long tail EOD + lazy intraday backfill.
4. **Access model:** frontend → API → database. Deny-by-default grants, no anon
   data reads (measured SignalForge exposure: 1,257/1,382 tables without RLS).
5. **Storage rules:** one partitioned table per entity, `timestamptz`/`date`
   types, `(ticker, timestamp DESC)` composites. No per-ticker tables.
6. **Stack:** Postgres (Supabase slim) hot, Parquet + DuckDB cold, Python
   3.10-compatible backend, FastAPI planned, no broker/microservices in v1.

## Consequences

- History no longer drives the Supabase bill — the fix is retention shape, not
  vendor switching.
- Two systems run in parallel during migration (cost + ops overhead for a
  bounded period).
- Rebuilding ingest/API costs weeks now; avoids repeated retrofit cycles later.
- 24–48h raw means backtests needing intraday fidelity beyond 48h must read T3
  Parquet via DuckDB (by design).

## Alternatives considered

- Optimize SignalForge in place: rejected — retrofitting 1,232 tables and text
  columns is comparable work to a clean build with worse payoff.
- SpacetimeDB: rejected — real-time WASM app DB, wrong shape for analytical
  time-series.
- Self-host everything from home machines: rejected for prod (uptime, CGNAT,
  residential bandwidth) — dev/internal only.
