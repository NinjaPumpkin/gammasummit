# Skylit per-cell value model — RE + calibration log (E0.6)

Card t_3a0b0ae0. Every number below comes from a real run; artifacts under
`data/e06/`. Commands in §7.

**Scope reframe (owner directive 2026-10-01, canonical spec
`docs/build/heatmap-formula-handoff.md`):** fitting Skylit's $-label constants
is CLOSED — proven impossible (their labels R²=0.033 from chain data; label
and color channels independent, Spearman 0.037). This log does NOT re-derive
those proofs. The live work is the **two-channel build** (label = net GEX,
color = signed GEX velocity → viridis) plus the now-OPEN **API calibration
path** (`SKYLIT_API_KEY`, temporary RE tool, sub ends ~Nov 2026; production
runs UW-only). Winning metrics: calibrated per-cell value agreement, nodeType
rank agreement, velocity color agreement.

## 1. Status scoreboard (honest, 2026-10-01)

| metric | baseline | this iteration | verdict |
|---|---|---|---|
| within-column R² (h = net_gex) | 0.089 | **0.0941** (43,380 cols, refreshed set) | reproduced, not improved |
| best single-feature within-column cos² | 0.089 | 0.0941 (nothing beats g; 39 features all ≤ 0.094) | shape bet blocked on static UW features |
| cell-level column Spearman (all UW families) | ~0 | **abs_gex +0.017 median** (best; n=5,164 cols) | per-cell label agreement ≈ 0 — consistent with proof 1 |
| node-level Spearman (API value vs our aggregates) | SPY +0.26 / SPX −0.46 / QQQ −0.51 (handoff first pull) | SPY +0.163 / SPX +0.246 / QQQ +0.174 / IWM −0.320 (best family, n=4 runs) | real but modest; sign/scale per-symbol |
| nodeType rank agreement | unmeasured | top6 overlap 6/6 SPY, 3 SPX, 3 IWM, 2 QQQ; king exact 0/4 (p50 err 5–30 pts) | rank rules replicated, ranking from our data is the gap |
| velocity color channel (their velocityPct vs our r) | unmeasured | QQQ **+0.44**, SPX +0.05, IWM +0.01, SPY −0.04 | velocity design CONFIRMED on QQQ only so far |
| king exact / node APE (card originals) | 35.42% / ~1.00 | unchanged (weight-path untouched) | $-label path closed per owner |

Corollary recorded: "very close" per-cell $ labels are NOT reachable from UW
static columns alone (proof-consistent). The open channels are (a) node-level
rank + per-symbol sign/scale calibration, (b) the velocity/color channel, (c)
accumulation features from our own history + leandata multi-year data.

## 2b. Accumulation features from leandata (judge direction, 2026-10-01)

Goal-judge re-check directed: pursue within-cell shape/accumulation features
from UW data + our own history (leandata) against the card metrics. Built
(`scripts/e06_accum_features.py`, artifacts `data/e06/accum/`):

- **options_minute interaction history** (per-(strike, expiry) cumulative
  call/put volume + trade counts over 2026-09-15→09-25, ends BEFORE the
  capture days 09-28/29/30 → no leakage): 3,612 (strike,expiry) cells
  (SPY 891 / QQQ 932 / IWM 337 / SPX 1,452).
- **strike touch history** (stock_1min SPY/QQQ/IWM + index_minute SPX spot
  paths since 2026-08-01): touch minutes / crossings / days touched over
  30d + 7d windows, node band = half nearest-neighbor gap (spec §10.2).

Measured on the 200-record probe sample (`data/e06/accum/accum_cos2.json`,
same column definition as feature_cos2):

| feature | median cos² | n cols | verdict |
|---|---|---|---|
| g (all sample cols) | 0.0909 | 5,164 | baseline |
| ovol_net / ovol_total (trailing vol history alone) | 0.0398 / 0.0331 | 503 | weak |
| tch_30d / cross_30d / days_tch (touch history alone) | 0.0118 | 5,069 | noise |
| g_x_ovol (g × trailing options-vol) | 0.1356 | 503 | selection bias, see below |
| **g on the SAME matched subset** | **0.1369** | 503 | g_x_ovol adds ~nothing |
| per-column 2-feat LS (g, ovol_total) — ORACLE bound, not shippable | 0.2183 | 503 | nested-model bound only |

