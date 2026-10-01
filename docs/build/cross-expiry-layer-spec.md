# Cross-expiry dynamic weighting layer — implementation spec (E0.2)

Status: **fit complete on Tier-A data (2026-09-28/29/30)**. Every number below
comes from real runs of `scripts/e02_cross_expiry_fit.py`,
`scripts/e02_pair_validate.py`, `scripts/e02_basis_check.py` over the X10
captures + UW `gamma_data_v2`; artifacts live under `data/e02/`. This document
is the EXACT spec source for `backend/core/exposure.py` (card E0.3) —
implement it literally.

Scope: the MISSING layer of the Skylit value model (per
`docs/build/skylit-value-model.md` verdicts 1-4): **cross-expiry dynamic
weighting**. Within-expiry math (star = argmax |value|, net_gex =
call_gex − put_gex) is established; this spec adds the per-expiry weight that
turns per-expiry strike values into the whole-grid node value.

**Measured verdict vs the ≤10% node-value-error target: NOT MET on the current
Tier-A scope** (median node-value APE 92–100% per session-day even with fully
free per-instant weights). The gap is quantified in §5/§9: it is cell-level
dynamic state (their values embed accumulation history), not the weighting
layer's functional form. The layer below is the best implementable model from
UW-only instantaneous inputs; §9 defines what closes the remaining gap.

Clean-room status: all formulas derived from RE evidence + own fits. No
SignalForge code was read or copied. Skylit API/captures = temporary RE tool
(sub ends ~Nov 2026); the implementation below runs UW-only in production.

---

## 1. Established math (re-verified on real data this card)

