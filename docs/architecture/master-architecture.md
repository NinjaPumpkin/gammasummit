# GammaSummit — Master Architecture (floor plan)

The umbrella blueprint. Every other doc = a room in this building. If two docs
disagree, THIS document and the ADRs win. Status: architecture phase — no
production changes.

## 1. Vision + scope

Options-flow intelligence platform: live gamma/flow dashboards + AI analysis,
all Unusual Whales tickers, top-200 live. UI follows skylit.ai layout patterns
(`docs/architecture/design-reference-skylit.md`). Product conventions owner-locked
(`frontend/README.md`).

**v1:** ingest + tiering pipeline, API, dashboard (heatmap matrix, flow feed,
AI Analyst card), auth (passkeys + magic fallback), alert-less read-only.
**v2:** chart workspace, AI canvas, alert rules + push, modes (Cloutseeker/
SpotGamma/FATTE), scanner/compass, saved shared layouts.
**Never v1:** community/prop-trading features, multi-region, broker execution.

## 2. System context

```
                 ┌──────────────┐   ┌──────────────┐
   UW / PHX / IBKR data ──────►│ ingest daemon  │   │  job workers  │
                 └──────┬───────┘   └──────┬───────┘
                        │ T0 writes         │ rollups/retention/export
                        ▼                   ▼
                 ┌───────────────────────────────────┐
                 │  Postgres (Supabase, slim plan)    │  T0 24–48h raw
                 │  pg_partman · pg_cron · pgmq ·    │  T1 30d buckets
                 │  pgaudit · index_advisor · hypopg  │  T2 90d–1yr rollups
                 └───────────────┬───────────────────┘
                                 │ postgres FDW / export
                 ┌───────────────▼───────────────────┐
                 │  T3 cold: Parquet                  │
                 │  external disk (primary)           │
                 │  + B2/R2 copy (3-2-1)              │
                 │  queried via DuckDB (+httpfs/cache)│
                 └───────────────┬───────────────────┘
                                 │
   Users ──► Vercel frontend ──► API (VPS, docker) ──┘
             (preview + prod)     │ service role only
                                  ▼
                            Supabase Postgres
```

## 3. Containers

| Container | Tech | Runs | Responsibility |
|---|---|---|---|
| ingest daemon | Python 3.10, systemd | VPS | fetch UW/PHX/IBKR → T0 writes, triggers downsampler |
| job workers | Python 3.10, systemd timers / pgmq | VPS | downsampler, rollups, retention/export, lazy backfill |
| API | FastAPI + uvicorn, docker | VPS | sole query surface for frontend; authn/authz/rate limits |
| Postgres | Supabase slim | managed | T0/T1/T2, partitioned, deny-default grants |
| cold store | Parquet | external disk + B2/R2 | full-fidelity history |
| analytics | DuckDB (+extensions) | researcher machines | backtests over T3 + federation to hot |
| frontend | Vite + React SPA | Vercel | dashboard; API-only data access |
| observability | Uptime Kuma + GlitchTip + journald | VPS | freshness alerts, errors, logs |
| workbench | duck-ui (MIT, in-tab) | browser | ad-hoc T3 research (never a server surface) |

## 4. Data tiers + jobs

Spec: `docs/ops/data-tiering.md`. T0 raw 24–48h → T1 5-min buckets 30d → T2
hourly+EOD rollups 90d–1yr → T3 Parquet indefinite.

Jobs (all idempotent, retryable, export-first): `downsampler` (5-min cadence),
`rollups` (hourly + EOD), `retention` (daily, manifest-verified),
`export` (daily, 3-2-1 sync), `lazy_backfill` (on-demand via pgmq).

## 5. Logical schema (entities — physical DDL in `db/migrations/`)

| Entity | Grain | Partition | Tier |
|---|---|---|---|
| `gamma_snapshot` | ticker,strike,expiry,ts | ticker list + ts range | T0 |
| `gamma_bucket_5m` | ticker,strike,expiry,bucket | ticker + date | T1 |
| `expiry_rollup_hourly` | ticker,expiry,hour | ticker + date | T2 |
| `strike_eod` | ticker,strike,expiry,day | ticker + date | T2 |
| `spot_tick` | ticker,ts | date | T0→T2 downsample |
| `flow_print` | contract,ts | date | T0→T2 |
| `darkpool_print` | ticker,ts | date | T2 |
| `king_node_history` | node,ts | date | T2 (ported) |
| `ticker_universe` | ticker | — | catalog |
| `top200_membership` | ticker,month | — | policy |
| `export_manifest` | file,ts | — | ops |
| `alert_rule` / `alert_event` | user / rule | — | product |
| `audit_log` | actor,ts | date | security (pgaudit) |