Honest verdict: the apparent `g_x_ovol` lift (0.136 vs 0.091 baseline) is
**selection** — the 503 columns with options-vol history are actively-traded
columns where g alone scores 0.137. Accumulation proxies from leandata do NOT
improve within-column shape on current coverage; the 2-feature oracle bound
(0.218) is nested-model-inflated and not evidence of shippable gain. Coverage
caveat: options_minute covers 8 sessions only (2026-09-15→25) and 503/5,164
columns; touch features cover all columns and are pure noise (0.012).

**Multivariate incremental fit (`scripts/e06_cell_model.py fit`, vectorized
ALS, scale-honest objective = mean per-column cos² with per-column LS scale
profiled; LODO = fit on 2 days, score held-out day; full run 2026-10-01,
`data/e06/cell_theta.json`):** every feature group LOSES to plain g on the
MEDIAN metric.

| group | in-sample median cos² | LODO median cos² (09-28/29/30) |
|---|---|---|
| chain (F=7) | 0.064 | 0.050 / 0.044 / 0.081 |
| chain+oi_vol (F=18) | 0.065 | 0.065 / 0.065 / 0.053 |
| chain+shape (F=20) | 0.073 | 0.065 / 0.042 / 0.087 |
| chain+accum (F=15) | 0.067 | 0.037 / 0.051 / 0.057 |
| all (F=39) | 0.046 | 0.042 / 0.069 / 0.055 |
| **g baseline (for reference)** | **0.0941** | — |

Mechanism: ALS maximizes MEAN cos² (J 0.145–0.169 fitted vs the g-basis mean),
tilting toward the high-signal column tail at the expense of the median
column. V-mode eval of the fitted θ (`eval --group all` →
`data/e06/eval_models_all.json`, 1,691 records) confirms the regression
across the board — and re-pins the g baseline EXACTLY to every published
number (metric parity verified):

| metric | g baseline (reproduced) | theta_all | published pin |
|---|---|---|---|
| king exact | **0.3542** | 0.2886 | 35.42% ✓ |
| king within tol | **0.8332** | 0.5849 | 83.32% ✓ |
| top6 overlap | **2.9823** | 1.7138 | 2.9823 ✓ |
| node med APE p50 | 1.0165 | 0.9995 | ~1.00 ✓ |
| oracle_free exact | **0.4086** | 0.2886 | 40.86% ✓ |
| oracle_joint exact | **0.6860** | 0.3400 | 68.60% ✓ (bound intact) |

**Class verdict (this iteration):** no linear within-cell shape model on
same-instant UW + leandata accumulation features beats the `g` basis — on
singles, on matched subsets, on multivariate fits (in-sample AND
leave-one-day-out), or in V-mode. The 68.6% oracle bound stands. The gap is
the private per-cell state (proof-consistent), not the feature search.

## 2c. Non-linear classes: power basis BREAKS the oracle bound (2026-10-01)

Goal-judge directive "concrete further RE iteration (non-linear/shape model
classes)" → `scripts/e06_nonlinear_probe.py` + V-mode eval
(`data/e06/accum/nonlinear_probe.json`, `data/e06/eval_models_all.json`):

1. **Strike-lag alignment is clean**: column cos² of c vs g shifted ±1..±3
   grid steps ≈ 0.002 at every shift vs 0.094 at lag 0 — no grid-misalignment
   artifact; the basis sits at the right strikes.
2. **Within-column power class** `h = sign(g)·|g|^p` (per-column LS scale
   profiled — cos² scale-free): p grid {0.25…2} peaks at **p = 1.25**:
   median within-column cos² **0.0941 → 0.0972** (+3.3% rel; p=1.5 0.0967).
   First measured improvement of the shape metric on this card.
3. Per-DTE-bucket / piecewise spot-side ALS θ: every split loses to plain g
   inside its own bucket (e.g. 0DTE g 0.167 vs θ 0.130). Baseline g is
   strongest on 0DTE columns (0.167) and weakest on 8–45d (0.075).

**V-mode measured on 1,691 records (power basis
`h = max|g|_col · sign(ĝ)·|ĝ|^1.25`, ĝ = g/max|g|_col — column magnitude kept
g-scale so the psi layer is untouched):**

