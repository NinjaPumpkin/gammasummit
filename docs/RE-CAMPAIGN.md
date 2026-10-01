# Skylit RE Campaign — 2-month budget & capture plan

Owner window: **~2 months of Skylit left** (goal: replicate with UW lifetime
sub afterwards, drop Skylit). Started 2026-09-30. Objective: fit the missing
cross-expiry/dynamic layer so UW data → Skylit nodes at **≤10% error** (owner
bar), then run UW-only.

## Limits & rates (verified 2026-09-30, docs + developer console)

| Item | Value |
|---|---|
| Account | lapcheong · purchased credits 0 · free grant **5,000** |
| Plan credits | Pro monthly API credits used first, reset 1st ET (Pro = 100,000/mo per announcement) |
| Heatmap / GEX levels | **1 credit** / call (≤10 symbols) |
| Historical replay `/v1/historical` | **5 credits** / call |
| **Historical range `/v1/historical/range`** | **25 credits** / call — every frame (1s where available) in a ≤15-min window, ≤5 symbols |
| Live stream | 1 credit / symbol to open + 1 / symbol / minute; 1-hour max per connection |
| Flowseeker | 1–5 credits / call |
| Rate limits | plan-dependent (`GET /v1/account` → `data.limits`); invite = 60 req/min; standard = 120/min; /v1/heatmap cached 5s |
| Failures | all 4xx/5xx refunded — retries free |
| Archive | Pro historical back to **2023-03-28** |

## The killer tool: historical range

25 credits per 15-min window × 26 windows = **650 credits per full RTH day for
up to 5 symbols at 1-second resolution**. The RE ground-truth machine.

## Budget (2 months ≈ 200K plan credits + 5K free)

| Phase | What | Cost |
|---|---|---|
| P-1 (day 1) | Backfill the 23 existing capture days + their 1s ranges (SPX/SPY/QQQ/IWM) | ~3K |
| P-1 continuous | 4 symbols × full RTH × 40 sessions, 1s frames | **26K** |
| P-2 | `/v1/heatmap` live poll for nodeType + velocityPct spot checks (100/day) | ~4K |
| P-3 | Streams: 4 symbols × RTH × 20 sessions (velocityPct ground truth, window mechanics) | ~31K |
| P-4 | Deep days: 60-min windows pre/post RTH around open/close (10 days) | ~3K |
| Buffer | retries, sweeps, MCP experiments | ~10K |
| **Total** | | **~75K of 205K** — headroom 2×; $50 pack only if monthly grant proves smaller |

Watch `X-Credits-Remaining` on every response; `402` = stop and tell user.

## Capture architecture

- `scripts/skylit_re_capture.py` (to build): paces 25cr/15-min range calls for
  SPX/SPY/QQQ/IWM, stores raw frames Parquet → `X10 Pro/gammasummit/t3/re/`
  + manifest. Runs on Mac launchd during RTH.
- Pairing: our `gamma_data_v2` (~2 min cadence, call/put gex, vanna, ask/bid
  vols, prev_oi) aligns to their 1s frames by timestamp.
- Temporal features derived: Δgex 5m/30m/1d, OI migration, flow history
  (`flow_scores`), node interaction state.

## Fit targets (the missing layer)

1. Cross-expiry weighting: why their king sits in its column (ratio evidence:
   their column ratios run 1.2→13.3 intraday, no static factor).
2. Value scale dynamics (55M→231M/day swings).
3. `velocityPct` semantics = direct window-Δ readout of their value → extra
   equation system per cell.
4. nodeType thresholds (king/gatekeeper/…) as a by-product.

## Acceptance (unchanged owner bar)

king exact ≥ **90%** (≤10% error), top6 ≥ 5/6 on ≥80%, ≥20 session-days →
owner signs → `backend/core/exposure.py` (fresh code) frozen as the UW-only
implementation → Skylit subscription cancelled.

## Post-expiry replication (UW lifetime only)

Everything fitted must be computable from UW alone: chains/OI/flow buckets
(already the datasource of every Skylit feature). Final artifact =
`exposure.py` + fitted constants + verification report + drift alarm
(node-agreement checker runs weekly against nothing — Skylit gone — so
validation shifts to price-reaction scoring of our nodes).

## Day-1 actions (owner)

1. Open https://app.skylit.ai/developer → **Create a key** (accept API Terms —
   owner action), store as `SKYLIT_API_KEY`.
2. `GET /v1/account` → record real `limits` + monthly credit grant.
3. Start P-1 backfill (cheap, immediate: it covers our 23 existing captures
   at 1s truth).
