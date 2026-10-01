# P0 acceptance report — calc-parity gate (E0.4)

**P0 NOT SIGNED (reasons + gaps)**

- Report generated: 2026-10-01 (evidence runs 2026-10-01T08:09–08:12Z)
- Gate definition: `docs/build/README.md` § "P0 gate (before any product build)" —
  clean-room `backend/core/exposure.py` (zero SignalForge imports), **king exact
  ≥ 90% over ≥ 20 session-days** vs Skylit nodes, **node values within ≤ 10%
  error**.
- Evidence chain (every number below traceable to these saved runs):

```bash
python3 scripts/e03_batch_harness.py run --execute   # 2026-10-01T08:09Z rerun -> data/e03/
python3 scripts/e03_batch_harness.py verify          # VERIFY: PASS (exit 0)
python3 scripts/e04_acceptance_report.py --check     # -> data/e04/acceptance_stats.json (hash check: OK)
python3 -m unittest discover -s backend/tests        # 23 tests OK (E0.3, re-verified in E0.3 handoff)
```

Machine-readable source of every table: `data/e04/acceptance_stats.json`
(script `scripts/e04_acceptance_report.py`, stdlib-only, read-only). Underlying
run outputs: `data/e03/{summary.json, per_record.csv, star_comparison.csv,
node_comparison.csv.gz}`.

## 1. Gate matrix

| # | Criterion | Bar | Measured (2026-10-01) | Met |
|---|---|---|---|---|
| 1 | Parity dataset session-days | ≥ 20 Tier-A aligned days | **3** (2026-09-28/29/30; 1,691 records) | **NO** |
| 2 | King exact match | ≥ 90% over ≥ 20 session-days | **26.85%** over 3 days | **NO** |
| 3 | Node value error | ≤ 10% | **median node APE 1.0013** (~100% error; 0/1,691 records below 0.50) | **NO** |
| 4 | Clean-room implementation | zero SignalForge imports/tokens | verify PASS: import-scan hits NONE, non-stdlib imports NONE (stdlib only: `__future__`, `datetime`, `math`, `typing`) | YES |

Verdict logic: 3 of 4 gate criteria NOT met → **P0 NOT SIGNED**. Product build
(E1+) stays gated. The E0.3 ψ/EWMA weighting layer is correct as specified
(`docs/build/cross-expiry-layer-spec.md` §3.3/§3.4) and reproduces E0.2's
independent fit end-to-end — the residual is the §9 cell-level dynamic state,
not the weighting layer.

## 2. Per-day table (Tier-A aligned records)

Source: `data/e03/summary.json` `per_day` (mirrored in
`data/e04/acceptance_stats.json`). Exact-match % = king exact rate
(king = argmax |V| on the Skylit grid; exact = predicted strike == Skylit
king strike).

| Day | Records | King exact | King ±tol | Node med APE (median) | Star exact | Star top-3 | Top-6 overlap (mean) | Global star exact |
|---|---|---|---|---|---|---|---|---|
| 2026-09-28 | 25 | 40.00% | 60.00% | 1.0122 | 20.47% | 43.72% | 2.56 | 0.00% |
| 2026-09-29 | 788 | 25.00% | 68.78% | 1.0004 | 21.80% | 34.81% | 2.53 | 10.03% |
| 2026-09-30 | 878 | 28.13% | 70.27% | 1.0014 | 16.48% | 35.64% | 2.53 | 6.26% |
| **ALL** | **1,691** | **26.85%** | **69.43%** | **1.0013** | **19.06%** | **35.36%** | **2.53** | **7.92%** |

Notes (normative definitions, `scripts/e03_batch_harness.py`):
- `king_within_tol` = |pred − true| ≤ tol, tol ±25 SPX points / ±5 SPY/QQQ/IWM
  (spec §3.3). Includes exact matches.
- `node_med_ape` = per-record median node APE over material nodes
  (|V| ≥ 5% of max |V|) after the per-record least-squares scale scalar
  (scale-free model, spec §6.8).
- Star metrics are context (RE evidence: Skylit "top-3 75%" comparable metric),
  not gate criteria.

## 3. King exact per symbol and per day×symbol

Source: `data/e04/acceptance_stats.json` `per_symbol_king`,
`day_symbol_king_exact` (computed from `data/e03/per_record.csv`).

| Symbol | Records | King exact | King ±tol | Exact rate | ±tol rate | Misses within tol |
|---|---|---|---|---|---|---|
| SPX | 467 | 351 | 351 | 75.16% | 75.16% | 0.0% (no miss within ±25 — bimodal) |
| SPY | 416 | 99 | 302 | 23.80% | 72.60% | 64.0% of misses |
| QQQ | 406 | 1 | 121 | 0.25% | 29.80% | 29.6% of misses |
| IWM | 402 | 3 | 400 | 0.75% | 99.50% | 99.5% of misses (adjacent-or-same strike on the 5-pt grid) |

