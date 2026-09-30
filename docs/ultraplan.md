# UltraPlan — GammaSummit master execution plan

Date: 2026-09-30. Status: binding sequencing document. Sits on top of
`master-architecture.md` (the floor plan) and the parity checklist (the UI
contract). Owner directive: reach 1:1 skylit parity → freeze architecture →
port SignalForge → run production from gammasummit.

## North star

A lean, tiered, self-healing options-intelligence platform: Skylit-class UI at
1:1 behavioral parity (own identity + own value layer), bill that does NOT grow
with history, one canonical codebase under `gammasummit/`.

## Workstreams

| WS | Name | Depends on | Source of truth |
|----|------|------------|-----------------|
| A | UI parity (Skylit heatmap → chart → flow → AI) | — | `parity-checklist-skylit.md` + RE doc |
| B | Data machine (core, schema, ingest, jobs) | — | `master-architecture.md` §4–5, `data-tiering.md` |
| C | API (security-first) | B (schema), A (contract) | `master-architecture.md` §6 |
| D | Security + ops hardening | C | `security.md`, `security-future.md`, `operations.md` |
| E | SignalForge port + cutover | B+C+D | `migration-from-signalforge.md` |
| F | Frontend build (React) | A frozen, C contract | `design-reference-skylit.md`, demo v3 |

A and B run **in parallel** (no shared code). C bridges. E last.

## Phases, gates, definition of done

### P0 — Parity freeze (WS A, ~1–2 sessions)
Work: resolve checklist rows 🔍/📝 for heatmap: cell detail panel component
spec, movement-filter semantics, hover RAW HOVER, normalization constants fit,
node tier names; one intraday side-by-side session (live skylit vs demo).
- **DoD:** heatmap checklist = 0 open 🔍; owner signs "heatmap parity locked".
- Deliverable: demo v4 (heatmap only, pixel-honest) + updated checklist.

### P1 — Foundations (WS B, parallel with P0)
Work: `backend/core` (config/errors/logging/db), `db/migrations/0001`
(entities from master-architecture §5: types, partitions via pg_partman,
deny-default grants, BRIN+B-tree indexes), pgtap invariants, CI skeleton
(ruff/mypy/pytest + supabase-security linter + grants regression test).
- **DoD:** migrations apply clean on empty DB; `get_advisors` = 0 ERROR; CI
  green; ADR 0004 records schema.

### P2 — Data machine (WS B)
Work: ingest daemon (UW fetchers, T0 writer w/ batch-upsert+retry), jobs:
downsampler → T1, rollups → T2, retention/export → T3 (manifest-verified),
pgmq lazy-backfill queue; freshness metric + Uptime Kuma alert.
- **DoD:** 5 trading days of shadow data at target tiers; measured hot set ≤
  size budget; retention proves export-first (manifest verified); ADR 0005.

### P3 — API + security (WS C+D)
Work: FastAPI endpoints (grid/series/flow/freshness/jobs), OpenAPI spec,
passkeys + magic fallback auth, rate limits, cache headers, audit log
(pgaudit), Cloudflare edge; keyhub env injection optional.
- **DoD:** contract tests vs OpenAPI; ZAP baseline clean; anon probe finds 0
  readable data; p95 < 200ms on cached aggregates.

### P4 — Frontend v1 (WS F)
Work: React app from demo v3 + parity checklist: heatmap matrix w/ all
toolbar panels + cell detail, flow feed, AI card, ⌘K, shortcuts. Mock mode +
preview workflow (ADR 0002) from commit 1.
- **DoD:** visual/behavioral diff vs checklist passes; perf budgets met
  (shell <2s, widget <100ms); owner review on preview URL.

### P5 — Port + cutover (WS E)
Work: dual-write shadow from SignalForge ingest; 2-week reconciliation
(daily diff reports via DuckDB federation `postgres` extension); endpoint
flip; SignalForge → read-only → archive.
- **DoD:** 10 consecutive trading days of zero material diffs; rollback
  rehearsed; `gammasummit` = production.

### v2 (post-cutover backlog)
Chart workspace (Atlas-class), AI canvas (Talon-class), scanner/compass,
alerts + Web Push, replay (Shift+R spec), modes (Cloutseeker/SpotGamma/FATTE),
Node % premium features (saved presets, RAW HOVER), export images.

## Sequencing rules (hard)

1. No production writes to SignalForge outside approved ops actions.
2. Migrations precede writer restart; readers cut over after validated writers.
3. Every phase: ADR + tests + `get_advisors` clean + updated docs.
4. Parity gate P0 must pass before F builds beyond demo translation.
5. Retention jobs ship disabled until export manifests verified twice.

## Risk register (pointers)

- Value-model parity ceiling (RE doc §0) — own value layer calibrated against
  captures; never claim exact $ parity.
- Oct 30, 2026 Supabase Data API grants change — run linter on both projects.
- UW API budget — circuit breaker + fetch budgets (toolkit doc).
- Weekend ingest spikes (open question) — downsampler must dedupe.
- 0928 export artifacts unaccounted — resolve in P2.

## Work queue after this plan is accepted

1. P0: heatmap parity closeout (demo v4)
2. P1: `db/migrations/0001` + `backend/core`
3. Then P2 → P3 → P4 → P5 strictly in order.
