# GammaSummit

Options-flow intelligence platform (TWEATerminal-style): gamma/GEX dashboards,
flow analytics, OI movers, multi-ticker live data from Unusual Whales / PHX / IBKR.

**Status: build scaffold in place (E1.1) — manifests, API skeleton, contract
sync, migration lint, frontend placeholder. P0 calc-parity gate still open.**

## Quickstart (fresh clone)

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # backend + tooling
.venv/bin/python -m pytest backend/tests                      # tests
.venv/bin/ruff check .                                        # lint
python3 scripts/migration_lint.py                             # migration gate
python3 scripts/contract_sync.py --check                      # zod<->pydantic sync
npm install && npm run build                                  # frontend (workspace)
```

## Docs map

| Folder | Contents |
|---|---|
| `docs/build/README.md` | **Builder guide — START HERE** (workstreams, gates, hard rules) |
| `docs/architecture/` | floor plan, design reference, AI stack, topology, product inventory |
| `docs/build/` | ultraplan, parity checklist, RE campaign, value-model verdicts |
| `docs/ops/` | tiering, security, operations, backup, offboarding, migration |
| `docs/decisions/` | ADRs (architectural law) |

## Relationship to SignalForge

`~/Desktop/Github Projects/SignalForge` is the **reference implementation and
current production system**. It keeps running until this project is proven and
cut over. Logic gets re-derived and re-written here lean; nothing is copied
blind. See `docs/ops/migration-from-signalforge.md` for the reuse map and the
anti-patterns that must NOT be carried over.

## Core principles

1. **Tiered storage.** Raw data ages out in 24–48h. History lives as rollups
   (hot) and Parquet (cold). The bill never scales with history.
2. **API-first.** The frontend talks to our API only. Never Supabase directly.
   Deny-by-default database access.
3. **One table per entity**, partitioned — no per-ticker tables.
4. **Lean by default.** Smallest dependency set, smallest schema, smallest
   query surface that does the job. Python 3.10-compatible (VPS constraint).
5. **Export-first, non-destructive.** Anything that deletes data exports it
   first. 3-2-1 backup rule for cold storage.
6. **Observability is a feature.** Data freshness ("last updated") is both a
   product feature and an alert.

## Data tiers (summary — full spec: `docs/ops/data-tiering.md`)

| Tier | Content | Retention | Store |
|------|---------|-----------|-------|
| T0 | raw full-cadence snapshots, top-200 live | 24–48h | Postgres |
| T1 | 5-min per-strike/expiry buckets | 30d | Postgres |
| T2 | hourly + EOD rollups | 90d–1yr | Postgres |
| T3 | full-fidelity raw, Parquet | indefinite | external disk + B2/R2 copy |

## Universe policy

- All Unusual Whales tickers collected (~609 today).
- **Top 200 live** (intraday T0/T1) — ranked by trailing 20d options volume/OI,
  refreshed monthly.
- Long tail: EOD rollups (T2) always; intraday backfilled lazily on page open.

## Layout

| Path | Purpose |
|------|---------|
| `backend/` | Python: `core/`, `ingest/`, `jobs/`, `api/`, `tests/` |
| `db/` | migrations, schema docs, rollup/query definitions |
| `frontend/` | dashboard web app (API consumer) |
| `deploy/` | systemd units, docker, VPS layout |
| `scripts/` | one-off ops scripts |
| `data/` | local dev data (gitignored) |
| `docs/` | architecture, tiering, security, operations, ADRs |

**Start here: [`docs/architecture/master-architecture.md`](docs/architecture/master-architecture.md)** —
the floor plan — and [`docs/build/ultraplan.md`](docs/build/ultraplan.md) — the execution
plan. UI follows skylit.ai layout patterns
(`docs/architecture/design-reference-skylit.md`, parity gate:
`docs/build/parity-checklist-skylit.md`).

## Naming conventions

- Dirs: lowercase single word (`backend`, `db`) or kebab-case for docs files
- Python: PEP 8, `snake_case` modules, type hints everywhere
- SQL migrations: `db/migrations/NNNN_short_description.sql`
- ADRs: `docs/decisions/NNNN_title.md`
- systemd units: `deploy/systemd/gammasummit-<role>.service`
- Env vars: `GAMMASUMMIT_*` prefix; secrets only in env files (gitignored)

## Build order

1. Foundation: `backend/core` + `db/` schema/migrations (types correct from day 1)
2. Ingest + tiering jobs (downsampler, rollups, retention/export)
3. API layer (security model first: no anon data access)
4. Frontend (reads API only)
5. Deploy/ops + measured cutover from SignalForge

Each phase lands with tests and an ADR. Slow and meticulous — this is the build
we do not redo.
