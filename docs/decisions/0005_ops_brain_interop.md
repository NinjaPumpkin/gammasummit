# ADR 0005 — Ops brain interop: scope boundary and handoff to GammaSummit

Date: 2026-10-02. Status: **Accepted** (operating). Revisit at SignalForge cutover
per `docs/ops/migration-from-signalforge.md`.

Context: the week's ops-brain builds were driven conversationally and live OUTSIDE
this repo, in the production layer (SignalForge + `~/.hermes` harness). This ADR
notifies GammaSummit of what exists, fixes the boundary, and sets the handoff path
so product specs never get built from chat memory.

## What now exists (production, operating)

| Piece | Where | Status |
|---|---|---|
| Decision layer: `typesafe-mcp` (OpenJev @ codiv) in ALL 6 harnesses + 6 decision skills | `~/.hermes`, per-profile configs | live |
| Receptionist cron (inbox → JEV urgency gate → one telegram digest) | job `9f31816e71b3` (default profile) | live; delivery pending gateway telegram recovery |
| Market Analyst Outlook swarm workflow | `SignalForge/docs/MARKET_ANALYST_OUTLOOK_WORKFLOW.md` | designed; bot paused, pinned mimo-v2.6-pro, fallbacks kimi-k3 → glm-5.3 |
| Local VLM (LFM2.5-VL-3B, GGUF) | `127.0.0.1:8092`, client `~/tools/lfm-vlm/` | live |
| Eval framework (purposes → score → improve) | `SignalForge/eval/` + `data/ai_eval.db` | live, baselines frozen 2026-09-25 |
| AI systems reference (incl. OpenJev addons catalog) | `SignalForge/docs/AI_SYSTEMS.md` | current |
| Skylit UI map (Trinity/Atlas/nodes/replay controls) | `SignalForge/docs/SKYLIT_REVERSE_ENGINEERING.md` + this repo's inventory | partial, updated as probed |

## Decision

1. **Ops brain stays in the production layer** (SignalForge + harness) until the
   measured cutover. It is a consumer and critic of Skylit, not a GammaSummit
   feature surface. No product code for heatmap/Atlas/Talon-canvas lives in it.
2. **GammaSummit consumes SPECS, not brain code.** Handoffs:

   | Brain produces | Lands in |
   |---|---|
   | Talon probe findings (answer shape, depth, accuracy vs our ground truth) | `docs/architecture/talon-ai-framework.md` |
   | Skylit feature/node map (Trinity, Atlas chips, Barney/Pika tiers, replay controls) | `docs/architecture/skylit-product-inventory.md` |
   | Decision schemas that work in production (`jev_ask` question sets, thresholds) | `docs/architecture/ai-stack.md` → Product feature → layer wiring |
   | Labeled screenshots / UI-drift findings | `docs/architecture/design-reference-skylit.md` |

3. **Notification protocol:** changes to any of the above get an ADR here
   (numbered, following 0001–0004); product decisions that change what the brain
   may assume (data shapes, endpoints) get an ADR here too. Cross-repo pointers in
   both directions — SignalForge docs are the spec source until cutover.
4. **Scoping rule (owner, 2026-09-25):** OpenJev decision MCP = all harnesses;
   the OpenJev+LiquidAI combo (VLM + decision loop) serves SignalForge/Gammasummit
   ONLY. Every wiring declares a purpose, is scored, then improved.

## What is NOT built yet (registered, not just chat)

SkyWatch P1–P4 (API+DOM state reader → decision cadence → telegram trade calls →
scoring), Atlas replay post-mortem (sparse capture + hindsight labels), node-alert
filter, Talon probe set. All carry `purposes.yaml` entries in
`SignalForge/eval/` before first run — no wiring ships without a purpose.

## Revisit triggers

1. Cutover per migration plan → brain components ported module-by-module with
   their decision logs.
2. If GammaSummit ships its own analyst surface, delivery moves behind its API;
   the receptionist becomes a client.
