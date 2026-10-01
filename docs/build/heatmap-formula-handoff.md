# Heatmap Formula Handoff — for the GammaSummit build agent

*From the SignalForge RE session, 2026-09-30. Purpose: unblock the Skylit
heatmap "formula" work with what is PROVEN, what is PROVEN IMPOSSIBLE, and the
spec to build instead.*

## TL;DR — stop fitting, start building

Two proofs close the reverse-engineering question (both from real captured
pairs in `SignalForge/data/skylit_pairs/` — 21 grids, **7,893 cells**, each cell
carrying BOTH the displayed `$` label and the resolved fill color):

1. **The `$` labels are not reproducible from public chain data** —
   `SignalForge/scripts/skylit_formula_fit.py`, n=3,899, best R²=0.033, and the
   per-grid scale drifts 55M→231M (a private positioning feed rescales it).
   Verdict recorded 2026-09-29 in `docs/SKYLIT_REVERSE_ENGINEERING.md` §0.
2. **The cell COLORS are independent of the `$` labels** —
   `SignalForge/scripts/skylit_color_fit.py` (today): mapping each fill hex back
   through the viridis ramp and correlating ramp position against the cell's own
   displayed value gives **per-grid Spearman ≈ 0.037 (mean of 21 grids)**; every
   power-law/center/normalization family tested fits at R² ≤ 0. The label
   channel and the color channel carry different information.

**Therefore: parity-by-fitting their constants is impossible. Anyone asking for
"the Skylit formula" needs these two proofs, not more fitting runs.** The color
channel most plausibly encodes a *change/velocity* dimension (the DOM hint
`data-velocity-key=strike_expiry`), fed from the same private layer as the `$`.

## What IS known about their visual grammar (from live RE, keep these)

- Default palette = matplotlib **viridis** (7 palettes total: viridis, cividis,
  inferno, magma, plasma, turbo, grayscale).
- Anchor colors: zero region ≈ `#355b8a` (blue), max positive ≈ `#fde725`
  (yellow), max negative ≈ `#440154` (purple).
- Measured zero-value cells sit at ramp position **t ≈ 0.41** (n=40 cells).
- Cell CSS vars: `--desktop-heatmap-fill` / `--desktop-heatmap-brightness` /
  `--desktop-heatmap-cutoff`; **ink flips at brightness/cutoff 128** (light text
  on dark cells, dark text on bright cells).
- Node marks: `lucide-star` = significant cell, crown = auto-center button.
- Their normalization is asymmetric (pos branch and neg branch behave
  differently — pos ≈ `.5+.5·r^1.5`, neg ≈ `.5−.5·|r|^.85` as the RE-era shape
  guess). Constants were never fittable — see proof 2.

## The formula to BUILD (ours, principled, anchor-consistent)

Design decision: keep their **two-channel design language** — label and color
carry different information — but fill both from OUR data.

### Channel 1 — cell label (the $ value)
Net gamma exposure per strike × expiry cell, standard GEX:

```
cell_$ = Σ_contracts  OI × gamma × spot × 100 × ±1   (calls +, puts −)
```

Already implemented: `gammasummit/backend/core/exposure.py`. Source columns:
Supabase gamma tables (`call_gex`, `put_gex`, `call_oi`, `put_oi`, `spot_price`,
`is_spot` flag — there is NO `index_value` column).

### Channel 2 — cell color (the velocity layer)
Signed **GEX change since the prior snapshot** (the closest public analog to
their velocity dimension):

```
r = Δcell_$ / max|Δcell_$| in the current grid
```

### Color mapping (constants chosen to hit the observed anchors exactly)

```
t(r) = 0.41 + 0.59 · r^1.5          r > 0   (0.41 -> 1.0, yellow)
t(r) = 0.41 − 0.41 · |r|^0.85       r < 0   (0.41 -> 0.0, purple)
color = viridis(t)                          (matplotlib LUT, 256 stops)
```

