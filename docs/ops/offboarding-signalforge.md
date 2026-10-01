# Offboarding SignalForge → GammaSummit

Owner directive 2026-09-30: plan the full offboard — repo, VPS workloads, data,
files. SignalForge files get removed (archived) only after gammasummit is
complete and wired up. Planning mode: nothing executes until P5 gates open.

## Scope

| Surface | From | To | Removal step |
|---|---|---|---|
| Code repo | `SignalForge/` (live prod) | `gammasummit/` (fresh code) | superseded modules → X10 `gammasummit/legacy/`, repo tagged `signalforge-final` then archived (git history kept forever) |
| VPS workloads | systemd `gammasummit-ingest`, `/opt/gammasummit` release symlinks, `/etc/gammasummit/env`, duckle timers, cron fleet (uw-cache-refresh, staleness alarm, outcome tracker, filter, weekly report) | same VPS, new units `gammasummit-*` + release deploy, jobs move to `backend/jobs` | stop old units only after 2w clean diffs; delete old releases after 30d |
| Data | per-ticker `gamma_data_<t>/expiry_summaries_<t>` (1,232 tables), `gamma_data_v2` etc. | partitioned `db/migrations/0001` schema, tiers T0-T3 | old tables dropped only after export-first manifests verified (T3) + 2w reconciliation |
| Frontend | dashboard-next (Vercel) | SPA on Vercel (branch previews per ADR 0002) | old project → Vercel archive after DNS flip |
| Domain/DNS | `gammasummit.top` | same | flip only at API cutover |
| X10 storage | `leandata/`, `SignalForge Archive/-backups/-Migration` | `gammasummit/t3/` + `legacy/` | consolidate after cutover; never delete raw archives |

## Hard gates (any failure = stop)

1. Calc-parity gate signed (P0) — before anything ships.
2. **Dual-write ≥ 2 weeks** with daily diff reports (DuckDB `postgres`
   federation, `diff_pipelines`-style): zero material diffs for 10 consecutive
   trading days.
3. Rollback rehearsed: old ingest resume + DNS revert script, timed.
4. Export-first + manifest-verified before ANY table/file drop.
5. Removal = archive move to X10 `legacy/`, never `rm` (non-destructive rule).

## Phase checklist (P5 detail)

- **P5a data migration**: backfill partitioned schema from old tables; verify
  counts/min-max-ts per entity; retention jobs armed but export-first.
- **P5b API cutover**: endpoints flip one-by-endpoint (heatmap reads first,
  then flow, then analytics); old API stays read-only standby.
- **P5c frontend cutover**: SPA + preview sign-off → production domain.
- **P5d VPS swap**: new systemd units start; old units stop after 2w diffs;
  duckle/cron jobs repointed or retired (single-scheduler rule: never both).
- **P5e SignalForge offboard**: tag repo `signalforge-final`; copy superseded
  code to X10 `gammasummit/legacy/signalforge/`; delete working copies from
  `Github Projects/` (repo archived, not git-history-destroyed); dashboard-next
  → Vercel archive.
- **P5f dependency hardening** (from 2026-09-30 dependency audit):
  - leandata T&C check (post-termination retention of extracted archive) — one
    read, record verdict in `docs/decisions/`
  - B2/R2 3-2-1 copy of `leandata/` + `uw-archive/` (today: single-disk copies
    only — the real "lost subscription" exposure)
  - **fix `com.signalforge.uwarchive`** (launchd agent exists but never ran —
    empty log, missing destination; UW heavy data currently VPS-only)

## Data dependencies (leandata survivability — verified 2026-09-30)

Live product = UW-only (lifetime): heatmap gex/vanna, flow, Tempest IV inputs.
Realized vol/prices = UW candles (`candles_1m/daily` heavy datasets) +
`spot_ticks` accumulation. Leandata = historical depth only (kept copy on X10
survives lapse; ongoing deep history continues from UW). Outcomes marking:
leandata minute bars → UW candles swap.

## Expected efficiency gains (measured baseline → target)

Baseline (2026-09-30): 38 GB Supabase, +3–6 GB/day raw growth, 1,232 per-ticker
tables, 2,207 unused indexes, text `timestamp`/`expiry_date`, 4–8M rows/day
ingest.

| Metric | Today | After | Why |
|---|---|---|---|
| Hot DB storage | 38 GB, growing 3–6 GB/day | **5–10 GB, flat** (O(30d), not O(history)) | raw 24–48h only; 5-min buckets 30d; rollups 90d–1yr; Parquet T3 |
| Storage growth cost curve | bill grows forever with history | **flattens** — no overage creep | tiers age out to X10/B2 |
| Write load | 1,232 tables + 2,207 unused indexes + text cols | partitioned + deny-default + typed `timestamptz`/`date` | index diet + typed columns: **~30–60% less write amplification** |
| Whole-board query (heatmap read) | slow scans across per-ticker tables | **API p95 < 200 ms** (NFR) | partition pruning + BRIN + precomputed rollups + keyset paging |
| 90d/1y history views | raw scans | **10–100× faster** (analytical reads) | DuckDB columnar over Parquet + materialized T2 rollups |
| Freshness visibility | row counts (missed a 3-month freeze) | payload-ts freshness + verdict alarms | ops lessons baked in |
| Backtest compute | Supabase compute | DuckDB on X10 = **zero DB cost** | local columnar + postgres federation for live joins |
| Frontend updates | poll intervals | **SSE deltas < 2 s** | push channel + keyset |
| Security surface | 1,255 RLS-off tables, anon readable | deny-by-default + CI regression + passkeys | Oct 30 grants change survives cleanly |

Ingest headroom: 4–8M rows/day comfortably fits T0 with batched upserts
(existing pattern) once write amplification is gone.

## Rollback

Each flip reversible for 30 days: old tables kept until manifests verify + 2w
diffs; DNS revert script; old systemd unit definition kept in git. Archive
moves (P5e) happen only after that window closes.
