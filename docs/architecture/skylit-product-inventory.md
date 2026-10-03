# Skylit product inventory → GammaSummit inclusion map

Full docs sweep 2026-09-30 (llms.txt index + guides + API reference). Verdict:
every module reads public/OPRA/UW-style market data — **all replicable on our
UW lifetime stack**. Inclusion decisions below. Names are ours.

## Module map

| Skylit module | What it is | GammaSummit | Phase | Source for us |
|---|---|---|---|---|
| Heatseeker | strike×expiry exposure heatmap + nodes | ✅ core (parity target) | P0/P4 | UW chains (gex/vanna) |
| Heatmap replay | time-step replay of the heatmap (1m / 5m / … steps) — scrub history frame-by-frame | ✅ Heatmap replay (new, owner 2026-10-02) | P4 | our snapshots (accrue from day 1 — replay is only as good as our stored frames) |
| Node alerts | filterable node alerts (criteria: node tier / strike / ticker / change) | ✅ Node alerts + filtering (new, owner 2026-10-02 — "can come up with right now") | P4 | our node classification + alert rules |
| Flowseeker | live flow feed + scoring + scanners | ✅ Flow module | P4 | UW flow + `flow_scores`/outcomes |
| Atlas | chart workspace + heatmap overlay on chart, works for ALL tickers | ✅ Chart module | P4 | leandata + our levels |
| Tempest | volatility intelligence (SVX, cones, sigma, skew, tilt, earnings, VRP) | ✅ **Vol module (new — owner pick)** | P2 calc / P4 UI | UW chains IV + leandata realized |
| Talon | AI analyst | ✅ AI Analyst | P4 | our doctrine doc |
| Nexus | $100K paper wallet + leaderboard | 📋 v2 (gamification) | v2 | own |
| Academy/Patternpedia | reading doctrine | ✅ Analyst knowledge base | P4 | own doctrine (see talon-ai-framework.md) |

## ⭐ RE-critical endpoints (added to capture campaign)

| Endpoint | Cost | Why |
|---|---|---|
| `GET /v1/gex/levels` | 1cr | **node classification ground truth** (king/gatekeeper/pika/barney/significant + distance from spot) — their tier thresholds directly observable. LIVE only → sample hourly in campaign |
| `GET /v1/stats/daily` | 5cr | per-day cell extremes + `peakAbsMean` concentration — value-layer validation + universe ranking |
| `GET /v1/vol/history` | 5cr | **up to 2 YEARS of their daily SVX/tilt/skew columnar** — validates our Vol module cheaply |
| `GET /v1/vol/derived` | 3cr | 1y usual-range bands + VRP series + setups |
| `GET /v1/vol/snapshot` | 5cr | occasional full-module validation pulls |

## Tempest (owner pick) — replicate map

All readings computable from UW chains + leandata prices:

| Reading | Their definition | Our implementation |
|---|---|---|
| SVX (1d/9/30/3m/6m) | constant-maturity IV, VIX-style variance strip on the symbol's own chain | strip interpolation over UW chain IVs |
| SVX weekend-adjusted | weekly calendar pattern removed | own estimator (calendar-variance adjustment) |
| IV rank / percentile | vs trailing year on adjusted reading | leandata history |
| Term 9−30 / curve state | backwardation vs contango | strip slope |
| Expected-move cones (close/1d/week/opex/30d) | 1σ bands from implied variance | own calc + Atlas overlay |
| Sigma | today's move in units of priced 1d move + budget + odds | own calc (running sigma) |
| Skew rr25/bf25 + skew %ile + SKEW index | 30d 25-delta RR/BF | own calc from chain |
| Tilt | 1-strike-OTM call vs put premium imbalance, z + %ile | own calc from UW premiums |
| Events (earnings move + VRP) | implied move vs past moves; VRP = implied − realized | UW earnings + leandata realized |
| `/vol/market` complex | VIX1D/9D/3M/6M, VVIX, SKEW from SPX+VIX chains, curve roll, regime, Mag7 dispersion, Fear&Greed | own calc from UW SPX/VIX chains |
| Radar screener | whole-universe ranking by richness/cheapness | own DB query + preset filters |
| Setups | past episodes of today's conditions | own (leandata 2y) |

Known gaps vs them: their 2y Tempest history backfill (we start accumulating
now — but `vol/history` pulls let us VALIDATE during the window), thin-chain
quality flags (we replicate via quote-depth heuristics).

## Flowseeker → our Flow module (feature-level parity)

Build from existing UW + `flow_scores` + `flow_outcome_tracking`:
- live feed + filters + saved tabs (22-col spec already captured)
- **Flow Score −100..+100 + conviction weighting** (we have `flow_score` + outcomes to VALIDATE ours — they can't)
- **momentum z-scores vs time-of-day baseline** (5m/30m/1h) — new calc, easy
- historical-compare (today vs 20d avg + 5 similar days)
- logical sweep grouping (1-sec multi-exchange merges) — UW sweep flags
- vol-oi accumulation score (new vs closing positions) — from vol/OI + ΔOI
- moneyness pattern detection (deep-ITM..deep-OTM buckets + named patterns)
- chain/contract bid-ask-mid ratios + **call/put-aware bull/bear pressure**
- NCP/NPP tide (we have `flow_tide_5m`), market breadth + sector rotation
- dark pool (UW darkpool feed — healthy per ops notes)
- max pain, put/call ratio (`/metrics`)

## Atlas indicators (new specs found)

- **GEX VWAP** — dealer-positioning center line + band + envelope (novel, ours too)
- VWAP + 3 deviation bands (session/week/month/quarter/year anchors)
- CVD (sided volume delta candles)
- Volume Profile (POC + value area) + TPO (market profile: single prints, IB, naked levels)
- Drawing presets (named, synced)

## Capture additions (Sept burn + October campaign)

1. `gex/levels` hourly during RTH (1cr) — node-tier ground truth
2. `stats/daily` per symbol per day (5cr) — validation series
3. `vol/history` + `vol/derived` per symbol, weekly (cheap 2y validation pulls)
4. `vol/snapshot` spot checks before expiry of the sub
