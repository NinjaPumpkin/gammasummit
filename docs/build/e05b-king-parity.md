# E0.5b king parity — flip taxonomy, root causes, corrections (P0 gap G2)

Status: **analysis + selection gap closed to the honest measured level** — king
exact 34.06% → 35.42%, within-tol 78.42% → 83.32% on the 3 Tier-A days
(2026-09-28/29/30, post-refresh dataset). The ≥90% bar is NOT met and, as
shown in §5, is **not reachable by any cross-expiry weight model of the form
`V(s) = Σ_e a_e·g(s,e)`** — the value-faithful oracle bound is 68.6% exact.
The gate bar is enforced by card t_b157a485 at re-measure (~2026-10-28, ≥20
session-days).

Every number comes from a real script run; run commands in §7. Scripts:
`scripts/e05b_flip_taxonomy.py`, `scripts/e05b_king_fix.py`,
`scripts/e05b_report.py`; artifacts under `data/e05b/`.

Provenance note: the card's "26.85% now" figure is the PRE-refresh number
(`data/e03/summary.json`, silently truncated UW snapshots, spec §10.0). After
the E0.5a pagination fix + dataset refresh the E0.3 baseline measures
**34.06%** exact / 78.42% within-tol (1,691 records; `data/e05b/before`,
identical to `data/e05a/before`). All numbers below are post-refresh.

Scoring definition (unchanged, harness `scripts/e03_batch_harness.py`): king
pred = argmax |V| over the Skylit grid strikes with tie-break to the smallest
strike; king true = the Skylit `king` nodeType (= their argmax |V| on all
1,691/1,691 records, verified); tol ±25 SPX / ±5 SPY/QQQ/IWM (spec §3.3).

## 1. Flip taxonomy

Per record, with T = true king strike, P = predicted king strike, y = Skylit
node values, o = our node values on the grid, and per-expiry contributions
`a_e·g(s,e)`:

| class | rule (priority order) |
|---|---|
| `exact` | P == T |
| `near_tie_intrinsic` | their own surface ties the pair: y(P) ≥ 0.9·y(T) |
| `near_tie_ours` | our surface ties: o(T) ≥ 0.9·o(P) |
| `sign_cancellation` | gross mass Σ_e\|a_e g\| at T ≥ at P but \|V(T)\| < \|V(P)\| |
| `expiry_mislocal` | gross mass at P > at T (cross-expiry magnitudes put the mass on the wrong strike) |
| `far_other` | residual |

Counts on the baseline walk (`data/e05b/flip_taxonomy.json`, per-record rows in
`flip_taxonomy_per_record.csv`; the taxonomy run uses `--gamma 1.0` to sit on
the pre-correction baseline):

| class | all | SPX | SPY | QQQ | IWM |
|---|---|---|---|---|---|
| exact | 576 (34.06%) | 401 (85.87%) | 87 (20.91%) | 47 (11.58%) | 41 (10.20%) |
| near_tie_intrinsic | 34 | 0 | 18 | 4 | 12 |
| near_tie_ours | 24 | 10 | 5 | 9 | 0 |
| sign_cancellation | 0 | 0 | 0 | 0 | 0 |
| expiry_mislocal | 1057 | 56 | 306 | 346 | 349 |
| far_other | 0 | 0 | 0 | 0 | 0 |

**94.8% of all misses are `expiry_mislocal`**: our cross-expiry magnitude mix
builds more gross |a_e·g| mass at the wrong strike than at the true king. Only
3.05% of misses have y(P) ≥ 0.9·y(T) (near-equal on THEIR surface) — the
"argmax ambiguity" story is a minor class, not the driver. Our own surface
ties at T in only 2.15% of misses (o(T) ≥ 0.9·o(P)); median o(T)/o(P) = 0.25,
median y(P)/y(T) = 0.25 — the value SHAPE genuinely peaks at the wrong strike.

Mechanism diagnostics over all 1,115 misses (`data/e05b/flip_taxonomy.json`):

- driver-column mismatch (our dominant expiry at P ≠ their dominant cell
  expiry at T): **69.6%**;
- node sign disagreement at T (our LS-scaled value sign vs theirs): 43.6%;
- error distance: p50 0.6 tol units, p90 5.0; 19.6% adjacent-or-same grid step;
- dominant-expiry DTE at P (ours): 0DTE in 749/1115 misses vs their driver at
  T: 1–7d in 451, 0DTE in 440 — our V is over-driven by the nearest expiry.

## 2. Per-symbol root causes

Grid structure (measured on the Skylit capture grids; corrects the card body's
"5-pt grid" assumption — pre-refresh finding):

- **SPY/QQQ/IWM grids are 1-pt dense near the money** (IWM near-money strikes
  include 283.0; 1-pt gaps dominate: 127/196 IWM gaps = 1.0), 5-pt in the
  wings. SPX is 5-pt near money. QQQ carries 78 fractional `x.78` strikes
  paired 0.22 below standard strikes — the king NEVER lands on them (0/406)
  and every true king is exactly UW-reachable (1691/1691 records), so the
  reachability bound (§10.4.5) does NOT bind the king metric.