| Day × Symbol | n | King exact |
|---|---|---|
| 2026-09-28 SPX | 15 | 66.7% |
| 2026-09-28 SPY | 5 | 0.0% |
| 2026-09-28 IWM | 5 | 0.0% |
| 2026-09-29 SPX | 216 | 67.1% |
| 2026-09-29 SPY | 194 | 25.3% |
| 2026-09-29 QQQ | 189 | 0.0% |
| 2026-09-29 IWM | 189 | 1.6% |
| 2026-09-30 SPX | 236 | 83.1% |
| 2026-09-30 SPY | 217 | 23.0% |
| 2026-09-30 QQQ | 217 | 0.5% |
| 2026-09-30 IWM | 208 | 0.0% |

(QQQ has no Tier-A records on 2026-09-28.) The aggregate 26.85% is carried by
SPX; QQQ/IWM exact ≈ 0% are the dominant drag — see gap G2.

## 4. Error distribution

Source: `data/e04/acceptance_stats.json` `error_distribution`.

### 4.1 King strike error (|pred − true| in tolerance units; 1.0 = ±25 SPX / ±5 others)

| Bucket (mutually exclusive) | Records | Fraction | Cumulative |
|---|---|---|---|
| exact (0) | 454 | 26.85% | 26.85% |
| (0, 1] | 720 | 42.58% | 69.43% |
| (1, 2] | 102 | 6.03% | 75.46% |
| (2, 5] | 202 | 11.95% | 87.40% |
| (5, 20] | 176 | 10.41% | 97.81% |
| > 20 | 37 | 2.19% | 100.00% |

Quantiles (tol units): min 0, p25 0, **p50 0.6**, p75 2.0, p90 9.2, p95 17.6,
max 56.0, mean 2.90 (n = 1,691).

### 4.2 Node value error (APE = |V_ours_scaled − V_skylit| / |V_skylit|)

Per-record median node APE (the gate metric), n = 1,691 records:

| min | p10 | p25 | p50 | p75 | p90 | p95 | max | mean |
|---|---|---|---|---|---|---|---|---|
| 0.8403 | 0.9909 | 0.9986 | **1.0013** | 1.0161 | 1.0653 | 1.0855 | 1.1899 | 1.0128 |

- Records with median node APE ≤ 0.10 (gate bar): **0 / 1,691**.
- Records with median node APE ≤ 0.50: **0 / 1,691** (min is 0.8403).
- Records ≤ 1.0: 648 (38.3%); (1.0, 2.0]: 1,043 (61.7%).
- Per-record p90 node APE: p50 1.1073, p90 1.6942, max 3.4920.

All compared nodes (715,454 rows in `node_comparison.csv.gz`; 715,313 with
defined APE, 141 undefined/empty):

| Node APE (cumulative) | Nodes | Fraction |
|---|---|---|
| ≤ 0.10 (gate bar) | 3,009 | 0.42% |
| ≤ 0.25 | 7,776 | 1.09% |
| ≤ 0.50 | 17,572 | 2.46% |
| ≤ 1.00 | 453,475 | 63.4% |
| ≤ 2.00 | 692,194 | 96.8% |
| > 2.00 | 23,119 | 3.2% |

Signature of the gap: p50 of the all-node APE distribution sits at exactly
1.00 — most nodes compare `v_ours_scaled ≈ 0` against nonzero Skylit values.
This is the documented §9 residual (cell-level dynamic state), not weighting-layer
error. Material nodes per record: min 10, p50 31, max 74 (mean 34.3).

## 5. Dataset coverage and day accrual

Source: `data/p0/{re_inventory,uw_coverage,session_day_frames}.json`,
`data/e02/fit_dataset/index.json`, `data/e04/acceptance_stats.json` `coverage`.

| Layer | Days | Detail |
|---|---|---|
| RE Skylit captures (X10 `gammasummit/t3/re/raw/`) | 20 session-days (2026-09-01 → 2026-09-30) | 5,187 manifest entries (matrix/gamma 3,087, matrix/vanna 1,580, range/gamma 520); 0 manifest-vs-disk mismatches |
| UW `gamma_data_v2` rows | 3 session-days (09-28: 185 snapshots, 09-29: 210, 09-30: 318) | days 09-01 → 09-25 have 0 rows (frame status `skylit-only`); UW batch collection starts 2026-09-26 |
| Tier-A aligned (RE instant + UW batch, tol 90 s) | **3** | 1,691 records (09-28: 25, 09-29: 788, 09-30: 878); fit_dataset instants 1,691 |

Binding constraint for criterion 1 is **UW batch coverage**, not RE captures:
17 of the 20 RE days cannot pair with UW data. Accrual: one new Tier-A
session-day per RTH session (daily refit cron `gammasummit-e02-daily-refit`,
id fd1a1660c172, 14:30 local; incremental `prepare` per spec §8.6) →
**≥ 20 Tier-A aligned days ≈ 2026-10-28**.

## 6. Reasons for the verdict + gaps

Reasons (each maps to a gate-matrix row):