| metric | g baseline | power p=1.25 | delta |
|---|---|---|---|
| within-column R² (median) | 0.0941 | **0.0972** | +0.0031 |
| node med APE p50 | 1.0165 | **1.0112** | improved |
| king exact (psi path) | 35.42% | 35.13% | −0.29pt (flat) |
| king within tol | 83.32% | **83.56%** | +0.24pt |
| ORACLE_free exact | 40.86% | **42.81%** | **+1.95pt** |
| ORACLE_joint exact | 68.60% | **71.79%** | **+3.19pt — BOUND BROKEN** |
| ORACLE_joint within tol | 80.31% | **83.38%** | +3.07pt |

**Criterion 5 trigger:** the value-faithful ceiling of the model class rises
68.60% → **71.79%** — the first class to break the oracle bound. Spec for
`backend/core/exposure.py` (below); gammasummit-backend pinged via card
comment + implementation task.

### 5b. Power-basis spec for `backend/core/exposure.py` (clean-room)

Within-cell shape transform of the established `g = call_gex − put_gex`
basis (§2 cell model unchanged otherwise: `C(s,e) = a_e · h(s,e)`,
`V = Σ_e C`; MAG_GAMMA temper, θ, λ, EWMA state untouched):

```
m_e(t)   = max_s |g(s,e,t)|                     # per column (zero-safe)
h(s,e,t) = m_e · sgn(g) · |g / m_e|^p           # p = MAG_SHAPE_P = 1.25
```

- `p = 1` reduces EXACTLY to `h = g` (backward-compatible switch).
- Provenance: `data/e06/accum/nonlinear_probe.json` (p grid, median cos²),
  `data/e06/eval_models_all.json` (V-mode + oracle deltas) — pilot-grade,
  3 Tier-A days; fold the p refit into the daily refit
  (`python3 scripts/e06_cell_model.py fit/eval`) as days accrue.
- p was selected on the shape-metric grid (median cos²) and confirmed
  INDEPENDENTLY on V-mode metrics + oracle bounds — not tuned to king exact
  (which is flat, honestly noted).
- Edge cases: `m_e = 0` → `h = 0`; missing rows unchanged (§6.6/§6.7);
  sign convention §6.4 untouched (h preserves sign exactly).
- **Implementation landed 2026-10-01 (card t_1f5bc921, gammasummit-backend):**
  `backend/core/exposure.py` now carries `MAG_SHAPE_P = 1.25` +
  `shape_transform` / `shape_column` / `cell_basis`; `cell_values` /
  `node_values` compute `C = a_e · h`, `V = Σ_e C` (p = 1.0 reduces exactly to
  the g basis — bit-for-bit early return; unit tests in
  `backend/tests/test_exposure.py::TestShapeTransform`). The §10 state model
  stays on the g basis (STATE_BETA was fitted on g — compare with p = 1.0).
  `scripts/e06_cell_model.py eval` now calls `exposure.shape_column` (single
  source of truth). Real acceptance run (1,691-record walk, dry-run through
  the refactored path) reproduces the V-mode table above **exactly** — all
  metrics of `g_baseline` / `power_p125` / `theta_all` bit-identical to
  `data/e06/eval_models_all.json` (g-basis pins 35.42/83.32/2.9823/40.86/68.60
  intact; power oracle_joint 71.79% confirmed). 88/88 unit tests green, ruff
  clean. Pilot-grade caveat unchanged; p refit folds into the daily refit as
  days accrue past 20 (gate card t_b157a485).

## 2. RE findings from the UI captures (X10, read-only)

Source: `/Volumes/X10 Pro/gammasummit/t3/re/raw/matrix/gamma/` (per-cell
matrices at capture instants; 5,187 captures, 20 session-days).

1. **Their per-cell values are near-static intraday.** Same-grid cell values
   across consecutive matrix captures (2026-09-24, 1-min cadence, SPX):
   corr(c_t, c_t+1min) = **0.993**, corr vs 13:30 capture stays **0.960 after
   5 hours**, same-sign 97.5–99.9%, median |Δ|/|c| ≤ 5% over 6.5 h. Sampled
   cell (8000 / 2026-12-18): −1.02e7 → −1.67e7 in the first 20 min, then slow
   drift. Their label channel is a slow state, not an instantaneous chain
   function — consistent with proof 1 (private positioning feed rescaling).