- **SPX (85.87% exact, misses always far)**: 66 misses, err p50 12 tol units
  (300 SPX points), 0% within 1 tol; **all 66 miss BELOW the true king**
  (side bias). The Skylit SPX surface is bimodal (two walls with near-equal
  |V| far apart — y(P)/y(T) p75 = 0.46 yet distances are huge): when our
  magnitude mix over-weights a far-expiry column whose g peaks at the lower
  wall, we flip to the other mode entirely. Their king node value is negative
  on 467/467 records (SPY 404/416 negative) — a regime property of the king
  node on these days, worth re-checking at re-measure.

- **IWM (10.20% exact, 85.6% within tol)**: 361 misses, err p50 0.6 tol units
  (3 points), 83.9% within 1 tol; miss side biased BELOW (269 below / 92
  above). On the 1-pt grid, our |V| peak sits 1–3 strikes below theirs most of
  the time — a small, systematic peak-placement bias (consistent with the
  0DTE-overweight driver picture), not random argmax noise.

- **QQQ (11.58% exact, 64.8% within tol)**: 359 misses, err p50 0.6 tol,
  60.2% within 1 tol, side biased ABOVE (238 above / 121 below); highest node
  sign-disagreement rate (64.6% at T). QQQ is the weakest symbol on both exact
  and within-tol: its |V| surface is the flattest and the sign/cancellation
  structure is the least reproduced.

- **SPY (20.91% exact, 76.4% within tol)**: 329 misses, err p50 0.4 tol,
  70.2% within 1 tol, side biased ABOVE (229/100), lowest sign-disagreement
  (26.1%) — closest sibling of IWM, opposite bias direction.

The opposite side biases (IWM/SPX below vs QQQ/SPY above) track the
dominant-column picture: whichever expiry column our magnitude mix
over-weights drags the peak toward that column's own g peak, and the direction
is symbol-specific through the expiry set and spot position.

## 3. Cross-expiry magnitude + sign evidence (the mechanism behind the taxonomy)

All measured on the aligned Tier-A records (`scripts/e05b_king_fix.py` sweep
lineage + probe scripts, recorded in `data/e05b/sweep.json`):

1. **Magnitude spread.** Per-batch |a_e| spread (max/min) — ours (ψ EWMA):
   p50 **11,370×**, p90 222,507×, max 2.26M×. Theirs (empirical free
   per-column LS weights `a_free = <C_e,g_e>/<g_e,g_e>` on the same records):
   p50 **623×**, p90 3,740×. Our relative column magnitudes are ~18× more
   skewed at the median than the target's own.
2. **Rank correlation** of |a_e| ours vs |a_free| per record: p50 0.299
   (p10 −0.286) — our column-magnitude ordering is weakly informative.
3. **Sign is unpredictable.** Weighted accuracy of sign candidates vs
   sign(a_free): `sgn(net_col)` (normative §6.4) **41.4%**, always-positive
   41.4% (identical accuracy — net_col sign adds no information),
   call/put-side 46.2%, customer-flow-net 44.1%, cpflip-sum (verdict-3 family)
   **52.6%** — all coin-flip. No instantaneous column statistic predicts the
   cell-value sign; the §6.4 OPEN ITEM stays open (do not switch it on this
   evidence).

## 4. Corrections evaluated and shipped

Variant sweep (`scripts/e05b_king_fix.py sweep`, king exact / within-tol over
1,691 records):

| variant | exact | within tol |
|---|---|---|
| V0 baseline (γ=1) | 34.06% | 78.42% |
| Vmag pow0.25 | 28.98% | 74.93% |
| Vmag pow0.5 | 31.99% | 79.36% |
| **Vmag pow0.7 (shipped)** | **35.42%** | **83.32%** |
| Vmag pow0.85 | 34.89% | 81.02% |
| Vclip 13.3 / 50 / 623 / 3740 | 30.40 / 30.69 / 34.65 / 34.83% | 78.06 / 81.79 / 83.21 / 83.38% |
| Vbasis cpflip / cpflip pow0.5 | 23.77 / 34.00% | 71.56 / 81.90% |
| Vbasis oi_size / pow0.5 | 13.72 / 24.90% | 27.26 / 34.30% |
| Vsign cpflip / flow | 31.87 / 28.74% | 75.87 / 73.63% |
| ORACLE_free (per-column LS vs their cells) | 40.86% | 69.96% |
| **ORACLE_joint (per-record LS vs their node values)** | **68.60%** | 80.31% |

**Shipped correction (spec §12): psi magnitude temper.**
`|ψ_e| = exp(γ·θ·x_e)` i.e. `|ψ| → |ψ|^γ`, γ = `MAG_GAMMA` = 0.7
(`backend/core/exposure.py`). Value-level correction: the relative
cross-expiry column magnitudes feeding `V = Σ_e a_e·g` are compressed toward
the target's own measured spread distribution; the EWMA, sign convention, and
`V = Σ_e C` summation are untouched.

