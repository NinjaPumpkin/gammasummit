# Migration from SignalForge

SignalForge (`~/Desktop/Github Projects/SignalForge`) is reference + current
production. It keeps serving until GammaSummit is proven and cut over. No
flag-day switch — dual-run, measure, then flip.

## Reuse map (logic re-derived, not copied)

| SignalForge artifact | Reuse | How |
|---|---|---|
| `lib/supabase_writer.py` (batch upsert + retry + stats) | ✅ pattern | re-implement in `backend/core/db.py`; keep conflict-key upsert semantics |
| atomic publication RPCs | ✅ pattern | port SQL into `db/migrations/`, transaction boundaries preserved |
| `v3/p2_gamma/gamma_ingest.py` writer flow | ✅ logic | re-derive in `backend/ingest/`; writer contract (what lands when) documented in `db/schema/` |
| fetcher chunking / history budgets (leandata workers) | ✅ logic | resume-budget pattern into `backend/ingest/` |
| `--phx-datasets` scoping | ✅ mechanism | becomes top-200 policy + lazy tail (`docs/data-tiering.md`) |
| `deploy/gammasummit-ingest.service` | ✅ shape | redeployed units in `deploy/systemd/`, new env + paths |
| parity spec `docs/TWEATERMINAL_PARITY_IMPLEMENTATION_GUIDE.md` | ✅ reference | frontend widget parity target |
| per-ticker `gamma_data_<t>` tables (1,232) | ❌ never | single partitioned tables (`db/README.md` rule 5) |
| `timestamp text` / `expiry_date text` columns | ❌ never | `timestamptz` / `date` |
| anon-readable grants / 1,257 tables no RLS | ❌ never | deny-by-default, API-only read surface |
| unthinned raw retention (3–6 GB/day) | ❌ never | T0 = 24–48h (`docs/data-tiering.md`) |
| 609-ticker always-live ingest | ❌ never | top-200 live + lazy tail |

## Measured facts carried over (verified 2026-09-30)

- Hot DB was 38 GB; snapshot tables ≈ 80% of it.
- Write rate: SPX 1.0–1.5M rows/day, universe-wide est. 4–8M rows/day.
- 0928 gamma_prune ran (snapshot tables cut to ≥ 2026-09-26); 0928 export
  artifacts unaccounted for — resolve before cutover (open item).
- Weekend ingest spikes (09-26/27): determine backfill-vs-continuous before
  the downsampler design freezes.

## Cutover strategy

1. Build GammaSummit alongside; SignalForge stays live.
2. Dual-write shadow: new ingest writes to new schema, no readers.
3. Compare outputs (spot checks + rollup reconciliation) for ≥ 2 weeks.
4. Move frontend readers endpoint-by-endpoint to new API.
5. SignalForge ingest → read-only → archive. Keep until 30d clean.

## Python floor

VPS = Python 3.10.12. All GammaSummit code 3.10-compatible until the VPS
changes (recorded in `docs/decisions/`).
