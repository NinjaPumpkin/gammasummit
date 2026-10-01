# AI stack — layering Jev, LiquidAI, and hosted models

Owner question 2026-09-30: use codiv/Jev + LiquidAI on the VPS, or Hermes +
mimo v2.6 pro? And which of the awesome-jev projects fit?

**Verdict: not either/or — they are different layers. Use all three, each in
its lane.** Jev is explicitly *not a chat model* ("unstructured state + typed
question → typed decision with confidence"), so it cannot write analysis
prose; mimo can't beat it on cheap typed decisions.

## Layer map

| Layer | Component | Does what | Where |
|---|---|---|---|
| **1 — Analyst prose** (Talon-class) | **mimo v2.6 pro** primary; fallbacks claude (dexuebao) / glm-5.3 (zai) / v4.1-flash (deepseek) | market rundowns, chat (Cmd+J), canvas building | hosted, multi-provider failover (existing proven stack) |
| **2 — Typed decisions** (System One) | **Jev via codiv/TypeSafe MCP** | flow bull/bear/neutral typed + confidence, node triage, alert escalate/ignore, **rubric-scoring of Analyst claims against live data** (our outcome-verified twist), tool-call guards | hosted API ($0.000004/call, ~81 ms per jev-trader's published dry run) |
| **3 — Local free/high-volume** | **LiquidAI LFM2.5 `:8092`**, VL-450M `:8094`, whisper `:8097`, embed `:8093`, classify `:8095/:8096` | per-alert tags, similar-days embeddings (their "5 similar days" match), image/chart extraction, voice | VPS llama-servers, zero marginal cost |
| **4 — Build agents** | Hermes (mimo v2.6) + harness fleet | builds the product | dev |

## VPS reality check (verified 2026-09-30, read-only)

Running: `brain-mcp` (GammaSummit Brain MCP), `tradingview-mcp`, embed-serve
:8093, classify-serve :8095/:8096, whisper :8097, llama-server :8092
(LiquidAI) + :8094 (VL-450M), hermes health-monitor :8099.

**No openjev/codiv daemon on the VPS** — Jev runs as MCP from the harnesses
(TypeSafe `typesafe-mcp`), not as a VPS service. It was flaky earlier in this
session; verify availability at build. LiquidAI stack = confirmed live.

## awesome-jev adoption shortlist (1.7k★ list; its own rule: curation ≠ endorsement)

| Project | Pattern we take | Maps to |
|---|---|---|
| `ai-hedge-fund` (virattt) | native JevLLM typed-decision integration, no parsing fragility | our flow/decision pipeline |
| `jev-guard` (klauswg) | typed risk triage **with hard-rule veto layered on top** + published 3-column calibration vs rules-only baseline | alert triage; our rules stay authoritative, Jev scores |
| `Jev X Sentiment Analysis` | mass-evidence → pre-process → **decision card** (entry/stop/target) | our AI Analyst action cards |
| `jev_stock` (sosopop) | structured market state → typed direction + backtest script | pipeline shape + validation habit |
| Verification & Guardrails / Scoring & Ranking categories (37+37) | claim-scoring + guard patterns | Analyst claim verification |
| `typesafe-mcp` / `jev-mcp` | MCP bridge | already how we call it |

Before adopting any repo: real API call present? runnable check? license?
(code-review checklist from the list itself). Read also for our confidence
thresholds: "Jev Can't Be Calibrated" (alexmolas, 2026-09-23) — we should
calibrate our OWN escalate thresholds against `flow_outcome_tracking` rather
than trusting model confidence blindly.

## Portability / GitHub stance

- Jev = optional provider behind the same AI-provider abstraction (BYO-key),
  nothing hard-wired — code is open on GitHub and must not lock to one API.
- **Laya** (Apache-2.0, laya.tools, ~950 projects) = open Jev-compatible
  alternative → fallback if Jev access/pricing changes. Decision layer is
  swappable by design.
- Privacy: TypeSafe policy = no training on prompts, retention exists; market
  data is public → fine. (Personal-document rule from KeyHub unchanged.)

## Use-case map: Jev + small models in the quant loop (2026-09-30)

Guardrail (hard): backtest math = deterministic DuckDB code. Models wrap the
loop — never inside the numeric core. Every AI decision logged as
(typed question, evidence IDs, answer, confidence) → auditable, GitHub-grade.

### 1. Trading decisions — YES (decision layer, paper-first)
Pattern (from `jev-guard`/`jev-trader`): evidence bundle (node state, flow,
regime tag) → Jev typed `Choice` + confidence → **hard-rule veto on top** →
execution gate. Nexus paper wallet (v2) is the sandbox: the loop runs live on
play money, decisions get outcome-scored like our 28,939 labeled alerts —
only after hit-rates hold does it gate real signals. Confidence never trusted
blindly (calibration critique) — thresholds fitted to `flow_outcome_tracking`.

### 2. Backtesting — AROUND it, not inside it
- **Inside**: deterministic rules over DuckDB/Parquet (fast, reproducible).
- **Jev at the edges**: (a) pre-labels regime/day types as backtest FEATURES
  (typed classify per day: risk-on/off, opex, vol-event), (b) post-hoc rubric
  scores of results — "train vs test drift? lookahead smell? sample too thin?"
  (overfitting sniff-test, the `jev-guard` 3-column calibration style),
  (c) compares strategy variants as typed questions over the result tables.

### 3. Strategy creation — YES (the agent research loop, standing method)
Candidate rules generated by agents → backtested → **Jev scores evidence
quality / overfit risk / rule contradictions (typed)** → small model drafts
the research note → mimo reviews → outcome tracking adjudicates. Strategy =
typed schema (entry/exit/conditions); Jev validates logic (conflict?
lookahead?) before a single credit of backtest is spent. Feeds the standing
research queue (e.g. gamma COM-migration → settle question).

### 4. Data analysis — YES (where the small model earns its keep)
- **LiquidAI LFM2.5 `:8092`** (free, unlimited): alert/trade journal
  narratives, batch relabeling of the 28,939 outcomes + new ones, report
  drafts, composing Jev's typed-question context cheaply.
- **embed `:8093`**: similar-days matching (their "5 similar days" feature) +
  duplicate-flow detection + strategy-pattern similarity.
- **classify `:8095/8096`**: flow-pattern labels (deep-ITM cluster, 45° ladder
  — their moneyness taxonomy), regime tags, data-quality triage.
- **VL `:8094`**: chart-image extraction; **whisper `:8097`**: voice notes →
  journal.

### 5. The flywheel (the real upgrade)
Jev labels bootstraps → embeddings + local classifier trained on
`flow_outcome_tracking` → classifier does volume cheaply → **Jev audits the
classifier** (verification layer) → mimo rewrites doctrine → loop. Model
budget stays flat as alert volume grows. Evaluation harness = our own
3-column comparison (rules-only vs Jev vs classifier) on held-out days,
bench-style, re-run monthly.

## Add-ons from the ecosystem sweep

- Decision journal schema (typed q/a/confidence/evidence) as a first-class
  table — enables Nexus leaderboard + reproducible Analyst claims.
- Tool-guard/decision MCP for the agent fleet during build (already used in
  harnesses).
- `tradingview-mcp` (running on VPS) = market-context tools for the Analyst.
- Laya compatibility shim noted in ai-stack.md keeps the decision layer
  swappable for the open-code release.

## Product feature → layer wiring

- Chat Analyst (Cmd+J) → L1 + L2 claim-checks
- Flow feed scoring → L2 typed + L3 tags (existing `flow_scores` + outcomes train thresholds)
- Alert triage → L2 with hard-rule veto
- Similar-days / historical-compare → L3 embeddings
- Voice/chart input → L3 whisper/VL
- Everything user-facing reads from our API only (never calls AI providers from the browser)