2. **Noise floor at far strikes.** Where our net_gex ≈ 0.0x–0.5 their cells
   still carry ±1e5–1e6 with mixed signs across adjacent strikes; near money
   c/g ratios swing 0.013–0.14. No constant scale; sign not smooth in strike.
3. **Independent corroboration of the unfittability (refreshed data):** the
   E0.6 feature sweep (`scripts/e06_cell_model.py features`, 1,691 records /
   4,981,926 cells / 43,380 scored columns) evaluates 39 same-instant +
   accumulation features (chain, OI/vol/ask-bid, strike-relative interactions,
   per-(s,e) EWMAs + cumulative volume/imbalance/OI-migration from our own
   uw_cache walk): best median within-column cos² = 0.0941 (tied: g and its
   column normalization), accumulation EWMAs 0.090–0.093, everything else
   lower; median column Spearman 0.001. `data/e06/feature_cos2.json`. The
   mid-run ALS multivariate fit was deliberately ABORTED after the owner
   reframe (that is the closed label-constant-fitting class).

## 3. API calibration (the open path)

Harness: `scripts/e06_api_calibrate.py` (clean-room own client; Skylit
`GET /v1/heatmap?symbols=…`, `Authorization: Bearer <SKYLIT_API_KEY>`,
1 credit/pull; UW PostgREST creds loaded read-only from the runtime env-file).
Pulls saved verbatim: `data/e06/calibration/runs/pull_*.json` (+ `index.jsonl`);
aggregates `data/e06/calibration/analysis.json`. 4 pulls run 2026-10-01
(17:19–17:26 UTC; same UW batch 17:16:39 — effective UW-side n=1; pulls
accumulate with cadence). Continuous cadence: cron `e06-skylit-calibration-pull`
(job c52c0ca2b47d, `*/30 13-20 * * 1-5` UTC, no_agent script
`e06_calib_tick.sh`, 1 credit/tick, deliver=local). NOTE 2026-10-01: the
Hermes gateway was not running at creation — the job is saved but inert until
`hermes gateway start`.

### 3.1 Per-symbol sign/scale families (n=4 runs, best family per symbol)

Their `/v1/heatmap` value aggregates only the 5 expiries listed in the
response (measured: restricting our aggregates to those expiries lifts
Spearman on every symbol — SPY 0.12→0.17, SPX 0.15→0.18, QQQ 0.11→0.16).

| symbol | best family | Spearman | scale ratio (median their/ours) | sign note |
|---|---|---|---|---|
| SPY | net_gex_5exp | +0.163 | 0.288 | call−put, positive |
| SPX | abs_gex_5exp | +0.246 | 0.0041 | UNSIGNED gamma tops — their sign is a separate channel |
| QQQ | abs_gex_5exp | +0.174 | 0.159 | unsigned gamma tops |
| IWM | call_gex | **−0.320** | 0.568 | sign FLIPS (put−call = +0.19) |

- **Sign conventions differ per symbol** (IWM inverted vs SPY; SPX/QQQ best
  on unsigned |gamma|). This matches the handoff's first-pull observation
  (SPX/QQQ negative correlations) — the family search resolves the sign, the
  residual is magnitude.
- **Scale ratios are unstable across instants and wildly different per symbol**
  (0.004 … 0.57) — proof-1's private rescaler seen from the other side. Treat
  per-symbol scale as a DISPLAY constant refit continuously, never as a model
  target. Full family table (12 families × 4 symbols): `analysis.json`.

### 3.2 nodeType tiers (rank-based, replicated)

Measured counts on pull 1 (`analysis.json` runs[0]): king = 1 always; pika =
exactly 3; barney = exactly 3; gatekeeper = SPX 8 / SPY 4 / IWM 3 / QQQ 0
(the 3–10 band, symbol- and instant-dependent). Rank order by median |value|
normal < barney < pika < gatekeeper < king holds on SPY/SPX/QQQ; **IWM run 1
inverts barney/pika medians** (12.2M vs 6.0M) — the tier order rule needs more
pulls before it is normative for IWM.

