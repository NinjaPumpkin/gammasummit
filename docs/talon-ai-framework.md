# Talon AI framework — what the "secret sauce" actually is

Reverse-engineered from Skylit's own public docs (Talon field guide + Core
Concepts + Academy references, fetched 2026-09-30). Verdict up front: **there
is no hidden model — the sauce is a reading doctrine + strict data grounding +
guardrails.** Every layer is replicable on our stack.

## The five ingredients

1. **Reading doctrine (their Academy/Patternpedia) — the actual sauce.**
   Semantic rules for interpreting the map:
   - absolute value > sign/color (magnitude = pull strength)
   - nodes are magnets: pull strengthens as price converges; deflection margin
     ~5–10 SPX points; drives-off early session, pin jobs late
   - King = dominant node (contested king if <10% ahead of next), Gatekeeper =
     deflection point between price and king (test-fail → map reshuffles)
   - retest decay: 1st touch strongest → 2nd weaker → 3rd+ unlikely to hold;
     "fresh > delivered"; node growing (rate of change) → reversion more likely,
     node shrinking → less
   - rolling ceilings = bearish evidence, rolling floors = bullish evidence
   - midpoints = worst R:R (1:1), trade range edges
   - hedge nodes (event insurance, slow, far), air pockets (low-resistance
     zones; negative-gamma pocket = violent, positive = mild), OPEX-week
     distortion (nodes weigh less), power-hour liquidations (mechanical flow)
   - level lifecycle vocabulary: fresh / tested / delivered / spent
   - patterns as named setups: Whipsaw, Rainbow Road, Gatekeeper, Trend, Rug
     Setup, speculative/decoy nodes, topping/bottoming via VEX
2. **Live data grounding.** "Numbers come from Skylit data, not from memory" —
   every level/strike/expiry/price is a live tool read (their own API), with
   sources shown on push-back ("fetches the data again and shows its source
   instead of defending its last answer").
3. **Context injection.** "It sees your page" — the open page + focused ticker
   ride with every message, so "what are the levels?" is a complete question.
4. **Horizon + effort selectors.** Scalp/Day/Swing/Position = which expiries
   get read (same ticker, different maps). Fast/Balanced/Deep effort for
   multi-read chains (confluence, trade maps, rotation scans). Prose vs
   Concise field blocks + follow-up chips + queued questions.
5. **Guardrails = trust.** "It does not make the call": trade map = reference
   levels + **structural invalidation** (price that proves the idea wrong) +
   risk-to-reward. Never buy/hold/exit/size, even when asked via template.
   Disclaimer gate; thumbs-down → report flow.

## Their deterministic reads (slash commands)

`/levels`, `/talon` (trade map), `/trinity` (SPXW+SPY+QQQ confluence — 2 of 3
agree = leaning), `/watchlist`, `/breadth`, `/flow` (single-leg + week compare
+ premium leaders buy/sell split), `/darkpool`, `/metrics` (put/call, max
pain), `/earnings`, `/market`, `/news`, `/screen air pockets|rugs`,
**stacked kings** (gamma king + vanna king on same strike/expiry). Cards
(trade map / scan report / Trinity ladder) are structured blocks over the same
data as the prose.

## GammaSummit replication map (our AI Analyst)

| Ingredient | Ours |
|---|---|
| Doctrine | implement as analysis functions over our nodes (own names: king/wall/gatekeeper/significant) + our own pattern catalog; seed from our measured truths (close-window rejection log, flow quality-loop stats) |
| Grounding | all numbers via our API (T0/T1/T2) + DuckDB (T3); never from model memory; cite table+timestamp |
| Context | page context + ticker + horizon ride with every message (mobile single-UI) |
| Horizon/effort | same selectors (they are generic UX patterns) |
| Guardrails | structure + invalidation + R:R; no advice, ever; sources shown on challenge |
| Extra they can't do | **outcome-verified claims** — our flow_outcome_tracking hit-rates and node-touch scoring give the analyst evidence they don't publish; every doctrine rule gets measured (their "rule of thumb, not a tested signal" → our tested labels) |

Suggested first commands (own names): `/read` (trade map), `/trinity`,
`/flow`, `/darkpool`, `/levels`, `/screen`, `/stacked` (gamma+vanna co-located
king), `/why` (node history + rate-of-change explanation for a level).
