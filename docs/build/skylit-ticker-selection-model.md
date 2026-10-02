# Skylit ticker-selection model — what makes a ticker tradable

E0.7 RE deliverable · 2026-10-02 · clean-room derivation, UW-PHX-implementable.

**Claim discipline:** this doc claims only what evidence supports. It does NOT
claim to know Skylit's internal model. Every rule carries a provenance tag and
provenance is never blended:

- `[academy]` — quoted from Skylit Academy curriculum (owner's Heatseeker sub,
  acct lapcheong; captured 2026-10-02 → `docs/re/skylit-academy/`, 26 courses,
  digests `DIGEST-heatseeker-ticker-selection.md` / `DIGEST-flowseeker-ticker-selection.md`)
- `[observed]` — observed product behavior: live web app surfaces + public API
  docs/defaults + real API responses (`data/e07/skylit_api/`, `data/e07/observations.jsonl`)
- `[derived]` — our inference/hypothesis, computable from UW PHX, tagged as such

Evidence inventory: `docs/re/skylit-academy/` (curriculum), `docs/re/skylit-docs/`
(public API/product docs), `data/e07/` (observations.jsonl, raw captures,
skylit_api pulls, uw_features_*, validation_report.*).

---

## 1. The honest headline

Skylit does not run one "pick a ticker" model. Its surfaces encode a **two-stage
attention machine**:

1. **Premium-led rank** — "what is the biggest dollar activity today" (`/v1/underlying`
   is literally ordered by total premium; the Flow Scanner default sort is
   premium) `[observed]`. Our UW-only premium ranking reproduces Skylit's top-25
   premium tickers at **P@25 = 0.92–1.00** over 3 replayed days `[derived+observed]`.
2. **Unusualness overlays as separate surfaces** — RVOL anomalies, OI changes,
   repeat hits, opening orders — each a *parallel* list, never merged into the
   premium rank `[observed]`. Academy doctrine agrees: *"Premium rank and Vol/OI
   measure how unusual a print is, not which way it points."*
   (flowseeker-05 §7) `[academy]`.

A single blended scalar **degrades** against every ground truth we hold (measured,
§5) `[derived]`. The implementable model is therefore: **gate → premium rank →
unusualness overlays**, not "one score".

## 2. Stage 0 — the tradability gate (which tickers exist at all)

| # | Rule | Prov | Evidence |
|---|---|---|---|
| G1 | Ticker must have traded options that day ("every ticker that traded options on the requested date" = the discovery universe) | [observed] | API `GET /v1/underlying` doc; UW `ticker_universe` (5,902 tickers, `has_chains`, tier by OI rank) |
| G2 | Contract liquidity floor: baseline avg volume ≥ **100** contracts (product default `min_avg_volume`) | [observed] | `GET /v1/contract/unusual-volume` defaults |
| G3 | Nothing qualifies → empty result; thresholds are never loosened ("An empty scan is a real answer") | [academy] | talon-prompt-guide §7 |
| G4 | Dark-pool block floor: notional ≥ **$1,000,000** (product default; "blocks-by-default rule") | [academy]+[observed] | dark-pool-prints §3; `GET /v1/dark-pool/trades` default `min_notional=1e6` |
| G5 | Cancelled prints never count | [academy] | flowseeker-02 §2 ("a CANCELLED badge. A cancelled print did not happen") |
| G6 | Index/issuer split: index products (SPX/SPY/QQQ/VIX family) have no earnings/peers; event logic applies to single names only | [academy] | talon-prompt-guide §7 |
| G7 | Dark-pool/Talon context window = fixed **5 sessions**; DP overlay lookbacks ∈ {30,45,90,180}d, top-N ∈ {1,2,3,5} | [academy] | dark-pool-prints §4, talon §6 |

No IV floor, spread floor, or market-cap floor appears anywhere in curriculum or
product defaults `[academy gap / observed gap]`. Tempest does flag thin chains
(`quality`/`thin`) `[observed]` — a liquidity *warning*, not a universe filter.

## 3. Stage 1 — attention rank (why a ticker gets looked at)

Ranked list semantics, all `[observed]` unless noted:

| Surface | Sort key | Doc/default |
|---|---|---|
| `/v1/underlying` | total premium desc | "ordered by total premium (descending) … repopulating the universe of tradable tickers" |
| `/v1/underlying/top/daily` | `order_by` ∈ {premium (default), volume, net_premium, call_put_ratio} | API doc |
| `/v1/contract/top/daily` (Flow Scanner) | premium default; also volume/oi/iv; 3 cr market-wide | API doc + observed web scanner default sort = premium |
| `/v1/market/overview` | "top 10 tickers by total premium"; premium RVOL vs **trailing 20-day** same-time-of-day baseline | API doc |
| Flow Compass panels | Aggressive Bets = "aggressively-bought, unusual **relative** flow"; Large Opening Orders = "biggest fresh **size-over-OI** bets"; Repetitive Hits = "repeated equal-clip ask-side accumulation" | observed panel titles |

Academy reinforcement `[academy]`:

- *"Size rewards cheap contracts traded in bulk; premium measures dollars actually
  committed — so lead with premium."* (flowseeker-02 §3)
