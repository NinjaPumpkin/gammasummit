# ADR 0004 — Real-time CDC (Postgres WAL → DuckDB): rejected for v1

Date: 2026-09-30. Status: **Rejected** (revisit only if a stated trigger fires).

Context: owner shared a "Real-Time CDC Pipeline" guide (Supabase Postgres →
wal2json → local DuckDB, <1 s replication, LSN-tracked idempotent consumer).
Question: worth implementing in GammaSummit?

## Decision

Not for v1. The guide solves "analytics without touching OLTP + zero ETL lag" —
that problem is already solved differently here, at lower standing cost.

## Why not

| Guide's promise | Our reality |
|---|---|
| Sub-second analytics replica | UW feeds arrive at ~1–2 min cadence — a <1 s replica of a 2-min-cadence store adds nothing. T1 5-min buckets + rollups cover analysis; DuckDB `postgres` federation covers ad-hoc live joins **with zero replication** |
| Avoid OLTP scan load | Rollups + partitioned schema + keyset already keep analytical reads off raw tables (that is the tiering design) |
| Minimal overhead | In practice: `wal_level=logical` + replication slots + `REPLICA IDENTITY FULL` (2× WAL images on tables churning 4–8M rows/day) + a forever-daemon with LSN state to babysit. A stalled slot **retains WAL and can fill the disk** = prod-availability risk. Violates "as little overhead as possible" and the single-scheduler/ops-simplicity rules |
| Freshness vs nightly ETL | Our freshness contract is payload-timestamp monitoring + verdict alarms (ops lesson), not a replication channel |

## What we keep from the guide

- Idempotent upsert + crash-safe state checkpointing — already our ingest pattern.
- "Never run analytics on the OLTP path" — already law (frontends → API; analysis → T1/T2/DuckDB).

## Revisit triggers (any one)

1. Intraday research needs a **local live mirror** on a Mac (e.g. streaming backtests during the session) — then run the consumer **dev-only**, key-only `REPLICA IDENTITY DEFAULT`, on 2–3 small tables (never the raw churn tables).
2. We self-host Postgres (no managed WAL limits) AND multiple real-time consumers appear.
3. UW ever exposes a true streaming API and end-to-end sub-second latency becomes a product requirement.

Until a trigger fires: tiering + rollups + DuckDB federation stand as the
analytical architecture.
