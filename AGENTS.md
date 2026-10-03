# Builder guide — read this first

Routing document for whoever (or whatever) builds `gammasummit`. Planning is
complete; this file says what to build, in what order, from which specs.

> If your harness supports an `AGENTS.md`/`CLAUDE.md` entry file, copy this
> content there at build kickoff.

## Mission

TWEATerminal/Skylit-class options-flow intelligence platform (heatmaps, flow,
charts, volatility, AI analyst), **fresh code** ported from the SignalForge
reference project, data from the Unusual Whales (UW) lifetime subscription,
1:1 UI parity with skylit.ai layout patterns (our branding, their IP not
copied).

## Current state (2026-09-30)

- 2026-10-01 (owner ruling): build opens NOW, in parallel with P0 calc-parity
  work. P0 gate NOT signed yet (oracle bound 68.6% king exact for the
  weight-model class — `e05b-king-parity.md` §5); it stays the cutover
  milestone with bars honest. Priorities: data collection (Skylit + UW +
  leandata), per-cell calc RE until very close, build-out meanwhile.
- SignalForge = live production + reference. **Never write to SignalForge
  prod** (no table drops, no prod inserts, no VPS service restarts).
- RE campaign in flight: `RE-CAMPAIGN.md` + `../scripts/skylit_re_capture.py`.

## Reading order

1. `../architecture/master-architecture.md` — the floor plan (canonical)
2. `ultraplan.md` — phases P0–P5, workstreams A–F, gates
3. `../decisions/0003_build_stack.md` — stack (FastAPI/asyncpg, Vite+React,
   TanStack, TradingView charts, SQL migrations, Zod↔pydantic one contract)
4. `../architecture/skylit-product-inventory.md` — product modules
5. Specs for your workstream (table)

## Workstream map

| WS | Scope | Authoritative specs | Acceptance |
|---|---|---|---|
| A | Heatmap UI parity | `parity-checklist-skylit.md`, `../architecture/design-reference-skylit.md`, `../../frontend/mockups/dashboard-v3.html` | 34/34 checklist items |
| B | Data machine (ingest, tiers, rollups) | `../ops/data-tiering.md`, `../ops/migration-from-signalforge.md` | raw 24–48h, T1 5-min/30d, freshness alarms |
| C | API (FastAPI, keyset, SSE) | `../architecture/master-architecture.md` §API, `../decisions/0003_build_stack.md` | p95 < 200 ms; frontend never touches DB |
| D | Security & ops | `../ops/security.md`, `../ops/operations.md`, `../ops/backup-topology.md` | deny-default grants, CI regression, export-first |
| E | Port + cutover | `../ops/offboarding-signalforge.md`, `../ops/migration-from-signalforge.md` | 10 zero-diff trading days, rollback rehearsed |
| F | Frontend SPA + previews | `../architecture/frontend-design.md`, `frontend-future.md`, ADR 0002 | 1:1 parity sign-off |

Cross-cutting: AI stack `../architecture/ai-stack.md` +
`../architecture/talon-ai-framework.md`; linkage/DNS/GitHub/R2
`../architecture/topology-linkage.md`; RE knowledge `skylit-value-model.md`
+ `../ops/signalforge-knowledge-transfer.md`. **Code tree, module duties,
versioning & rollback: `code-structure-and-release.md` (this folder).**

## P0 gate (before any product build)

Clean-room calc parity: fresh `backend/core/exposure.py` (zero SignalForge
imports), king exact ≥90% over ≥20 session-days vs Skylit nodes (≤10% error).
Inputs: RE captures on X10 `gammasummit/t3/re/raw/` + UW `gamma_data_v2`.
Known math: star = argmax |value|; within-expiry `net_gex = call_gex − put_gex`;
missing layer = cross-expiry dynamic weighting (fit target = 1s range frames).

## Hard rules (violating = wrong)

- **Clean-room calcs**: never copy SignalForge calculation code; re-derive.
  RE knowledge from experiments + Skylit API is fine; copied code is not.
- **`--dry-run` default** for anything destructive; `--execute` to apply;
  export-first + manifest-verified before any drop.
- **Frontend → API only**; no Supabase key in browser, ever.
- **Secrets never in git/chat**: `.env` gitignored, `.env.example` holds
  placeholders only. Keys: `GAMMASUMMIT_*` env vars.
- Naming: `NNNN_` migrations + ADRs, `gammasummit-<role>.service`,
  release-symlink deploys.
- One scheduler for rollups (pg_cron XOR backend timers — never both).
- Raw UW retention 24–48h; never let raw tables grow unbounded.
- Skylit API (`SKYLIT_API_KEY` in `.env`) is a **temporary RE tool** (sub ends
  ~Nov 2026); production must run UW-only.
- **UW PHX is the ONLY production data source going forward (source of truth,
  owner 2026-10-02)** — Skylit + leandata data = RE/reference/backtest
  archives only, never production inputs.
- **Rate limits are NEVER hit on any source** (Skylit API, leandata vendor,
  UW PHX, app.skylit.ai web RE): pace ≤50% of documented limits with jitter,
  exponential backoff + cooldown on any rate signal, daily request caps,
  incident comment + pause. A rate-limit hit is a process failure.

## Where things live

| Path | Contents |
|---|---|
| `../../backend/` | `api/` FastAPI, `core/` calcs (exposure.py), `ingest/`, `jobs/`, `tests/` |
| `../../db/` | `migrations/NNNN_*.sql`, `schema/`, `queries/` |
| `../../frontend/` | Vite+React SPA (`mockups/` = approved reference visuals) |
| `../../deploy/` | systemd, docker, VPS deploy scripts |
| `../../scripts/` | RE capture + research harnesses |
| `/Volumes/X10 Pro/gammasummit/` | cold tier + RE raw captures (external) |
| `../decisions/` | ADRs — architectural law; change needs a new ADR |

## Definition of done

Feature done = tests pass + lints clean + acceptance column met + documented
in the right folder. Never declare done on plausible output — verify with real
runs.

## Org rulebook
- Company structure, model tier ladder (T0 OpenJev -> T1 LiquidAI local -> T2 mimo -> T3 gated), harness policy (Multica frozen), reporting SLAs: `../docs/ops/AGENCY_ORG.md` (ADR 0006)
- Trading doctrine for any trading work: SignalForge `docs/TRADING_DOCTRINE.md` (per ADR 0005)