1. **R1 — session-days 3 < 20.** UW `gamma_data_v2` coverage begins 2026-09-28;
   the gate cannot be formally measured over ≥ 20 session-days before
   ≈ 2026-10-28. Not waivable: the §9 state features must not be fitted on
   < 20 aligned days (overfit risk, spec §9).
2. **R2 — king exact 26.85% < 90%.** Far from the bar even on the 3 measured
   days. Worst: QQQ 0.25%, IWM 0.75% exact. SPX misses are bimodal (0% of
   misses within ±25).
3. **R3 — node error median APE 1.0013 > 0.10.** 0/1,691 records anywhere near
   the ≤ 10% bar; dominant residual = missing cell-level dynamic state (spec §9).

Gaps → follow-up research cards (assignee `gammasummit-research`, created
2026-10-01, parented so G2 runs after G1 — both touch
`backend/core/exposure.py`):

| Gap | Card | Scope | Target |
|---|---|---|---|
| G1 — node error | **t_64a5c8a7** (E0.5a) | §9 cell-level dynamic state layer: per-(s,e) EWMA of gex/flow, node interaction counts (touched/rejected/delivered), rolling ceiling/floor of column magnitudes; new spec §10 + implementation + tests + before/after node-error measurement on current Tier-A days | median node APE ≤ 10% (bar enforced at gate re-measure over ≥ 20 days) |
| G2 — king parity | **t_561c5dbb** (E0.5b) | flip taxonomy (near-tie vs sign vs expiry mislocalization; QQQ/IWM exact ≈ 0 root causes; SPX bimodality) + value-level selection corrections + measured per-symbol exact rates | king exact ≥ 90% (bar enforced at gate re-measure over ≥ 20 days) |

(One mis-created duplicate of G1 exists — t_95d37209, wrong workspace flavor —
carrying a "superseded by t_64a5c8a7" handoff comment; do not dispatch work
there.)

G3 (day accrual) needs no research card: it is calendar-gated and automated —
cron `gammasummit-e02-daily-refit` (id fd1a1660c172) accrues one Tier-A day per
RTH session, refits incrementally, and comments day-count (N/20) on the gate
card.

## 7. Re-measure procedure (what flips the verdict)

Gate card t_b157a485 is parked (needs_input) and E1.1 scaffold
(t_9d6d5d66) stays gated — product build (E1+) starts ONLY after this gate
signs. Re-dispatch this card when **both** hold:

1. ≥ 20 Tier-A aligned session-days in `data/e02/fit_dataset` (≈ 2026-10-28);
2. gap cards t_64a5c8a7 and t_561c5dbb done.

Then: rerun the three commands in the evidence chain, regenerate
`data/e04/acceptance_stats.json`, replace the tables above with the ≥ 20-day
numbers, and set the verdict line to **"P0 SIGNED"** only if king exact ≥ 90%
over the full ≥ 20 session-days AND median node APE ≤ 10% — otherwise restate
**"P0 NOT SIGNED (reasons + gaps)"** with updated reasons.

## 8. Provenance and determinism

- E0.3 harness rerun 2026-10-01T08:09Z (run `--execute`) reproduced E0.3's
  2026-10-01T08:00Z run exactly: `summary.json` identical (minus
  `generated_at`), `per_record.csv` and `star_comparison.csv` byte-identical,
  `node_comparison.csv.gz` content-identical (gzip header timestamp only).
  Pre-run backup: `data/e03/history/pre-e04-20261001T080927Z/`.
- Output hashes recorded by `scripts/e04_acceptance_report.py --check`
  (`data/e04/acceptance_stats.json` `source_run`, sha256):
  - `summary.json` 4bc2c577ad23c6226a11043db8ea7df691110113abd1bc8732dfd32e0b919bd2
  - `per_record.csv` 5899136176ecdab5053c1abe4c6b95f8bea834d369afb1ab9ea7df9e857d2df0
  - `star_comparison.csv` 1a0028f0dbe5a0c5669f11fec9c376c64d64e3e70669d102221668421a78eef0
  - `node_comparison.csv.gz` f32c1dfced7374f156fcd491841b76ab5f78bcd61a8df906c2a3dfeaf91191b2
- Row counts: per_record 1,691 = summary `n_scored` 1,691; node_comparison
  715,454; star_comparison 15,260. `verify` re-checks these on every run.
- Clean-room evidence (E0.3 handoff + `verify`): textual import-scan hits NONE;
  `backend/core/exposure.py` imports stdlib only; no SignalForge tokens in
  code.
- No writes to SignalForge production; no Skylit API calls in this report's
  pipeline (RE data = already-captured raw on X10); secrets untouched.

---

**P0 NOT SIGNED (reasons + gaps)** — R1: 3/20 session-days (UW coverage starts
09-28; ≥ 20 days ≈ 2026-10-28). R2: king exact 26.85% < 90%. R3: median node
APE 1.0013 > 0.10. Gaps: G1 t_64a5c8a7 (§9 state layer), G2 t_561c5dbb (king
parity). Re-dispatch gate at ≥ 20 Tier-A days + gap closure (§7).
