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

## Backend extraction readiness (assessed 2026-09-30)

Verdict: **ready to EXTRACT logic, not to copy code.** SignalForge `v3/` is a
coupled monolith (22 MB) — only `p2_gamma/` (ingest + data layer), parts of
`p2_market/`, and `lib/` scorers (greek_scorer, gamma_vanna_scorer, flow_triage,
iv_percentile) are product scope. `p1_discord`, `p3_execution`, `p4_telegram`,
`p5_brain`, `p6_analysts` are NOT gammasummit v1 (stay in SignalForge).
Extraction happens in Ultraphase P2 into `backend/ingest|jobs|core`, per the
reuse map above. Port blockers to handle in P1: 30 KB `config.py` env coupling,
`.env` handling, STDB legacy refs, 3.10 syntax floor.

## X10 Pro external disk — cold storage layout (created 2026-09-30)

Root: `/Volumes/X10 Pro/`. GammaSummit uses ONLY:

```
gammasummit/                       ← new canonical cold-storage root
├── t3/gamma/                      # raw full-fidelity snapshots (post-48h export)
│   └── ticker=<T>/date=<YYYY-MM-DD>/*.parquet   (hive-partitioned — DuckDB pruning)
├── t3/flow/                       # flow/darkpool cold archives
├── t3/rollups/                    # T2 archives aged out of Postgres (>90d–1yr)
├── t3/manifests/                  # export manifests (counts, min/max ts, checksums)
├── backups/                       # DB dumps, encrypted config backups
├── research/                      # .duckdb files, backtest outputs
└── legacy/                        # SignalForge consolidation after cutover
```

Pre-existing X10 folders (read-only inputs / frozen until cutover — do NOT
delete or restructure):

| Folder | Size | Role |
|---|---|---|
| `leandata/` | 152 GB | seed archive: `parquet/` (options_eod, options_minute, stock_1min, stock_daily, index_*, cboe_close) + `supabase_archive/` (phx csv.gz + vexatrader SQL dump) → migrates INTO `gammasummit/t3/` |
| `SignalForge Archive/` | 5.5 GB | pre-cleanup DBs, gamma_copilot copies, phx_flow_alerts |
| `SignalForge-backups/` | 1.2 GB | snapshot-2026-06-17 |
| `SignalForge-Migration/` | 162 GB | full SignalForge data copy |
| `GITPROJECTS/SignalForge*` | — | repo copies (backup) |
