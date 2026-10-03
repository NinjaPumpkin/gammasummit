# Operations

Runbook skeleton. Fills in as services land; every incident adds a section.

## Freshness = health

Deep health check = data freshness, not process liveness (ch.12, ch.15).
"Last updated" shown in the UI is backed by the same metric that alerts.
The metric is payload-timestamp based (upstream tape time, never `now()`
bookkeeping) — the SignalForge lesson: a vendor freeze looked alive for days.
Code: `backend/jobs/freshness.py` (report + verdicts + Kuma beacon in one run).

Alerts (thresholds configurable via `GAMMASUMMIT_FRESHNESS_*`, defaults below):

- Alert when newest T0 timestamp > 15 min stale during market hours
  (`t0_freshness`; gated on the US regular session 09:30–16:00 ET — an idle
  pipeline outside market hours is normal, not an alarm).
- Alert when downsampler lag (T0 max ts − T1 max bucket) > 30 min
  (`downsampler_lag`).
- Alert when retention/export job misses its daily window (`retention_jobs`:
  no successful scheduled `retention_t0` + `export_cold` run in the audit_log
  within 48 h — THE scheduler is the only writer of those rows, ADR 0007).

Run it:

    python -m backend.jobs.freshness                  # report JSON to stdout
    python -m backend.jobs.freshness --report f.json  # + save
    python -m backend.jobs.freshness --push           # + beacon Uptime Kuma
    python -m backend.jobs.freshness --as-of 2026-10-06T15:00:00Z   # staleness test

Exit code 0 = all checks ok, 1 = any check alert (CI-friendly). `--as-of`
shifts threshold evaluation only — it never touches data (same verification
hook pattern as `jobs/export_cold.py`).

## Alarms (Uptime Kuma)

Self-hosted Uptime Kuma (OSS, Docker) holds one **push monitor per freshness
check** plus an `overall` monitor; `freshness.py --push` beacons each verdict
(up/down + message) to its monitor URL. A silent job is caught too: a missed
beacon ages out the push heartbeat.

| monitor | check | env key (push URL — SECRET) |
|---|---|---|
| `gs-freshness-overall` | overall verdict | `GAMMASUMMIT_KUMA_PUSH_OVERALL` |
| `gs-t0-freshness` | `t0_freshness` | `GAMMASUMMIT_KUMA_PUSH_T0_FRESHNESS` |
| `gs-downsampler-lag` | `downsampler_lag` | `GAMMASUMMIT_KUMA_PUSH_DOWNSAMPLER_LAG` |
| `gs-retention-jobs` | `retention_jobs` | `GAMMASUMMIT_KUMA_PUSH_RETENTION_JOBS` |

Setup (idempotent; admin password is generated locally into `.env` — never
printed, never committed):

    docker run -d --name gs-kuma -p 127.0.0.1:3001:3001 \
      -v gs-kuma-data:/app/data louislam/uptime-kuma:1
    python3 scripts/e24_kuma_admin.py wire --webhook-url <ops webhook URL>
    python3 scripts/e24_kuma_admin.py test   # verify the notification channel

Wiring notes (learned the hard way, E2.4):

- Kuma-in-Docker calling back to a host webhook must use
  `http://host.docker.internal:<port>/` — `127.0.0.1` inside the container is
  the container itself. The receiving sink must bind `0.0.0.0` for that path.
- Notification channel: webhook `gs-freshness-alarms` (production: point it at
  the real ops endpoint — telegram/email bridge; the local `scripts/e24_kuma_sink.py`
  is the proof harness that logs every alarm/recovery POST to
  `data/e24_kuma/alarms.jsonl`).
- Push tokens are secrets: they land in `.env` (gitignored) and
  `data/e24_kuma/push_urls.json`, never in git/chat.
- Beacons ride the freshness run cadence. Prod cadence = every 5 min
  (systemd timer `gammasummit-freshness.timer`), so set monitor
  heartbeatInterval=300, maxretries=3. The shadow sandbox beacons from the
  daily accrual run (heartbeatInterval=86400, maxretries=1).

### Deliberate staleness test (alarm drill — run after any rewiring)

1. Baseline: `python -m backend.jobs.freshness --push` (all monitors Up).
2. Fire: `python -m backend.jobs.freshness --push --as-of <next market-open
   instant>` — the clock hook makes the metric evaluate as if the market were
   open with no fresh payloads (and the daily job window elapsed): `alert`
   beacons flip the monitors Down and the webhook channel FIRES
   (`[gs-t0-freshness] [🔴 Down] …` lands in the sink log).
3. Clear: `python -m backend.jobs.freshness --push` (true state) — recovery
   webhooks land (`[✅ Up] …`). The drill is only complete when the recovery
   POST arrives.
4. Archive `data/e24_kuma/` (freshness reports + heartbeats + sink log) with
   the incident.

Never "clear" an alarm by pushing Up over a genuinely stale pipeline — fix the
data first (capture/backfill + rerun the tier jobs), then the Up beacon is
truthful.

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
