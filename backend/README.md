# backend/

Python 3.10-compatible services. No code yet — this defines the target layout
so modules land in the right place from the first commit.

## Layout

```
backend/
├── core/        # config, logging, errors, db connections, models, metrics
├── ingest/      # source fetchers (UW, PHX, IBKR) + T0 writers
├── jobs/        # downsampler, rollups, retention/export, lazy backfill
├── api/         # HTTP layer (FastAPI planned): routes, auth, validation
└── tests/       # unit + integration; fixtures only, never live transports
```

## Rules

- Python 3.10 syntax floor (VPS runs 3.10.12). No 3.11+ syntax.
- Dependencies minimal: every new package needs a reason in the PR.
- Type hints everywhere; `ruff` clean before commit.
- Config via env (`GAMMASUMMIT_*`), validated at startup, fail fast (ch.14).
- Tests must be unable to construct live clients or write outside tmp fixtures.
- Imports: `core` is imported by all; `ingest`/`jobs`/`api` never import each
  other except through `core` interfaces.

## Reuse policy from SignalForge

Logic is re-derived from the reference implementation, not copied. Known-good
patterns to port deliberately (see `../docs/ops/migration-from-signalforge.md`):
batch upsert + retry + stats (supabase_writer), atomic publication RPCs,
fetcher chunking/resume budgets. Anti-patterns that must NOT come along:
per-ticker tables, text timestamps, anon-readable grants, unthinned raw
retention.

## Build order

1. `core/` first (config, errors, logging, db) — everything depends on it
2. `ingest/` + `jobs/` (the data machine)
3. `api/` (security model before endpoints)