Rank-match of our own ranking (best family, run 1): king exact 0/4 (SPY 760
vs 765 = 5 pts off; QQQ 730/740; SPX 7500/7850; IWM 282/283 = 1 pt off); top6
overlap 6/6 SPY, 3/6 SPX, 3/6 IWM, 2/6 QQQ; our top6 captures 3–6 of their
non-normal nodes (7–15 per symbol). **Their rank structure is replicable;
which strike fills which tier is the open gap** (same "shape" gap as the card,
now measurable per pull).

### 3.3 Velocity channel (Channel 2 of the two-channel spec)

Their `velocityPct` (per strike) vs our velocity `r = Δcell_$ / max|Δcell_$|`
(Δ over consecutive UW batches, restricted net_gex): Spearman **QQQ +0.440**,
SPX +0.049, IWM −0.004, SPY −0.036 (run 1; run 2 identical UW batch). QQQ is
a clear positive signal — the velocity design is right; the weak symbols may
need their exact Δ window (our Δ = one ~4-min batch) or leandata-grade flow
derivatives. `gamma_velocity` table calibration + `/v1/historical` (5 cr,
1 s frames) window-shape RE are the next probes.

## 4. Two-channel build status

- **Channel 1 (label)** = net GEX per cell — `backend/core/exposure.py`
  (existing, untouched this iteration).
- **Channel 2 (color)** = signed GEX velocity → viridis mapping constants are
  canonical in `docs/build/heatmap-formula-handoff.md` (t(0)=0.41, t(+1)=
  #fde725, t(−1)=#440154, exponents 1.5/0.85, ink flip at cutoff 128, star
  |r| ≥ 0.8). Frontend parity (E4) consumes that file incl. the JS reference.
  E0.6's job is calibration of r vs their velocityPct (§3.3) — in progress.
- Per-symbol display constants (sign + scale for label display): §3.1 table,
  refit continuously from cheap pulls.

## 5. Data notes

- Tier-A set: 1,691 records (2026-09-28/29/30), refreshed UW (E0.5a
  pagination fix). Daily refit cron (fd1a1660c172, 14:30) keeps adding days;
  `scripts/e06_cell_model.py features` and
  `scripts/e06_api_calibrate.py analyze` are deterministic re-runs over the
  accumulated data (incremental by re-run, no fitted state to corrupt).
- `leandata` (`/Volumes/X10 Pro/leandata/`, 2020→2026, read-only; inventory
  card t_a6315bfb → `docs/data/leandata-inventory.md`): future feature source
  for velocity/accumulation (options_minute 54 tickers, stock_1min,
  index_cboe_close for overnight-gap baselines). Not yet consumed.
- Calibration pulls should accumulate at a cheap cadence (1 cr each; the
  analyzer aggregates runs automatically). `/v1/historical` (5 cr) reserved
  for targeted window-shape RE.

## 6. Next steps (ordered)

1. Accumulate `/v1/heatmap` pulls across sessions (cadence), re-run `analyze`
   → stabilize per-symbol sign/scale + tier-order rules (IWM barney/pika).
2. Velocity window-shape RE via `/v1/historical` on 1–2 targeted windows
   (QQQ first — ρ 0.44 anchor): find their Δ window vs our batch Δ; then
   calibrate r-channel constants against `gamma_velocity` + leandata flow.
3. Replicate node tier ranking from our calibrated values (rank-match metric
   per pull); track king exact / top6 across pulls in `analysis.json`.
4. Feed the calibrated display constants to the E4 frontend card via
   `heatmap-formula-handoff.md` (already the canonical pointer).

## 7. Reproduction

```
python3 scripts/e06_cell_model.py features --execute      # -> data/e06/feature_cos2.json
python3 scripts/e06_api_calibrate.py pull --execute       # 1 credit -> data/e06/calibration/runs/
python3 scripts/e06_api_calibrate.py analyze --execute    # -> data/e06/calibration/analysis.json
python3 scripts/e06_cell_model.py verify                  # clean-room + artifact check
```

Clean-room: all derivations from math + RE evidence + our own API client code;
no reference-system code read or copied. Skylit API = temporary RE tool;
production runs UW-only. Secrets: `SKYLIT_API_KEY` / `GAMMASUMMIT_*` env only,
never in git/chat/artifacts.
