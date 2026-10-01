# db/

Schema source of truth. Everything that touches the database starts here.

## Layout

```
db/
├── migrations/   # NNNN_short_description.sql — ordered, immutable once merged
├── schema/       # human-readable schema docs per entity
└── queries/      # rollup definitions, analytical queries, DuckDB SQL
```

## Hard rules

1. **Migrations precede writer restart.** Reader cutovers follow seeded and
   validated writers — never the reverse (inherited ops rule from SignalForge).
2. Migration files are immutable after merge; fixes are new migrations.
3. Every migration has a matching note in `schema/` (what + why + rollback).
4. Types from day 1: `timestamptz` for event time, `date` for expiries,
   `numeric`/`double precision` for metrics, `bigint` for counts. **Never text.**
5. One table per entity. Partition by ticker (list) + time (range). No
   per-ticker tables, ever.
6. Indexes: `(ticker, timestamp DESC)` composite on time-series tables;
   justify every additional index (write cost is real).
7. Grants deny-by-default. No anon access to data tables. App access via
   service role held only by the API/backend (see `../docs/ops/security.md`).
8. Rollup tables are append-only and recomputable from a lower tier.

## Tier ownership

| Tier | Tables | Producer | Consumer |
|------|--------|----------|----------|
| T0 | raw snapshots | ingest | downsampler, live view |
| T1 | 5-min buckets | downsampler | dashboards, charts |
| T2 | hourly + EOD rollups | rollup jobs | history views, on-demand |
| T3 | Parquet files | retention/export | DuckDB |

Full spec: `../docs/ops/data-tiering.md`.