| Fact | Status | Evidence |
|---|---|---|
| Node value `V(s,t) = Σ_e C(s,e,t)` (per-strike value = exact sum over expiry columns of cell values) | exact 501/501 strikes | `scripts/_e02_probe5.py` (X10 matrix 09-30 13:30 SPX) |
| `king = argmax_s \|V(s,t)\|` | 8/8 sampled captures for the aggregate rule; the single-cell variant argmax\|cell\| gives the same strike 7/8 (QQQ 09-29 15:00 differs — king follows the AGGREGATE) | `scripts/_e02_probe6.py` |
| Cell grid dense with explicit zeros (no nulls); matrix dims = strike-grid × expiry-set | 501×20 SPX | `scripts/_e02_probe7.py` |
| Range 1s `values` vector = `V(s,t)` at 1s resolution | exact match to matrix at boundary second | `scripts/_e02_probe5.py` (H2 exact) |
| Range `axes[]` = LIVE strike window (grid grows/shrinks with spot); each frame pins its `axis` id; `values` follow that axis's strike list | 286 window-files censused | `scripts/_e02_probe9_range_shapes.py` |
| Within-expiry strike selection = `net_gex = call_gex − put_gex` | their column-max strike ranks top-3 in net_gex ordering 64.4% (29/45 fresh columns, median rank #2) | `scripts/e02_pair_validate.py` → `data/e02/pair_validation.json` |
| Matrix filename = replay window start; per-symbol `asOf` 1s earlier; stale symbol-records exist | per-record rule `abs(asOf − window_start) ≤ 2 s` | card E0.1 + `is_stale_record()` in the harness |

Skylit expiry sets differ per symbol: SPX matrix captures carry monthlies /
quarterlies / leaps only (20 expiries on 2026-09-30 — NO weeklies/0DTE);
SPY/QQQ/IWM carry 0DTE + weeklies too (33/31/32). The layer must extrapolate
to expiries outside the fitted set (§6).

## 2. Value model (production = UW-only)

Given one UW `gamma_data_v2` batch at time `t` (rows per symbol):

```
g(s,e,t)  = call_gex(s,e,t) - put_gex(s,e,t)       # within-expiry, established
C(s,e,t)  = a_e(t) * g(s,e,t)                      # cell value model
V(s,t)    = Σ_e C(s,e,t)                           # node value (established, exact)
star      = argmax_(s,e) |C(s,e,t)|                # column max = star of that expiry
king      = argmax_s |V(s,t)|                      # established
```

The cross-expiry layer is the weight vector `a_e(t)` (one scalar per expiry per
symbol per UW batch). `a_e(t)` carries both cross-expiry relative weighting and
absolute scale; their private $ scale is NOT reproduced (exact-$ parity CLOSED
per verdict 2). Positive rescaling of all `a_e` leaves star/king selection
invariant — the layer's decision content is the RELATIVE column magnitudes.

## 3. Fitted layer

### 3.1 Empirical weights (fit targets, `data/e02/fit_results.json`)

Per-instant per-column least squares `a_e = <C_e, g_e>/<g_e, g_e>` over 1,691
aligned (instant, symbol) records (09-28: 25, 09-29: 788, 09-30: 878;
alignment dt median 74 s, p90 132 s, max 150 s):

- median within-column R² of `C_e ≈ a_e·g_e`: **0.089** (median spearman
  −0.016) — the cell-value basis explains little of their cells' variance;
- sign of fitted `a_e`: positive 6,530 / negative 7,940 (45.1% positive) —
  `sign(net_gex)` is NOT a reliable cell-value sign (see §6).

### 3.2 Static factor models (mandatory baselines — all FAIL)

Per-instant SSE ratio vs free fit (median over 1,691 instants):

| model | formula | sse_ratio (median) | fitted params |
|---|---|---|---|
| H0-uniform | `a_e = κ` | 1.148 | — |
| H1-dte-power | `a_e = κ·d_e^(−β)` | 1.077 | β median 0.45 (p25 0.0, p75 2.85 — unstable) |
| H2-colmag | `a_e = κ·(G_e/G_max)^γ`, `G_e = Σ_s\|g\|` | 1.098 | γ median 0.8 (p25 −0.4, p75 2.0) |

→ no static factor reproduces their column-magnitude ratios (matches verdict
4's 1.2→13.3 intraday swing finding); even H0 loses only ~15% SSE vs free
weights. Cross-expiry structure at cell level is weakly identifiable from
instantaneous chain state alone.

### 3.3 Dynamic feature model ψ (H4/H5) — the implementable layer

```
a_hat_e(t) = sgn(net_col_e(t)) * exp(θ · x_e(t))          # ψ_e(t)
x_e(t) = [1, log d_e, log G_e, net_col_sign_log_e, imb_e, doi_mig_e, com_dist_e, tod_t]
  d_e      = max(DTE_e, 0.25)                             # calendar days
  G_e      = Σ_s |g(s,e,t)|                               # gross column gex
  net_col_sign_log_e = copysign(log1p(|Σ_s g|), Σ_s g)
  imb_e    = (Σ_s ask_vol − Σ_s bid_vol) / (Σ_s ask_vol + Σ_s bid_vol + 1)
             (ask_vol = call_ask_vol + put_ask_vol, bid_vol likewise)
  doi_mig_e = Σ_s [(call_oi − call_prev_oi) + (put_oi − put_prev_oi)],
             entered as copysign(log1p(|·|), ·)
  com_dist_e = |COM_e − spot| / spot,  COM_e = Σ_s |g(s,e)|·s / G_e
  tod_t    = minutes-of-day / 1440
```

Fitted θ (OLS on log|a_e| over 14,470 (instant, expiry) samples,
`data/e02/fit_results.json:feature_model.theta`):

| term | θ |
|---|---|
| intercept | +25.345 |
| log d_e | −0.983 |
| log G_e | −0.675 |
| net_col_sign_log_e | −0.675 |
| imb_e | −0.300 |
| doi_mig_e | +0.078 |
| com_dist_e | −12.067 |
| tod_t | +1.449 |

Caveats (measured): R² on log|a_e| = **0.167**; `log G_e` and
`net_col_sign_log_e` are near-collinear (rank-deficient design — the equal
coefficients are the split of one shared weight; treat their sum as the
effective term); `sgn(net_col)` predicts `sgn(a_e)` with **45.1%** accuracy
(coin-flip level) — the cell-value sign convention remains OPEN (see §6/§9).
Leave-one-day-out end-to-end (`feature_model.leave_one_day_out`):

| held-out day | king exact | king ±tol | weight sign acc | node med APE |
|---|---|---|---|---|
| 2026-09-28 (n=25) | 40.0% | 60.0% | 0.366 | 1.000 |
| 2026-09-29 (n=788) | 27.5% | 73.9% | 0.441 | 0.998 |
| 2026-09-30 (n=878) | 22.7% | 61.2% | 0.463 | 1.000 |

(±tol = ±25 SPX points / ±5 points for SPY/QQQ/IWM.)

### 3.4 Normative layer for `exposure.py`

```
a_e(t) = λ·a_e(t_prev) + (1−λ)·ψ_e(t)        # EWMA recursion, §4
w_e(t) = a_e(t) / (Σ_e' |a_e'(t)| / E)        # scale-free display weights
V(s,t) = Σ_e a_e(t)·g(s,e,t)
```

Fitted constants: **λ_batch ≈ 0.79** per UW batch (derivation §4); θ table
above. Recursion runs at batch cadence, NOT per frame.

## 4. Dynamic state update

- Update trigger: every UW `gamma_data_v2` daemon batch. Measured batch
  cadence: median 234 s (09-28), 248 s (09-30); 185/210/318 batches per day
  (09-28/29/30) via full-day distinct walks
  (`data/e02/uw_cadence_walk.json`). The ticker-level distinct walk is
  canonical (strike×expiry walks UNDERcount — a row is written on only some
  batches). PM-note-2 conclusion: manifest counts are correct; aligned-pair
  yields can only be raised by widening tolerance (150 s adopted), not by
  discovering missed snapshots.
- Recursion state: per (symbol, expiry), keep `a_e` from the previous batch.
- λ fitted one-step-ahead on the empirical weight trajectories extracted from
  **51,485 real 1s range frames** (286 window-files, 0.2 Hz subsample, ridge
  joint LSQ with g frozen at the nearest UW batch;
  `data/e02/fit_results.json:dynamic.per_day.<day>.ewma`):
  **λ = 0.995 at the 5-s trajectory step for all 11 symbol-days with data**
  (grid corner — weights are extremely persistent at 5-s steps; one-step MSE
  drops up to 81× vs λ=0, e.g. IWM 09-29: 0.470 → 0.0058). Caveat: the grid
  ended at 0.995 — refit with an extended grid on ≥20-day data. Convert to
  batch scale for the recursion: `λ_batch = λ_5s^(cadence_s / 5)` ≈
  `0.995^(234…248/5)` ≈ **0.78–0.80** — use **λ_batch = 0.79**.
  Trajectory recursion fitted: `w_{k+1} ≈ λ·w_k + (1−λ)·mean_e` (target = next
  empirical weight; `mean_e` = per-expiry trajectory mean, standing in for ψ in
  the trajectory fit).
- Cold start: `a_e(0) = ψ_e(0)`.

## 5. Validity bounds

1. **Alignment**: UW inputs are valid for `|t − t_batch| ≤ 150 s` (half the
   batch cadence). Fitted dataset dt: median 74 s, p90 132 s.
2. **Stale Skylit-side records** (fit-time exclusion only): per-record
   `|asOf − window_start| ≤ 2 s` (`data/p0/re_inventory.json` map; 628 stale
   records over the campaign).
3. **What the model captures / misses** (basis sensitivity on 3,960 real 1s
   frames, `data/e02/basis_check.json`, joint R² median per basis):

   | within-expiry basis | R² median | p25 | p75 |
   |---|---|---|---|
   | B1 net_gex (NORMATIVE) | 0.434 | 0.085 | 0.516 |
   | B2 gross gex | 0.107 | 0.052 | 0.293 |
   | B3 cpflip (verdict-3 sign family) | 0.452 | 0.146 | 0.574 |
   | B4 oi_size | 0.332 | 0.040 | 0.507 |

   No instantaneous basis spans their 1s surface better than R²≈0.45 median
   (best windows ≈0.75). The residual is **cell-level dynamic state**
   (accumulation/unwinding history, rolling ceilings/floors — verdicts 2/4),
   NOT the weighting-layer form. B3 ≈ B1 within noise; B1 stays normative per
   established math.
4. **1s aggregate fit (empirical free weights, upper bound)**: per-frame R²
   median 0.157 / 0.329 / 0.188 (09-28/29/30) with g frozen per window
   (weights refit every frame) — what ANY weight trajectory can do on the 1s
   target given UW-only instantaneous inputs.
5. **Expiry-set extrapolation**: fitted on SPX monthlies/quarterlies/leaps
   (20) and SPY/QQQ/IWM 0DTE+weekly sets (31–33). The ψ form (DTE + column
   features) generalizes to all UW expiries, but far-end weights (2030–2031
   LEAPS) are fit only from SPX columns.

## 6. Edge cases & fallbacks (implement exactly)

1. **Expiry in UW with no matrix/fit counterpart** (production always): use
   the ψ form — it is defined for every expiry (DTE + column features from the
   UW batch itself).
2. **Column with `G_e = 0`** (no open interest rows / all gex 0): `a_e = 0`,
   column contributes nothing.
3. **Missing UW batch** (gap): hold last `a_e` for exactly one batch interval
   (≤ 2× median cadence ≈ 480 s); beyond that, mark state stale and reset to
   ψ on the next batch.
4. **Sign convention (OPEN ITEM)**: normative `sgn(a_e) = sgn(Σ_s g(s,e))`
   (accuracy measured 45.1% — do NOT trust for dollar-signed display; king
   selection uses `|V|` and is less exposed). Verdict-3's cell-level
   customer-flow flip (`sgn(ask−bid)` per side) is the leading replacement
   candidate (B3, §5.3) — re-fit on ≥20-day data before switching.
5. **Stale rows inside a batch**: drop rows whose `fetched_at` deviates > 1
   batch interval from the batch timestamp (UW-side hygiene).
6. **Zeros are real zeros** — dense grids; missing = 0 contribution (matrix
   cells carry explicit 0.0).
7. **Strike matching**: by exact strike value (UW grid 530 strikes covers the
   Skylit grids 196–522 per symbol; live windows shift intraday — never index
   positionally across sources).
8. **Scale/display**: `V` is scale-free up to one positive scalar per batch.
   Any display normalization (their rolling ceilings/floors) is OUR OWN layer —
   never present numbers as Skylit's.

## 7. Residual evidence per session-day (acceptance #4)

All from `data/e02/fit_results.json` / `residual_report.{json,csv}` (run
`python3 scripts/e02_cross_expiry_fit.py report`). "free" = per-instant
per-column weights fit to their cells; "joint" = weights fit to the node
values directly (the right estimator for node/king placement):

| session-day | n | node med APE (free) | node med APE (joint) | king exact (free) | king ±tol (free) | king exact (joint) | king ±tol (joint) | top6 (free) | top6 (joint) |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-28 | 25 | 1.011 | 1.003 | 80.0% | 100.0% | 80.0% | 80.0% | 3.48 | 2.44 |
| 2026-09-29 | 788 | 0.991 | 0.926 | 33.4% | 65.1% | 45.6% | 81.2% | 2.52 | 2.78 |
| 2026-09-30 | 878 | 0.988 | 0.967 | 31.4% | 63.1% | 46.7% | 62.8% | 2.97 | 2.56 |

APE = median `|V̂−V|/|V|` over material nodes `|V| ≥ 5%·max|V|`.

Supplementary (all real runs):
- feature-model LOTO table §3.3;
- 1s dynamic fit: 51,485 frames / 286 windows, emp R² 0.157–0.329 per day
  (§5.4);
- basis sensitivity §5.3;
- verdict-4 re-derivation: top-3 64.4% (29/45 columns) on gate-usable PAIRs
  (`data/e02/pair_validation.json`);
- PAIR freshness: 20/23 PAIR chain sets STALE (free phx endpoint, expired
  expiries present), 10/23 gate-usable via same-instant `gamma_data_v2` rows
  (`data/e02/pairs_freshness.json`).

**Verdict vs ≤10% node-value target: NOT MET on 2026-09-28/29/30**
(`residual_report.json:verdicts`). Documented per session-day as required;
§9 defines the closure path.

## 8. Implementation notes for `backend/core/exposure.py`

1. Public functions (clean-room, own code + tests):
   - `cross_expiry_weights(batch: dict, state: dict) -> dict[expiry, float]`
     — implements §3.3/§3.4/§4; `state` = `{expiry: a_e}` from previous batch.
   - `node_values(batch: dict, weights: dict) -> dict[strike, float]` —
     `V(s) = Σ_e w_e·(call_gex − put_gex)` over the batch's rows.
   - `select_nodes(values: dict) -> dict` — `king = argmax|V|`, per-expiry
     star = `argmax |w_e·g(s,e)|`, plus top-6 strikes by `|V|`.
2. Update cadence = UW batch cadence; recursion state persists per
   (symbol, expiry) across batches (§4).
3. Inputs: UW `gamma_data_v2` rows ONLY (columns used: strike, expiry_date,
   call_gex, put_gex, call_oi, put_oi, call_volume, put_volume, call_ask_vol,
   call_bid_vol, put_ask_vol, put_bid_vol, call_prev_oi, put_prev_oi,
   spot_price). No Skylit data in production.
4. θ table §3.3 and the λ grid §4 are the ONLY fitted constants — copy them
   into module-level constants with provenance comment
   (`E0.2 fit, data/e02/fit_results.json`).
5. Unit-test vectors (E0.3 `backend/tests/`):
   - `V = Σ_e C` and `king = argmax|V|` on a synthetic 2-expiry grid;
   - ψ formula on a hand-computed feature row;
   - EWMA recursion one step;
   - edge cases §6 (zero column, missing batch, sign fallback).
6. Incremental fit ingestion (E0.4 gate): `prepare` skips cached instants and
   appends new days; `fit`/`report` re-run over the growing set — one new
   Tier-A session-day accrues per RTH session (≥ 20 aligned days by
   ~2026-10-28).

## 9. What closes the remaining gap (measured, not speculative)

1. **Cell-level dynamic state** is the dominant residual (§5.3: best
   instantaneous basis R²≈0.45). Needed: history features accumulated in OUR
   store — per-(s,e) EWMA of gex/flow, node interaction counts (touched /
   rejected / delivered), rolling ceiling/floor of column magnitudes. These
   need ≥ 20 aligned days (E0.4 gate) to fit without overfit.
   → **§10 specifies this layer (card E0.5a) — implemented and measured.**
2. **Cell-value sign convention** (§3.3/§6.4): replace `sgn(net_col)` with the
   customer-flow flip family (B3) once the ≥20-day refit confirms.
3. **Scale normalization layer** (their rolling ceilings/floors): own display
   layer; fit from our own history, never from their numbers.
4. Refit cadence: re-run `prepare`/`fit`/`report` per new Tier-A day; the
   harness is incremental (`data/e02/fit_dataset/index.json`).

## 10. Cell-level dynamic state layer (E0.5a)

Normative for card E0.5a (closes §9 item 1's implementation gap). Clean-room:
derived from math + RE evidence (`docs/build/skylit-value-model.md` verdicts
2/4 doctrine: values respond to accumulation/unwinding speed, node growth/
decay history, rolling ceilings/floors). No SignalForge code read or copied.
Implemented in `backend/core/exposure.py` (state functions, §10.3); fitted
pilot-grade on 2026-09-28/29/30 (`scripts/e05a_state_fit.py` →
`data/e05a/state_fit.json`); measured before/after under `data/e05a/`.

### 10.0 Data completeness note (measured, 2026-10-01)

The §5–§9 numbers were produced on **silently truncated UW snapshots**: the
PostgREST endpoint (Supabase) caps every row response at the server-side
db-max-rows limit (measured **1000**) regardless of the requested
`limit` — a batch with **4,397 rows** (HEAD count=exact,
`2026-09-30T16:26:06+00:00` SPX) was cached as 1,000 rows, and 341/389
`data/e02/uw_cache/` files held exactly 1,000 rows. At fit time only 817 of
4,560 sampled cells at material nodes had a UW row — most "missing" (s,e)
cells were pagination loss, not grid gaps.

Fix (card E0.5a): `UWClient.q` paginates `limit/offset` until exhausted
(`scripts/e02_cross_expiry_fit.py`, `scripts/p0_parity_dataset.py`);
`scripts/e05a_refresh_uw.py` re-fetched every snapshot referenced by the fit
index (each verified equal to the live HEAD count) and rebuilt the fit-record
`uw` maps without touching the Skylit side. Pre-refresh data is backed up
(`scratch/e02_backup_pre_e05a_20261001.tar.gz`); pre-refresh metrics remain
verbatim in `data/e03/` + `data/e04/acceptance_stats.json`. All E0.5a
before/after numbers in `data/e05a/` are measured on the completed dataset.
The §3.3 θ table and §3.4 λ constants were fitted on the truncated set and
are kept unchanged in `exposure.py` (their refit is folded into the ≥20-day
refit, §10.4).

### 10.1 Why a state layer (measured residual)

Even **free** per-instant per-expiry weights fit directly to their node values
leave median node APE 0.93–1.00 (§7 "joint" columns) — no function of the
instantaneous chain alone reproduces the node-value shape. The missing content
is per-(s,e) accumulated state, held in OUR store (§9 item 1). Measured
signature on the Tier-A set (`data/e03/node_comparison.csv.gz`, 715,454
compared nodes): 63.1% of node APEs sit at 1.00 ± 0.01 (our scaled value ≈ 0
against nonzero theirs); 24.2% of compared nodes are exact-zero for us; on
material nodes the per-record LS-scaled ratio `v_hat/v_skylit` is within ±0.1
of 0 in 70.7% of cases and negative (sign disagreement) in 50.8%.

**Causal correction (§10.0):** the exact-zero nodes were NOT mostly "strikes
absent from the UW grid" — the snapshots behind the fit dataset were
truncated at the PostgREST 1000-row cap, so most (s,e) cells had no row at
fit time through pagination loss. Re-measured on the refreshed dataset
(`data/e05a/before/node_comparison.csv.gz`, 715,313 compared nodes): 47.0%
of node APEs sit at 1.00 ± 0.01; 11.6% of compared nodes are exact-zero for
us (10.9% of (Skylit strike, record) pairs have no refreshed UW row — the
true reachability bound, §10.4.5); scaled ratio `v_hat/v_skylit` within ±0.1
of 0 in 71.8% of cases and negative (sign disagreement) in 45.9%. The
shape-mismatch conclusion (the reason for this layer) is unchanged on the
surviving nodes.

### 10.2 State variables (per symbol, OUR store)

State is updated **once per distinct UW batch** at times `t_k` (batch cadence,
§4). `g(s,e,t) = call_gex − put_gex` (§2); `f(s,e,t)` = per-cell OI flow:

```
f(s,e,t) = (call_oi − call_prev_oi) + (put_oi − put_prev_oi)
```

1. **Per-cell gex EWMA** (level state):

```
q_g(s,e,t_k) = λ_k · q_g(s,e,t_{k−1}) + (1 − λ_k) · g(s,e,t_k)
λ_k          = λ_c ^ (Δt_k / cad)            # time-aware decay
Δt_k         = t_k − t_{k−1}  (clamped to ≥ 1 s),  cad = 241 s (§4)
```

   First observation of a cell initializes `q_g = g` (no artificial zero
   history). Accumulation speed is `Δg = g − q_g` (doctrine: accumulation/
   unwinding speed) — it lies in the span of `{g, q_g}` and is therefore
   included implicitly (avoiding the rank deficiency seen in §3.3).

2. **Per-cell flow EWMA** `q_f(s,e,t_k)` — identical recursion on `f`.
   Flow speed `f − q_f` again implicit in `{f, q_f}`.

3. **Rolling column ceiling/floor** of the gross column magnitude
   `G_e(t) = Σ_s |g(s,e,t)|`, within the session day (reset when the batch's
   UTC date changes; our own layer per §6.8):

```
ceil_e(t_k) = max(G_e(t_k), ceil_e(t_{k−1}))
floor_e(t_k) = min(G_e(t_k), floor_e(t_{k−1}))
ρ_e(t)      = (G_e(t) − floor_e(t)) / (ceil_e(t) − floor_e(t) + 1)   ∈ [0, 1)
```

4. **Node interaction counts** (touched / rejected / delivered) from the
   spot path at batch resolution, per node strike `s`. Node band:
   `δ_s = min(s − s_prev, s_next − s) / 2` over the sorted UW strike grid
   (one-sided at grid edges; `δ = 2.5` if the grid holds no neighbor at all).
   With `p_k = spot(t_k)`:

```
touch:   |p_k − s| ≤ δ_s                     → N_tch(s) += 1
deliver: (p_{k−1} − s) · (p_k − s) < 0       → N_del(s) += 1
reject:  |p_{k−1} − s| ≤ δ_s and |p_k − s| > δ_s and not deliver → N_rej(s) += 1
```

   Counts are cumulative across session days in our store. Scores (stationary
   under count growth):

```
d(s,t) = N_del(s,t) / (N_tch(s,t) + 1)      # delivery rate  ∈ [0, 1]
r(s,t) = N_rej(s,t) / (N_tch(s,t) + 1)      # rejection rate  ∈ [0, 1]
τ(s,t) = log(1 + N_tch(s,t))                # touch exposure  ≥ 0
```

### 10.3 State-augmented value model

Extends §2's cell model; with `β = (1, 0, …, 0)` it reduces EXACTLY to
`C = a_e · g` (the E0.3 baseline). `E(t)` = number of expiries with rows in
the batch:

```
C(s,e,t) = a_e(t) · (β₁·g + β₂·q_g + β₃·f + β₄·q_f + β₅·g·ρ_e)
           + (β₆·d(s,t) + β₇·r(s,t) + β₈·τ(s,t)) / E(t)
V(s,t)   = Σ_e C(s,e,t)                       # established summation, exact
```

Node-state terms (`d`, `r`, `τ`) are node-level and are spread uniformly over
the batch's expiries so `V = Σ_e C` holds exactly. `a_e(t)` is the §3.4 EWMA
weight unchanged (its sign convention stays the §6.4 OPEN ITEM — this layer
does not switch it). The whole model is **linear in β**, so β is fit by the
profiled least squares of §10.5. `V` remains scale-free up to one positive
scalar per batch (§6.8); all comparisons use the per-record LS scale.

Constants in `backend/core/exposure.py` (the ONLY fitted inputs of this
layer, provenance `E0.5a fit, data/e05a/state_fit.json`):

- `LAMBDA_CELL` (λ_c) — cell-state decay at one median cadence;
- `STATE_BETA` (β₁…β₈) — value-model coefficients.

### 10.4 Initialization, gaps, validity bounds

1. **Cold start**: first observation of a cell sets `q = observation`; counts
   start at 0; ceil/floor start at the first `G_e` of the session day.
2. **Gaps**: state is NEVER reset (contrast §6.3, which resets `a_e`). The
   time-aware decay `λ_c^(Δt/cad)` handles arbitrary gaps — accumulation
   state survives overnight and across missing batches; counts and
   ceil/floor survive by construction. `Δt` is clamped to ≥ 1 s.
3. **Unobserved vs zero**: a (s,e) absent from a batch is unobserved — its
   state is left untouched (§6.6 zeros are real zeros only when a row with
   zero value is present).
4. **Pilot-grade caveat (honest, §9 item 4)**: with < 20 aligned Tier-A days
   the β fit is **pilot-grade** — it can overfit day-specific structure and
   must NOT be read as validated. The fit is parameterized so the daily
   refit cadence (cron `gammasummit-e02-daily-refit`, which adds one Tier-A
   day per RTH session) re-runs `python3 scripts/e05a_state_fit.py fit` and
   refreshes `LAMBDA_CELL` / `STATE_BETA` as days accrue. The final
   "median node APE ≤ 10% over ≥ 20 session-days" bar is measured by gate
   card t_b157a485 at re-measure (~2026-10-28).
5. **Reachability bound**: strikes absent from the UW grid have no rows, no
   state, and `V(s) = 0` (§10.6). The pre-refresh 24.2% figure (§10.1)
   conflated grid reachability with pagination loss (§10.0) and is
   re-measured on the refreshed dataset (`data/e05a/refresh_uw_log.json`,
   `data/e05a/before_after_report.json`): **10.9%** of (Skylit strike,
   record) pairs have no UW row at all (11.6% of compared nodes exact-zero
   for us). No UW-only model can score on genuinely UW-absent strikes; the
   gate metric should be read with this bound in mind.
6. **Interaction-count bounds**: the spot path is observed only at batch
   resolution (~241 s median) — intra-batch touches/crossings are
   unobservable and counts undercount on sparse/gappy days. Scores
   `d`, `r` are ratios and stay bounded; `τ` grows as `log1p`.
7. **Spot requirement**: interaction counts need `spot` on both consecutive
   batches; without it the step updates no counts (features degrade to
   `d = r = τ = 0`).

### 10.5 Fit procedure (re-runnable, incremental)

Implemented in `scripts/e05a_state_fit.py fit` over the growing Tier-A set
(`data/e02/fit_dataset`, harness-order walk of §8.6):

1. Walk records sorted by (symbol, uw_ts, asOf); update state ONCE per
   distinct (symbol, uw_ts) batch; build per-record node feature matrix
   `Φ_r(s) = [Σ_e a_e·g, Σ_e a_e·q_g, Σ_e a_e·f, Σ_e a_e·q_f, Σ_e a_e·g·ρ_e,
   d, r, τ]` over the record's grid strikes and the target `v_r(s)` (their
   node values).
2. λ_c grid `{0.5, 0.7, 0.79, 0.9, 0.95, 0.98, 0.99}`; per candidate, fit β
   by power iteration on the reweighted surrogate of the **profiled** scale-
   free objective `J(β) = Σ_r cos²(v_r, Φ_r β)` (the per-record LS scale of
   §6.8 is profiled out — same scoring as the batch harness). Pick λ_c with
   best `J`; report per-λ table.
3. Report in-sample `J` for β = e₁ (baseline, = the E0.3 model shape) vs
   fitted β, plus per-record node APE after LS scale for both, and
   leave-one-day-out β stability.
4. Output `data/e05a/state_fit.json` (λ grid table, β, objective, record
   counts, commands). Copy `LAMBDA_CELL` / `STATE_BETA` into
   `backend/core/exposure.py` with provenance comment.

**Pilot result (measured 2026-10-01 on the refreshed §10.0 dataset, 3 Tier-A
days):** λ* = 0.99, β = (0.7919, −0.2581, −0.00017, −0.00011, −0.5535,
−3.5·10⁻⁶, −1.2·10⁻⁶, −1.7·10⁻⁵) — `d`/`r`/`τ` settle at ≈ 0 (3 days of spot
path cannot validate interaction counts); the weight sits on instantaneous
`g`, its deviation from the very persistent `q_g` (the accumulation-speed
form `g − q_g`, implicit in the `{g, q_g}` span), and the rolling-ceiling
modulation `g·ρ_e`. In-sample J_fitted 220.75 vs J_baseline 209.83 (+5.2%);
cos² p50 0.0847 → 0.0979. Leave-one-day-out is MIXED (held-out J vs baseline:
09-28 1.14/1.18 n=25, 09-29 110.28/135.17 n=788, 09-30 79.35/73.48 n=878) —
β shape is fold-stable but out-of-sample gain is not; concrete overfit
evidence for §10.4.4. Harness before/after
(`data/e05a/before_after_report.{json,md}`): per-record node med APE p50
1.0082 → 1.0001 (p90 1.111 → 1.033); all-node frac APE ≤ 0.10 0.51% → 0.39%;
top6 overlap 2.79 → 2.78. **The state layer does NOT close the node-error gap
in this pilot** — and king selection REGRESSES (exact 34.1% → 25.9%, ±tol
78.4% → 70.4%: reshaped values move the argmax adversely). Together with
§10.1's 45.9% post-refresh sign disagreement, the dominant residual points at
the §6.4 sign convention and the linear `a_e·h` cell form rather than at the
state features themselves; interaction counts need the ≥20-day accumulation
history before they can carry weight. Traceable numbers:
`data/e05a/before_after_report.{json,md}`, `data/e05a/state_fit.json`.

### 10.6 Edge cases (implement exactly)

1. **Zero column** (`G_e = 0`): `a_e = 0` (§6.2) — the `a_e`-weighted terms
   vanish for that expiry; the node-state terms still enter via `C`'s `E(t)`
   spread. State recursions still run (`q` decays toward 0).
2. **Missing batch / gap**: state survives, decayed by `λ_c^(Δt/cad)` on the
   next observed batch (§10.4.2). No reset.
3. **Strike outside the UW grid** (Skylit-only strikes): no rows, no state,
   `V(s) = 0` (§6.7 strike matching by exact value; never positional).
4. **Cell first seen**: `q_g = g`, `q_f = f` at that batch (§10.4.1).
5. **Stale rows inside a batch**: dropped by `normalize_batch` before any
   state update (§6.5) — state never ingests stale rows.
6. **Sign convention**: unchanged §6.4 OPEN ITEM; `d`/`r`/`τ` are unsigned
   scores and cannot flip signs. Dollar-signed display stays unreliable.
7. **Scale**: `V` scale-free up to one positive scalar per batch (§6.8);
   every comparison uses the per-record LS scale.
8. **E = 0** (empty batch): no cells, no node terms, `V = {}` (guard `E(t)` to
   ≥ 1 in the spread).

## 11. Data & reproducibility

```
python3 scripts/e02_cross_expiry_fit.py hypotheses   # -> data/e02/hypotheses.json
python3 scripts/e02_cross_expiry_fit.py --env-file <dotenv> uw-walk     # PM note 2
python3 scripts/e02_cross_expiry_fit.py pairs-check   # PAIR freshness
python3 scripts/e02_pair_validate.py                  # verdict-4 re-derivation
python3 scripts/e02_cross_expiry_fit.py --env-file <dotenv> prepare     # incremental
python3 scripts/e02_cross_expiry_fit.py fit           # all fits
python3 scripts/e02_basis_check.py                    # basis sensitivity
python3 scripts/e02_cross_expiry_fit.py report        # residual report
python3 scripts/e02_cross_expiry_fit.py verify        # PASS/FAIL
# E0.5a cell-level dynamic state layer (§10):
python3 scripts/e05a_state_fit.py fit                 # refit LAMBDA_CELL/STATE_BETA
python3 scripts/e03_batch_harness.py run --execute --out-dir data/e05a/before
python3 scripts/e03_batch_harness.py run --execute --state-layer --out-dir data/e05a/after
python3 scripts/e05a_state_fit.py report              # before/after node-error report
```

All external access read-only (X10 exFAT, Supabase SELECT/HEAD, SignalForge
data dirs read-only). Credentials via `GAMMASUMMIT_UW_URL` /
`GAMMASUMMIT_UW_SERVICE_KEY` env only (`--env-file` loads them at runtime from
a local untracked dotenv; values never printed, never persisted).

## 12. King parity: flip taxonomy + psi magnitude temper (E0.5b)

Amends §3.3/§3.4: `|ψ_e| = exp(γ·θ·x_e)` with **γ = `MAG_GAMMA` = 0.7**
(`|ψ| → |ψ|^γ`; γ = 1.0 is the pre-E0.5b model). Value-level correction for
the king = argmax|V| selection gap: our per-batch |a_e| spread (p50 11,370×)
was ~18× more skewed than their empirical free-weight spread (p50 623×);
γ = ln(623.3)/ln(11370.2) = 0.689 ≈ 0.7 matches the target's own spread
distribution. θ, λ, the EWMA recursion, the §6.4 sign OPEN ITEM, and
`V = Σ_e C` are unchanged. Measured before/after on the Tier-A days (post-
refresh, 1,691 records): king exact 34.06% → 35.42%, within-tol 78.42% →
83.32%, top6 2.79 → 2.98 (`data/e05b/before_after_report.md`).

Flip taxonomy + root causes (why QQQ/IWM exact ≈ 0-10%, why SPX misses are
always far, the per-symbol miss-side biases) and the **oracle bound** are
documented in `docs/build/e05b-king-parity.md` (referenced here as the
findings section of this spec): even hindsight per-record joint LS weights on
the established `g` basis cap king exact at **68.6%** — the ≥90% bar is
unreachable by ANY cross-expiry weight model and needs within-cell shape
fidelity (the §10 state direction), enforced by gate card t_b157a485 at
re-measure (~2026-10-28, ≥ 20 session-days). Validity: γ is pilot-grade on the
3 current Tier-A days (§10.4.4 status); `--gamma 1.0` on
`scripts/e03_batch_harness.py` / `scripts/e05b_flip_taxonomy.py` reproduces
the pre-E0.5b baseline exactly. Commands: §11 +
`python3 scripts/e05b_king_fix.py sweep --out data/e05b/sweep.json`.
