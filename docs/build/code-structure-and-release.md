# Code structure & release engineering

Scaffolding map: what code lives where, what each module does, and how
versioning, updates, and rollbacks work. Executes on top of the scaffold
already in the repo + ADR 0003. Build exactly this tree.

## 1. Target tree (annotated)

```
gammasummit/
├── README.md · AGENTS.md (copy of docs/build/README.md at kickoff) · CHANGELOG.md
├── .github/workflows/
│   ├── ci.yml              lint + type-check + tests + migration-lint + contract-sync + gitleaks
│   ├── deploy-web.yml      merge→Vercel (auto previews per ADR 0002)
│   └── deploy-api.yml      merge→SSH VPS release flip + smoke + auto-rollback
├── backend/
│   ├── api/
│   │   ├── main.py         app factory; middleware: auth, rate-limit, CORS, request-id
│   │   ├── routers/        heatmap.py · flow.py · charts.py · vol.py · analyst.py
│   │   │                   auth.py · admin.py · nexus.py   (thin: validate → core → respond)
│   │   ├── schemas/        pydantic response/request models = THE API contract
│   │   ├── sse.py          delta stream channel (heatmap/flow updates)
│   │   └── deps.py         DB pool, auth deps, settings
│   ├── core/               PURE logic — no DB, no network, no env. Fully unit-testable.
│   │   ├── exposure.py     ★ the clean-room calc (GEX/VEX, node values) — P0 gate artifact
│   │   ├── nodes.py        node classification: king / wall / gatekeeper / significant / normal
│   │   ├── vol.py          SVX, expected-move cones, sigma, skew, tilt, VRP (Tempest)
│   │   ├── flow_score.py   flow scoring + momentum z-scores + pattern labels
│   │   ├── outcomes.py     win-rate labeling (30m/1h/2h/d), threshold fitting
│   │   └── contracts.py    typed decision models (Jev q/a/confidence) — AI layer glue
│   ├── ingest/             UW → T0 writers (logic re-derived from p2_gamma, NOT copied)
│   │   ├── uw_client.py    UW fetch + backoff + payload-ts freshness checks
│   │   ├── chain_writer.py gamma/vanna snapshot writer (batched upserts, idempotent)
│   │   ├── flow_writer.py  flow prints + alerts · spot_writer.py
│   │   └── fleet.py        top-200 live vs tail lazy/EOD scheduler
│   ├── jobs/               scheduled work (single-scheduler rule: backend timers XOR pg_cron — ADR 0007)
│   │   ├── rollups.py      T0→T1 5-min buckets (downsampler) + T1→T2 hourly/EOD rollups
│   │   ├── export_cold.py  T1/T2→T3 Parquet→X10 + rclone→R2 + manifest-verified drop
│   │   ├── retention.py    T0 export-first retention (24–48h) · backfill.py (pgmq worker)
│   │   ├── scheduler.py    THE single scheduler (backend timers, advisory-locked, audit-logged)
│   │   ├── freshness.py    freshness metric per table/tier + Uptime Kuma push beacon (E2.4)
│   │   └── outcomes.py     outcome marking + threshold recalibration
│   └── tests/              unit/ (core), contract/ (schema sync), integration/ (API+DB)
├── db/
│   ├── migrations/NNNN_snake_name.sql   forward-only, expand/contract (see §4)
│   ├── schema/             declarative reference (never applied by hand)
│   └── queries/            saved analytical SQL (DuckDB + Postgres variants)
├── frontend/
│   ├── src/
│   │   ├── app/            router, providers, layout (Parity Shell — checklist v1)
│   │   ├── features/       heatmap/ · flow/ · charts/ · vol/ · analyst/ · nexus/
│   │   ├── components/     shared primitives (NodeBadge, VelocityChip, ExpiryRail…)
│   │   └── lib/            api/ (typed fetch client) · contract/ (zod = mirror of pydantic)
│   └── mockups/            approved reference visuals (dashboard-v3.html)
├── deploy/
│   ├── systemd/            gammasummit-api.service · gammasummit-jobs.service
│   ├── vps/                deploy.sh (release symlink) · rollback.sh · smoke.sh
│   └── docker/             compose for local dev parity (api + postgres + jobs)
├── scripts/                RE capture + research + ops utilities (--dry-run default)
└── docs/                   as structured
```

## 2. Dependency law (what may import what)

```
frontend ──HTTP──► api ──► core ◄── ingest
                     │       ▲         │
                     └──► db ◄─────────┘
              jobs ──► core + db + storage (X10/R2)
```

- `core/` imports nothing internal. Everything else may import `core`.
- Routers never contain business logic (validate → core → serialize).
- Frontend NEVER touches DB or env secrets — API only (hard rule).
- AI providers (Jev/mimo/LiquidAI) sit behind `core/contracts.py` as optional
  adapters — never hard-wired in routers (GitHub-open-code portability).

## 3. Config & conventions

- Settings via pydantic-settings, env prefix `GAMMASUMMIT_`; `.env` gitignored,
  `.env.example` documents every key.
- Structured JSON logs with request-id + payload timestamps (freshness trust).
- Health: `/healthz` (process) + `/readyz` (DB + UW + last-payload-age).
- Naming: modules snake_case, components PascalCase, migrations `NNNN_snake.sql`.

## 4. Versioning

| Layer | Scheme | Rule |
|---|---|---|
| App | SemVer tags `v0.x` pre-cutover, `v1.0.0` at cutover | CHANGELOG.md (Keep a Changelog), every release |
| DB schema | `NNNN_` sequential | **expand/contract only** — never alter/drop in place while serving; contract phase only after cutover + verified export |
| API | `/v1` URL prefix | breaking change = `/v2` + deprecation window; response contract = pydantic↔zod pair, CI-checked |
| Rollup data | `schema_version` column on T2 tables | backfill invalidates only its own version |
| Frontend | Vercel deployment IDs | preview → promote → instant rollback |

## 5. Release flow (updates)

1. PR → `ci.yml` must be green (lint, tests, migration-lint: no destructive DDL,
   deny-default grants check, contract-sync, gitleaks).
2. Merge → `deploy-web.yml` builds Vercel preview at `pr-N.preview.gammasummit.top`
   (passkey test account — solves the old magic-link preview pain).
3. Promote: API deploy = Actions → SSH VPS → build into `/opt/gammasummit/releases/<sha>/`
   → **atomic symlink flip** `current` → run `smoke.sh` (healthz + 3 key endpoints +
   one real heatmap read) → **auto-rollback on smoke failure**.
4. Migrations run BEFORE app flip (expand first), gated on CI migration-lint.
5. Keep last 5 releases on disk for instant rollback.

## 6. Rollback

| Failure | Action | Time |
|---|---|---|
| Bad API build | `rollback.sh` flips `current` symlink to previous release | seconds |
| Bad frontend | Vercel rollback to previous deployment | seconds |
| Bad migration | expand-only design = old app runs against new schema; fix forward | minutes |
| Contract migration regretted | contract phase never ran → nothing destructive happened | n/a |
| Bad data landed | export-first manifests + R2 = restore path; raw T0 24–48h churn is reproducible from UW | hours |
| Feature misbehaves (AI analyst, gates) | env/feature-flag kill switch, no deploy needed | seconds |

Hard rule: destructive data operations never ride app releases. They run as
their own `--dry-run`-by-default jobs with manifests (operations.md).

## 7. Feature flags

Env-driven booleans (`GAMMASUMMIT_FF_*`) read at startup: `FF_ANALYST`,
`FF_EXEC_GATE`, `FF_NEXUS`. Kill switches survive rollbacks because they live
in config, not code paths.