- t(0) = 0.41 matches the measured zero-cell position (n=40).
- t(+1) = 1.0 = `#fde725`, t(−1) = 0.0 = `#440154` — the observed anchors.
- The asymmetric exponents (1.5 vs 0.85) preserve the RE-observed shape
  language: positives compress toward yellow slowly, negatives darken fast.
- **These constants are OUR design choice within the measured anchor
  constraints** — Skylit's actual constants are unfittable (proof 2), so this
  is the honest substitute: visually consonant, mathematically clean.

### Reference implementation (JS, for the frontend)

```js
const VIRIDIS = /* 256-stop LUT (matplotlib viridis) */;
function cellColor(r) {                    // r = signed, |r| <= 1
  const t = r > 0 ? 0.41 + 0.59 * Math.pow(r, 1.5)
                  : 0.41 - 0.41 * Math.pow(Math.abs(r), 0.85);
  return VIRIDIS[Math.round(t * 255)];
}
function inkFor(t) { return (t * 255) > 128 ? '#111' : '#eee'; }  // cutoff 128
```

### UI details to keep (parity checklist items)
- `--desktop-heatmap-fill` gets `cellColor(r)`; `--desktop-heatmap-brightness`
  drives the 128-cutoff ink flip.
- Star node on significant cells (rule: |r| ≥ 0.8 or your own threshold);
  crown = auto-center.
- Palette picker: the 7 matplotlib stops.

## Reproduction (verify before trusting)

```bash
cd SignalForge
.venv/bin/python scripts/skylit_color_fit.py        # the fit attempts + $0 anchor
# plus the Spearman probe (in the docs commit message / RE notes)
```

Raw captures: `data/skylit_pairs/PAIR_*.json` (cells: `key`, `fill`, `text`,
`star`) + `data/skylit_sameinstant_v2.json` (full same-instant chain rows).

## UPDATE 2026-10-01 — API access changes the game (calibration path)

The owner's Skylit API key now exists (`SKYLIT_API_KEY` in `~/.hermes/config.yaml`
and `gammasummit/.env`; 68k+ credits, 120 req/min). The un-fittable proofs above
stand for *reverse-engineering from UI captures*, but the API exposes the real
inputs — so parity is now CALIBRATABLE rather than unknowable.
`SignalForge/scripts/skylit_api_calibrate.py` (1 credit/run) pulls
`/v1/heatmap` (per-strike `value`, `nodeType`, `velocityPct`) against our
`gamma_data_v2` snapshot. First side-by-side (2026-10-01 16:57 UTC):

- **Node tiers are RANK-based per symbol, structure exactly**: king = the single
  top |value| strike (n=1), gatekeeper = next band (3–10), pika = exactly 3,
  barney = exactly 3, rest normal. Order by |value|:
  `normal < barney < pika < gatekeeper < king`. Replicate this ranking, not
  absolute thresholds (their absolute ranges differ per symbol).
- **Values: per-symbol sign/scale conventions differ** (Spearman vs our net GEX:
  SPY +0.26, SPX −0.46, QQQ −0.51; scale ratios 1.27 / 0.075 / 1.87) — the
  negative correlations suggest a sign-convention difference (try
  `put_gex − call_gex`, `abs_gex`, gross). Remaining gap = a per-symbol
  calibration constant, computable continuously with cheap `/v1/heatmap` pulls.
- **`velocityPct` is live per strike** — the color-channel design (velocity) is
  confirmed correct and can be calibrated against our `gamma_velocity` table.

So the build guidance: keep the two-channel spec below, add a calibration layer
(their `value` → our display scaling, their `nodeType` rank rules), and use
`/v1/historical` (5 cr, 1s frames) for deeper RE when needed.

Owner wants GammaSummit visually 1:1 with Skylit's heatmap language (he uses
Heatseeker daily) but built on our own UnusualWhales/Leandata data. These two
proofs let the build move forward with confidence: we match what is observable
(grammar, anchors, interactions) and stop burning cycles on what is
mathematically private (their values, their scaler).
