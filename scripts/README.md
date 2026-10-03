# scripts/

One-off ops scripts: backfills, exports, repairs, migrations helpers.

## Rules

- Every script: `--dry-run` default for anything destructive, explicit
  `--execute` to apply. Export-first, non-destructive always.
- Scripts are throwaway-quality code with production-quality safety: arg
  parsing, confirmation, logging, no hardcoded secrets.
- Anything that runs more than twice becomes a `backend/jobs/` module instead.
- Name: `verb_noun.py` (`export_parquet.py`, `backfill_ticker.py`).
- `read_leandata.py` — READ-ONLY loader for `/Volumes/X10 Pro/leandata/`
  (never writes to source). Layout/schemas/coverage:
  `../docs/data/leandata-inventory.md`.
- `leandata_extract.py` — throttled leandata extraction driver (D3 resume).
  Wraps the SignalForge extractor suite read-only (importlib) with the
  owner/PM throttle (1 in-flight ≤50% of the vendor's 3-concurrency cap,
  1 s+jitter pacing, cooldown+abort on rate signals, 20k daily cap recorded
  in `../docs/data/leandata-pull-manifest.json`). Writes the LOCAL staging
  archive `../data/leandata-parquet/`. Resumable/idempotent. Promote to
  `backend/jobs/` when the backend phase starts (runs daily).
- `leandata_x10_merge.py` — staging → X10 merge (row-dedupe per file, state
  ledger union) + re-derivation of `data/missing_<ds>.txt` gap lists from the
  live X10 tree. `--dry-run` default, `--execute` to apply, `--derive-only`
  read-only gap lists.
- `leandata_daemon_tick.sh` — cron tick for `leandata-extract-daemon`
  (every 4 h): merge-if-healthy + relaunch extractor if idle.
