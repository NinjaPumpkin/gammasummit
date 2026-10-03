# ADR 0006 — Agency org adopted; harness policy (Multica frozen; tier ladder)

Date: 2026-10-02. Status: **Accepted**.

Context: three departments (personal estate via Open Brain, trading desk via
receptionist, product via this repo) were operating as parallel bots with ad hoc
reporting. Owner asked: need Multica? Mercury 2 or LiquidAI for small/private
models? mimo vs smaller for computer use? And mandated org docs that make ANY
called agent understand tools, context, and how to trade with gamma/GEX/VEX
learned from skylit.

## Decision

1. **`docs/ops/AGENCY_ORG.md` is adopted** as the company rulebook (faces,
   chain of command, reporting SLAs, model tier ladder, harness policy, scorecard).
2. **Harness policy: Hermes is the only control plane.** Multica frozen
   (read-only legacy; no new work; migration target = hermes kanban). Coding
   harnesses (Pi/CC/OpenCode/dsh/Odysseus) remain executors only. New harness
   requires an ADR.
3. **Tier ladder:** T0 OpenJev (all decisions) → T1 LiquidAI local (perception/
   drafts) → T2 mimo-v2.6-pro (default reasoning; kimi-k3/glm-5.3 fallbacks) →
   T3 bigger only via `jev_route_model` + Smart-Prompt compiler, logged.
   Mercury 2 = personal-face fastlane only; it never bypasses T0 decision gates.
4. **Trading doctrine:** SignalForge `docs/TRADING_DOCTRINE.md` is the on-call
   bundle every agent loads before touching trading work (tools, data, skylit-
   learned strategy, safety gates).

## Why not

- Multica: second control plane, skills never sync with Hermes, hosted dispatch
  failure history (5,535-run trigger), duplicated by inbox + Auto-Trigger + kanban.
- One model for everything: fails cost (volume work at frontier prices) or fails
  quality (3B models on multi-step UI reasoning — proven today).

## Revisit triggers

1. Multica ships a capability hermes kanban genuinely lacks → ADR then.
2. T1 local models measurably beat mimo on a computer-use benchmark → tier edit.