Types locked: `timestamptz`, `date`, `bigint`/`double precision`. Indexes:
`(ticker, timestamp DESC)` B-tree + BRIN on ts for append tables.

## 6. API surface (read-mostly, OpenAPI-first)

| Endpoint group | Purpose | Cache |
|---|---|---|
| `/tickers`, `/universe` | catalog + top-200 | 1h |
| `/grid` (strike×expiry matrix) | dashboard heatmap | 30s SWR |
| `/series` (DDOI, GEX profile) | charts | 30s SWR |
| `/flow` (feed, scanner) | flow module | 10s SWR |
| `/ai/analyze` | AI Analyst (SSE stream) | no cache |
| `/freshness` | health = data freshness | no cache |
| `/jobs/backfill` (auth'd trigger) | lazy long-tail load | n/a |
| `/alerts` (v2) | rules + events | n/a |

## 7. Security zones

Edge (Cloudflare) → frontend (Vercel) → API (authn: passkeys primary + magic
fallback; authz: per-resource; rate limits) → DB (service role only, deny-
default grants, RLS + API double-check, pgaudit). Full spec:
`docs/ops/security.md` + `docs/ops/security-future.md`. CI gates: grants regression
test, gitleaks, Semgrep, Trivy, supabase-security linter (⚠ Oct 30, 2026 Data
API grants change), `get_advisors` = zero ERROR lints.

## 8. Environments + deployment

| Env | Frontend | Data | Auth |
|---|---|---|---|
| dev | localhost | mock/local | test account |
| preview | `*.preview.gammasummit.top` | mock/staging | test accounts |
| staging | staging subdomain | staging API + staging DB | test accounts |
| production | `gammasummit.top` | live | passkeys/magic |

VPS: `/opt/gammasummit/releases/<ts>` + `current` symlink, env at
`/etc/gammasummit/env`, systemd units per role, docker for API. Migrations
precede writer restart; reader cutovers follow validated writers.

## 9. Module dependency rules

`core` ← everything. `ingest` / `jobs` / `api` never import each other except
via `core` interfaces. Frontend never imports DB logic. DuckDB scripts live in
`db/queries/` and are never called from the request path.

## 10. Non-functional requirements

| NFR | Target |
|---|---|
| Freshness (market hours) | T0 lag < 60s; alert at 15 min stale |
| Dashboard load | shell < 2s; widget render < 100ms |
| API p95 | < 200ms for cached aggregates |
| Hot DB size | ≤ 10 GB steady state |
| Retention safety | never delete un-exported data (manifest-verified) |
| Uptime | best-effort VPS + managed DB; freshness alerts, not SLA |

## 11. Build phases

1. **Foundations**: `backend/core` + `db/migrations/0001` (schema, grants,
   partitioning) + pgtap tests
2. **Data machine**: ingest + jobs (downsampler, rollups, retention/export)
3. **API**: security model first, then endpoints (OpenAPI)
4. **Frontend**: shell + heatmap matrix + flow feed + AI card (Skylit patterns)
5. **Hardening + cutover**: CI gates, load check, dual-write, reconcile,
   endpoint flip (migration doc)

Each phase = ADR + tests + `get_advisors` clean. Slow, meticulous, no redo.

## 12. Document map

| Doc | Room |
|---|---|
| `ARCHITECTURE.md` | runtime data path (short form) |
| `docs/ops/data-tiering.md` | tier + job rules |
| `docs/ops/migration-from-signalforge.md` | reuse map + cutover |
| `docs/ops/security.md` / `security-future.md` | security now / roadmap |
| `docs/ops/operations.md` | runbooks |
| `docs/architecture/frontend-design.md` | UX rules (⚠ mock visuals rejected — rewrite from design-reference) |
| `docs/architecture/design-reference-skylit.md` | layout patterns (UI source of truth) |
| `docs/build/frontend-future.md` | UI roadmap |
| `docs/ops/risks-and-toolkit.md` | pitfalls + tool/extension audits |
| `docs/decisions/NNNN_*` | ADRs (binding) |