- *"A $500K minimum shows large prints — not funds."* (premium floor ≠ actor filter, flowseeker-05 §5)
- *"Ten thousand contracts at $0.05 is $50,000 — often less than a few hundred
  contracts nearer the money."* (flowseeker-02 §7)
- Attention priority is a **2×2**: direction-strength × unusualness —
  *(strong, high) looked at first, (near-zero, low) last* (flowseeker-05 §2).
- *"A large print earns investigation. It does not identify a profitable trade."*
  (all flowseeker courses, endnote) — rank ≠ trade qualification.

## 4. Stage 2 — unusualness overlays (parallel lists, per contract)

Product-surfaced anomaly screens `[observed]` (API defaults = the quantified
thresholds; the UI panels are the same ideas):

| Overlay | Quantified trigger (product defaults) | UW-PHX computable from |
|---|---|---|
| RVOL anomaly (`/v1/contract/unusual-volume`) | `min_rvol=2` vs `avg_period=10d` baseline, `min_avg_volume=100`; sortable rvol/volume/premium/vol_oi/oi_change | per-contract daily volume history (build; see §7 gap), `uw_hot_chains.vol_pctile_15d` |
| OI anomaly (`/v1/contract/unusual-oi`) | `min_oi_change=500` OR `min_oi_change_pct=25`; `direction` opening/closing | `oi_movers` (61.5k rows, buckets), `top_chains.prev_oi`, `uw_hot_chains.days_of_oi_increases` |
| Vol>OI / Size>OI | "contracts where today's volume is above open interest" / single prints bigger than OI `[academy]` (flowseeker-04 §3) | `top_chains` volume vs open_interest |
| Accumulation score 0–100 + `strong_accumulation→low_activity` | `/v1/vol-oi/{ticker}` (Vol/OI bucketed by type × moneyness band) | `flow_scores`, chain sums via `gamma_data_v2`/`top_chains` |
| Sweep share / aggression | sweeps = same contract within **1 second** `[academy]`; `sweepVolume`, `bidPct/askPct`, `aggressionRatio` fields `[observed]` | `flow_scores.is_sweep`, `top_chains.ask_volume/bid_volume`, `uw_hot_chains.sweep_volume` |
| Baseline "is that unusual **for this name**" | premium percentile vs the ticker's own **trailing 20 days** `[academy]` (flowseeker-05 §2); trailing week / daily average `[academy]` (talon §5) | 20-day per-ticker premium series from `top_chains` (implemented) |
| Fresh-size bets | "size-over-OI", OI stale-by-one-session caveat `[academy]` (flowseeker-04 §2) | `prev_oi` deltas |

Directional scoring doctrine (not selection, but shapes the ranking fields)
`[academy]`+`[observed]`: Flow Score ∈ [−100,+100] from side, sweeps, moneyness,
DTE, premium, IV; scores "sort; they aren't probabilities"; Sweep = urgency
weight; side alone never sets polarity.

## 5. Candidate scores — measured against observed picks

Replay: 3 historical days (2026-09-29/30, 10-01) where both UW `top_chains`
(610 tickers/day) and Skylit daily rollups exist. UW features: `scripts/e07_uw_features.py`
(only UW PHX tables: top_chains, flow_scores, iv_history, uw_earnings_upcoming).
Skylit ground truth: `/v1/underlying/top/daily` (A: top-100 premium tickers),
`/v1/contract/unusual-volume`+`/v1/contract/unusual-oi` (B: 49–59 unusual
tickers/day), C = A∩top-25 ∪ B. Full numbers: `data/e07/validation_report.md`,
variant sweep `scripts/_e07_variant_probe.py`.

| Score | vs A @25 | vs B @25 | vs C @25 | verdict |
|---|---|---|---|---|
| **premium-only percentile** | **P 0.92–1.00** | **P 0.44–0.64** | **P 0.68–0.76** | best on every truth set |
| score_v0 (8-feature mean) | P 0.56–0.80 | P 0.36–0.48 | P 0.48–0.60 | dilutes premium |
| 50/50 premium×unusual blend | P 0.60–0.84 | P 0.32–0.56 | P 0.52–0.56 | dilutes premium |
| unusualness-only | P 0.20–0.28 | P 0.16–0.24 | P 0.20–0.24 | weak on current UW data |

Spearman(UW premium proxy, Skylit total premium) = **0.61–0.79** (n=76–83 common
tickers; the residual gap is dominated by `top_chains` truncation — only top-15
contracts/ticker/sort — and by Skylit-only index products like SPXW/NDX/XSP).
`[derived, measured]`

**Therefore (candidate model v1):**

```
gate(G1..G7)  ->  rank by day total premium (dollar-pinned, dedup contracts)
              ->  emit PARALLEL overlay lists (rvol_anomaly, oi_anomaly,
                  vol_gt_oi, sweep_heavy, repeat_hits), each with its own
                  quantified threshold from §4
              ->  never blend overlays into the premium rank
```

## 6. Backtestable hypotheses (for E0.8+; not yet validated)

