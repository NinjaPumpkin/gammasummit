# Skylit Value Model — RE verdicts & build path

Question (2026-09-30): can we reverse-engineer the heatmap cell-value
calculations from data we hold today? Short answer: **no — and now we know
why, twice.** The path forward is a dynamic-state model of our own.

## Verdict 1 — static chain formula (2026-09-29, n=3,899 cells)

`SignalForge/scripts/skylit_formula_fit.py` fitted 6 chain formulas
(gamma×0.01×OI×S² signed, |gex|, vanna, charm, ΔOI, volume). Best single
feature spearman **0.149**; multivariate OLS R²=0.033; best-fit scale swings
55M→231M in one day while chain state barely moves. → their values embed an
input absent from the option chain.

## Verdict 2 — flow-augmented fit (2026-09-30, 22 pairs, n=6,208 cells)

`SignalForge/scripts/skylit_formula_fit_flow.py` — added flow_scores features
(signed premium, flow_score, size over 30m/2h/all windows) + ask/bid imbalance
+ ΔOI to the chain baseline. `data/skylit_fit_flow_summary.json`:

| variant | spearman | top-q overlap |
|---|---|---|
| gex_signed | −0.020 | 0.326 |
| vex_signed | −0.004 | 0.311 |
| flow_prem_2h alone | **0.000** | **0.092** |
| gex + ΔOI | +0.030 | 0.376 |
| **gex + ask/bid imbalance** | **+0.101** | **0.400** |
| full (6 features) | +0.102 | 0.397 |

Findings:

1. **Recent flow premium does not drive their cells** (top-q 0.092 = worse
   than chance) — their layer is NOT "where flow went in the last hours".
2. Best signal = ask/bid volume imbalance + gamma (+0.10) — real but nowhere
   near visual parity (need ~0.7+ to reproduce their surface's ranking).
3. Confirms verdict 1: their values are a **dynamic state**, not a static
   function of chain + recent flow. Their own doctrine agrees — rate of
   change, node growth/decay, rolling ceilings/floors are central.

## What is closed / what stays open

- CLOSED: exact-$ parity. Any claim of reproducing their numbers is false.
  Both fits are archived as the evidence (`data/skylit_fit_summary.json`,
  `data/skylit_fit_flow_summary.json`).
- OPEN: a **dynamic-state model**. Their doctrine (Core Concepts) says values
  respond to accumulation/unwinding speed and history of interaction. Testable
  features we can now build: Δgamma over 5m/30m/1d (our T0/T1 + king_node_history
  + gamma_data_v2), node interaction history (fresh/tested/delivered), OI
  migration over multiple days, spot-relative distance. This is exactly what
  the new tiered architecture makes cheap.

## Calibration path (sanctioned, owner has API access)

Their public API (`api.skylit.ai`, one key) returns their values as data:

- `GET /v1/heatmap` — live per-strike `{strike, value, nodeType, velocityPct}`
- `GET /v1/historical` — replay at a past instant (1-second resolution where
  1s history exists), back to 2023-03-28
- `GET /v1/historical/range` — every snapshot in a 15-min window
- `GET /v1/stream` — live SSE

Plan: collect same-instant pairs (their values + our full feature state incl.
history) over ~20 sessions via 1s replay frames → fit a **dynamic model**
(temporal features) to their values as target → keep only the behavioral
kernel (how nodes attract/repel) in our own value layer, own weights.

## Product stance (locked)

- Visual system + behaviors: 1:1 parity (achievable — measured).
- Value layer: **ours** — gross-gamma surface + flow-directionalized adjustment
  (from our flow_scores/outcomes) + dynamic-state terms, calibrated toward
  their surface's behavior where license/API permits, validated by how price
  actually interacts (node touch reactions logged and scored — our edge vs
  their read-only product).
- Never present their numbers as ours; never copy their private weights.
