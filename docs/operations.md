# Operations

Runbook skeleton. Fills in as services land; every incident adds a section.

## Freshness = health

Deep health check = data freshness, not process liveness (ch.12, ch.15).
"Last updated" shown in the UI is backed by the same metric that alerts.

- Alert when newest T0 timestamp > 15 min stale during market hours.
- Alert when downsampler lag (T0 max ts − T1 max ts) > 30 min.
- Alert when retention/export job misses its daily window.

## Retention & export safety (export-first, non-destructive)

1. Retention job exports candidate rows to Parquet.
2. Write manifest (row counts, min/max ts, checksum) to cold storage.
3. **Verify** manifest (re-read sample, counts match) — only then delete.
4. Deletion failure = fine (retries). Export failure = abort, no delete. Ever.
5. 3-2-1: external disk + B2/R2 + one more copy (second disk or periodic
   snapshot).

## Backups

- Hot tier: Supabase managed backups (why we keep Supabase for hot).
- Cold tier: Parquet is the backup format — immutable files + manifests.
- Config/deploy: git is the backup; env files backed up encrypted separately.

## VPS conventions

- Deploy: release dir + `current` symlink flip + service restart. Rollback =
  flip back. No in-place edits on live code.
- Logs: journald per service (`journalctl -u gammasummit-ingest`).
- nginx: restart ≠ reload (known VPS pitfall).

## Incident playbooks (to fill in)

- Ingest gap (missing snapshots): …
- UW API failure / rate limit: circuit breaker state, backfill procedure: …
- Supabase saturation: kill runaway queries, freeze lazy backfills: …
- Corrupt Parquet export: manifest mismatch procedure: …

## Secret rotation

Quarterly + on any exposure suspicion: UW/API keys → `/etc/gammasummit/env`
update + service restart + verify freshness metric recovers.