Derivation (RE evidence, not metric-tuned): match our median per-batch |a_e|
spread to their median free-weight spread — `623.3 = 11370.2^γ` →
γ = ln(623.3)/ln(11370.2) = **0.689 ≈ 0.7**. The sweep grid
{0, 0.25, 0.5, 0.7, 0.85} confirms 0.7 as the best grid point for king exact
(the value is therefore not fitted to the king metric; the metric only
confirms it). Day-level honesty: per-day exact 60.0/38.83/31.66% after vs
60.0/37.44/30.30% before — no day regresses; 09-28 is 25 records only.

Validity bounds: derived and measured on the 3 Tier-A days (pilot-grade, same
status as §10.4.4). γ = 1.0 reproduces the pre-E0.5b model exactly
(`--gamma 1.0` on the harness/taxonomy; `data/e05b/before_g1_check` reproduces
`data/e05b/before` byte-level metric equality). θ and λ constants unchanged —
the daily refit flow (spec §11) is unaffected.

Rejected on evidence: sign-convention switches (all candidates coin-flip,
§3), cpflip/oi_size within-cell bases (worse even with oracle weights —
`ORACLE_joint_cpflip` 60.44% < `ORACLE_joint` 68.60% on the established
`net_gex` basis, consistent with §5.3 "B3 ≈ B1 within noise"), hard spread
clips (inferior to the power temper across the grid).

## 5. Oracle bound — why < 90% is structural

`ORACLE_joint` fits the per-record per-expiry weights by least squares
DIRECTLY to their node values on the grid (hindsight targets, not shippable),
then runs the same argmax selection: **68.60% exact / 80.31% within-tol**
(SPX 98.93%, SPY 66.59%, QQQ 55.42%, IWM 48.76%; per-day 80.0/71.83/65.38%).
This is the value-faithful ceiling of the whole `a_e` model class on the
established within-cell basis `g = call_gex − put_gex`: even perfect
cross-expiry weights cannot make `Σ_e a_e·g(·,e)` peak where their `V` peaks
31% of the time, because their cells are not `a_e·g`-shaped (median
within-column R² 0.089, §3.1; post-refresh shape signature §10.1).

Consequences:

- The ≥90% king bar cannot be closed by ANY weight-layer work (fitted or
  oracle). It requires within-cell shape fidelity — the §10 dynamic-state
  layer direction (per-(s,e) accumulation state), or a richer within-cell
  basis with measured R² ≫ 0.45.
- Current gap is therefore "shape", not "selection": the selection rule
  (argmax |V|, tie-break smallest strike) is established math (§1) and the
  taxonomy shows only 3% near-tie flips where a tie-break could act.
- The honest near-term lever is the ≥20-day growth of the Tier-A set: the §10
  state fit (G1) is the shape bet; at re-measure (~2026-10-28) the gate
  decides with real days.

## 6. Before/after (honest)

`data/e05b/before_after_report.md` (generated by
`python3 scripts/e05b_report.py`) carries the full table; summary:

| metric | before (γ=1) | after (γ=0.7) | after + §10 state layer |
|---|---|---|---|
| king exact | 34.06% | 35.42% | 30.75% |
| king within tol | 78.42% | 83.32% | 77.47% |
| top6 overlap | 2.7936 | 2.9823 | 2.8658 |
| global star exact | 8.75% | 10.76% | 12.83% |

(Full per-symbol/per-day tables: `data/e05b/before_after_report.md`, generated
by `python3 scripts/e05b_report.py`.) The state layer is NOT part of the
shipped king path: its pilot β reshapes values adversely for argmax (G1
measured 34.1→25.9% pre-refresh; E0.5b confirms post-refresh it still
regresses: 35.42% → 30.75% on top of the tempered psi) — keep it off the king
path until the ≥20-day refit re-validates.

## 7. Reproducibility

```
python3 -m unittest discover -s backend/tests                      # 52 OK
python3 scripts/e05b_flip_taxonomy.py taxonomy --gamma 1.0         # baseline taxonomy -> data/e05b/
python3 scripts/e05b_king_fix.py sweep --out data/e05b/sweep.json  # variant sweep + oracles
python3 scripts/e03_batch_harness.py run --execute --gamma 1.0 --out-dir data/e05b/before_g1_check
python3 scripts/e03_batch_harness.py run --execute --out-dir data/e05b/after
python3 scripts/e03_batch_harness.py run --execute --state-layer --out-dir data/e05b/after_state
python3 scripts/e03_batch_harness.py verify --out-dir data/e05b/after
python3 scripts/e05b_report.py                                     # -> data/e05b/before_after_report.{json,md}
```

Artifacts: `data/e05b/{flip_taxonomy.json,flip_taxonomy_per_record.csv,sweep.json,before/,after/,after_state/,before_after_report.json,before_after_report.md}`.
Clean-room: all derivations from math + RE evidence; no reference-system code
read or copied (harness `verify` import-scan clean). Skylit API/captures remain
a temporary RE tool; production runs UW-only.