| H | Hypothesis | Test | Tag |
|---|---|---|---|
| H1 | Contract-level RVOL (`min_rvol=2`, 10d) + OI-change (≥500 or ≥25%) on per-contract daily history recovers Skylit's unusual sets at P@50 ≥ 0.5 | needs per-contract day history (leandata `options_eod` as RE reference; UW accumulation going forward) | [derived] |
| H2 | `premium percentile vs own trailing 20d` ranks "surprising" names above raw premium within the same day | compare vs B per day | [academy]+[derived] |
| H3 | Ask-side share > 0.6 + sweep share > 0.3 on a ticker's top contracts predicts appearance in "Aggressive Bets" (needs Compass panel capture to label) | capture Compass rows when stream access works | [academy]+[derived] |
| H4 | Event proximity (earnings ≤ 5 sessions) concentrates unusual-oi hits in single names (UW `uw_earnings_upcoming.expected_move`, `rv_1d_last_12q`) | overlap stats on B per day | [derived] |
| H5 | GEX concentration (peakAbsMean-analog from `/v1/stats/daily` semantics: mean of daily max\|cell\|) ranks Heatseeker attention for singles the same way it does for indices | UW `gamma_data_v2` cells vs `uw_hot_chains` membership | [observed]+[derived] |
| H6 | Regime gate: in negative-gamma days the bar rises ("greater need for cross-index confirmation") → attention lists tilt defensive (TLT/HYG/XLF heavy on 09-29/30 unusual-oi — already visible) | classify days by GEX sign, compare B composition | [academy]+[derived] |

## 7. Data gaps on the UW side (honest)

1. **Per-contract daily history is missing** — `top_chains` keeps only top-15
   contracts/ticker/day (2 sorts), so day-premium is a truncated proxy and
   contract RVOL cannot be computed. Remediation: persist daily contract-level
   aggregates (volume, premium, oi, prev_oi, bid/ask split) for all captured
   tickers — the exact `ContractStats`/`UnderlyingStats` row shapes Skylit's own
   rollups use `[observed]`.
2. `flow_scores` covers only alert-driven names (34 tickers/day), 2026-09-11→09-30.
   Not a universe feed.
3. `ticker_metrics` / `options_screener_snapshots` are stale (max 2026-06-03 /
   2026-05-25) — known vendor-freeze class incident; do not build features on
   them until freshness-verdict alarms exist.
4. Skylit-only names (SPXW/NDX/XSP/weeklies) vs UW universe mismatch (≈20 of
   Skylit top-100 not in UW 610) — needs symbol-mapping layer.
5. Flow Compass panels (Aggressive Bets / Large Opening Orders / Repetitive
   Hits) never populated in our browser session (stream-gated) — H3 labels
   pending. Recorded as negative observation in `observations.jsonl`.

## 8. Session/timing context of the observations `[observed]`

- Scanner snapshot 2026-10-02 ~12:30 ET mid-session: top-100 rows = 12 distinct
  tickers, dominated SPX/SPXW (64), SPY/QQQ (20), then mega-caps (TSLA, NVDA,
  META, AMD, MU, STX) — one snapshot only, logged in `observations.jsonl`.
- Skylit's own daily rollups for 09-29/30: unusual-oi lists tilt ETF/defensive
  (TLT 17, HYG 7, EWZ 5, KRE/XLF) while premium tops stay index + MU earnings
  (MU report_date 2026-09-30 postmarket — event day) — consistent with H4/H6.
- Academy session doctrine: pre-open levels/maps, session "flow at planned
  levels", after-close Scanner totals, next-morning OI-by-date, weekly review
  incl. skips `[academy]` (flowseeker-10 §4).

## 9. What this model is NOT

- Not Skylit's internal scorer (weights of Flow Score/FlowBonus/Composite are
  undisclosed `[observed]` gap; FlowBonus "isn't a column on the Live Feed").
- Not a trade-qualification system — that stack (chart structure → map → flow →
  R:R ≥ 3:1 → Trinity 2/3 min) is documented separately in the digests and is
  about *taking* trades, not *choosing tickers to look at*.
- Not validated beyond 3 replay days + 1 live snapshot; every number above
  carries its sample size.

## 10. Provenance appendix — key quotes (short)

- "the universe of tradable tickers" — `/v1/underlying` API doc `[observed]`
- "Top 10 tickers by total premium" — `/v1/market/overview` `[observed]`
- "min_rvol … (default 2) / avg_period … (default 10d) / min_avg_volume … (default 100)" — unusual-volume API `[observed]`
- "min_oi_change … (default 500) / min_oi_change_pct … (default 25)" — unusual-oi API `[observed]`
- "the premium leaders — each carrying volume, open interest, vol/OI ratio, sweep share, and the buy/sell split" — talon-prompt-guide §5 `[academy]`
- "a $1M print is routine on SPY and rare on a quiet name" — flowseeker-05 §2 `[academy]`
- "Volume > OI — contracts where today's volume is above open interest" — flowseeker-04 §3 `[academy]`
- "Scan baskets are curated. Talon won't scan your personal watchlist and won't assemble a ticker list of its own." — talon-prompt-guide §9 `[academy]`
