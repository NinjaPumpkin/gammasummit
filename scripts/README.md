# scripts/

One-off ops scripts: backfills, exports, repairs, migrations helpers.

## Rules

- Every script: `--dry-run` default for anything destructive, explicit
  `--execute` to apply. Export-first, non-destructive always.
- Scripts are throwaway-quality code with production-quality safety: arg
  parsing, confirmation, logging, no hardcoded secrets.
- Anything that runs more than twice becomes a `backend/jobs/` module instead.
- Name: `verb_noun.py` (`export_parquet.py`, `backfill_ticker.py`).
