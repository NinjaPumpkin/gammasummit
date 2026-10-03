# AGENCY_ORG — the company rulebook (faces, departments, tiers, reporting)

Status: adopted 2026-10-02 (ADR 0006). Applies to every agent, model, and harness
we operate. Cross-reference: `../decisions/0005_ops_brain_interop.md` (scope
boundary), SignalForge `docs/TRADING_DOCTRINE.md` (trading on-call kit).

## 1. The three departments (faces report to the owner)

```
                         OWNER (you)
                              │
     ┌────────────────────────┼────────────────────────┐
     ▼                        ▼                        ▼
👤 PERSONAL ESTATE     🏛️ TRADING DESK           🏗️ GAMMASUMMIT (product)
  face: Open Brain       face: Receptionist         face: gammasummit-pm
  assistant chats        → telegram TRADING topic    profile + ADRs
  workers:               workers:                   workers:
  · telegram/slack/      · 16+ cron jobs in         · gammasummit-{pm,backend,
    drive ingest bots      8 profiles (keeper,        frontend,research} profiles
  · route-thought          warden, quartermaster,   · build agents (AGENTS.md
  · digests                sentry, archivist,         = builder guide)
                           uw-*, flow-*)           · VPS brain_telegram bot
                         · market-analyst swarm
                           (5 analyst profiles,
                            workflow doc)
                         · Multica legacy crew
                           (FROZEN — see §4)
                         · delegate_task children
```

## 2. Chain of command (non-negotiable)

1. **Workers report UP only** — to their department lead, never across lanes.
   (Coder→PM style: analyst → lead → face → owner.)
2. **Only the face talks to the owner.** Personal = assistant chats; Trading =
   receptionist topics; Product = ADRs + pm profile. Workers file reports to
   inbox lanes (`reports/market-analyst/<date>/`, cron output dirs, issues).
3. **Silence unless called** — mention-only / lane-only responses. No lane, no talk.
4. **Every handoff carries a contract**: acceptance criteria in, evidence-stamped
   completion out (`jev_review_completion` + `lib/jev_done_claims.py`).
5. **Cross-department = ADR** (canonical `docs/decisions/`), never side-channel edits.

## 3. Sparring → alignment → execution (the 3-layer loop)

Adopted 2026-10-02 from the owner's architecture doctrine. Order is mandatory:

1. **Sparring (adversarial pre-review).** Before any architecture, ADR, or
   major plan is dispatched: a FRONTIER MODEL OTHER THAN ITS AUTHOR attacks it —
   stress-test topology, surface edge cases, challenge assumptions (rotate from
   available frontier harnesses: DeepSeek/dsh, Claude/CC, mimo; a self-review
   does not count). Findings are filed in the ADR/plan as an explicit
   `Red-team` section. Sparring output = critique ONLY, never executed.
2. **Orchestrator inspection.** Hermes inspects the sparring-validated plan:
   enforces constraints (backups, non-destructive writes, SCONE wrappers,
   preflight/fail-closed), then generates or audits the code before a single
   line executes (skills: architecture-planning, writing-plans, jev-tool-guard).
3. **Hard boundary law (deterministic vs probabilistic).** Deterministic logic
   stays strictly deterministic. Probabilistic outputs — JEV nudges, classifier
   scores, generated text — cross into execution ONLY through rigid numerical
   guardrails (thresholds ≥0.8 act / 0.5–0.8 review, ranges, fail-closed
   staleness gates) or explicit human approval. **Raw model text never
   commands execution.**
4. **Alignment gate.** Execute only when all three layers agree: red-team
   record present + orchestrator constraint check green + JEV gate (and human,
   for money) signed. Stamp it: `ALIGNMENT: ok — sparring/constraints/gates`
   in the plan or ADR before dispatch.

## 4. Model tier policy (THE cost/accuracy ladder)

| Tier | System | Use | Gate |
|---|---|---|---|
| **T0** | **OpenJev** (codiv, `typesafe-mcp`, 5 tools) | ALL decisions, routing, guards, completion checks — 0 output tokens | always first; thresholds act≥0.8 / review≥0.5 |
| **T1** | **LiquidAI local** (LFM2.5-VL-3B :8092, LFM2.5 text; codiv diffusiongemma for cheap hosted text) | perception at volume: frame extraction, structuring, drafts — $0 | never for final judgment |
| **T2** | **mimo-v2.6-pro** (fallbacks: kimi-k3 → glm-5.3) | default reasoning: live computer-use navigation, analysis, complex multi-step | — |
| **T3** | bigger models | residual hard problems ONLY | requires `jev_route_model` verdict + Smart-Prompt compiler pass (`prompt-improver` shape), escalation logged |

Rules: **a worker may never jump tiers on its own.** Mercury 2 (Hermes fastlane)
stays the personal face's quick-answer path; it does not bypass T0 for decisions.
Computer-use split: LFM = eyes (volume extraction), mimo = brain (live navigation);
escalate VLM→mimo on UI drift or low confidence (`jev_route_model`).

## 4. Harness policy (anti-sprawl)

- **Spine = Hermes** (profiles, cron, gateway, inbox, kanban, delegation).
- **Coding variety stays**: Pi, Claude Code, OpenCode, dsh, Odysseus — used as
  executors, not as new control planes. No new harness without an ADR.
- **Multica = FROZEN**: read-only legacy SIG board; no new work; skills never
  sync with `~/.hermes/skills` so new work there fragments knowledge. Migration
  of anything valuable → hermes kanban / issues. Its dispatch function was
  replaced by the rebuilt Agent Auto-Trigger (paging + 6h cooldown + caps).
- Decision layer is harness-agnostic: `typesafe-mcp` is wired in all six and is
  the ONLY way decisions are made (skills `jev*` in every harness).

## 5. Reporting cadence (SLA per department)

| Department | Push | Pull | Escalation |
|---|---|---|---|
| Trading desk | event alerts (urgent noul ≥0.8) + 08:30 digest + EOD post-mortem | owner asks receptionist → reads eval/reports, DBs (read-only), Open Brain | blocked/preflight → local fallback, never silent death (streak alerts) |
| Product | ADR on every architectural change + daily build notes | AGENTS.md routes any builder to `docs/decisions/` | P0 gates stay honest (per AGENTS.md) |
| Personal | ingest on arrival, digests on schedule | on-demand | partition from trading scope (no bleed) |
| Delegation children | consolidated report on completion (evidence-backed) | parent inspects transcripts | interrupted children re-dispatched, never assumed |

## 6. Org scorecard (the company is scored too)

Per department, registered-style like `purposes.yaml`: throughput, rework rate,
spam incidents, cost/task (tier-mix), report latency. Weekly review; changes
versioned. The company obeys the same rule as every wiring:
**purpose → judge → score → improve.**
