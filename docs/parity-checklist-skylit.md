# Skylit 1:1 Parity Checklist

Owner directive 2026-09-30: reach 1:1 parity with skylit.ai, THEN finalize
frontend/backend architecture and port SignalForge into gammasummit.

**Honest boundary (from `SignalForge/docs/SKYLIT_REVERSE_ENGINEERING.md` §0,
fitted on 3,899 cells):** exact `$` value parity is NOT recoverable from public
chain data — their values embed a private flow-directionalized layer. "1:1"
therefore means: **visual system + layout + controls + behaviors = 100%**,
value layer = ours (gross-gamma surface + own positioning layer, calibrated).
Their branding/copy/assets stay theirs; our names/identity stay ours.

Legend: ✅ in demo v3 · 📝 spec'd, builds in phase 4 · 🔍 needs deeper session ·
⏭ v2 · 🚫 out of scope

## Heatmap — toolbar

| # | Element (their name) | Behavior | Status |
|---|---|---|---|
| 1 | Ticker picker + universe count + ⌘K | switch instrument, command palette | ✅ (palette = phase 4) |
| 2 | GEX / VEX toggle (⌘G / ⌘V, zap/activity icons) | metric mode | ✅ (VEX wiring ⏭ v2) |
| 3 | Pinned ticker strip (SPXW + spot + Δ%) | secondary instrument tape | ✅ |
| 4 | Movement filter `All ▾` → All / ↑ Increasing / ↓ Decreasing | filter by velocity direction | ✅ functional |
| 5 | **Velocity Timeframe** `Δ ▾` → **All, 1m, 5m, 15m, 1h, 4h, 1d** (detail panel also shows 10 min) | %Δ window for chips | ✅ functional |
| 6 | **Disable Velocity** toggle | hide chips + stop pulses | ✅ functional |
| 6b | Keyboard shortcuts `?` dialog + Cmd+J (AI), letter = ticker search, ←/→ prev/next ticker, Shift+G/V/C (NetGEX/NetVEX/GEX+VEX), Shift+T Trinity, Shift+R replay, Shift+H heatmap sidebar, Shift+A alerts sidebar, 1-9 watchlists, Cmd+1-9 favorites | power-user nav | 📝 spec captured (appendix A) |
| 6c | Notifications bell | alert center | 🔍 panel content unseen |
| 7 | **View Controls** (`92\|5` label): QUICK PRESETS Tight/Normal/Wide · STRIKE RANGE slider · EXPIRATIONS Front 2/3/5/All + To Friday / To Next Friday / To OPEX / To Next OPEX / To Q-OPEX / To Next Q-OPEX · HIDE STRIKES Empty/Under/Off | grid density + column/row filtering | ✅ functional (date ladders 📝) |
| 8 | **Node %** panel: PRESET Off/Focus/King · SAVED Custom/Save as · READ AS Value/% King · SIGN ±/Abs · DECIMALS 0-3 · TEXT SIZE + Auto · BOLD · LOW NODES Hide/Dim/Fade · MIN % KING slider · DIM TO · PALETTE ×7 · VELOCITY All/Selected · RAW HOVER · preview rig 6 cells | per-cell display semantics | ✅ core functional (TEXT SIZE/DIM TO/SAVED/RAW HOVER 📝) |
| 9 | Center on Spot (target) | recenter | ✅ static |
| 10 | Auto-center crown toggle | follow king node | ✅ static |
| 11 | Enter replay mode (Shift+R) | historical playback | ⏭ v2 (T3+DuckDB) |
| 12 | Refresh / auto-refresh timer | reload | ✅ static |
| 13 | Copy image / Save image | export PNG | ⏭ v2 |
| 14 | Add favorite | pin ticker | ⏭ v2 |
| 15 | Movers 20 filter | top-movers view | ⏭ v2 |
| 16 | Floating AI button ("Aegis") | their assistant | 🚫 ours = AI Analyst (own) |

## Heatmap — grid & cells

| # | Element | Behavior | Status |
|---|---|---|---|
| 17 | Strike × expiry matrix, 18px rows, sticky strike col | core layout | ✅ |
| 18 | Cell color system: fill + brightness + cutoff 128 ink flip (light/dark text) | legibility on heat | ✅ (luminance flip) |
| 19 | 7 palettes (Viridis default, Cividis, Inferno, Magma, Plasma, Turbo, Grayscale — matplotlib stops) | theme picker | ✅ functional |
| 20 | Asymmetric normalization (pos ≈ .5+.5·r^1.5, neg ≈ .5−.5·|r|^.85, intensity floor) | color mapping | ✅ approx — constants 📝 fit from live pairs |
| 21 | **Velocity chip bubble** in-cell (`-5%` = change over selected window) | live Δ% | ✅ |
| 22 | **Cell pulse on big change: green = increasing, red = decreasing** (`velocity-pulse` scale 1.02/opacity .6→1 1.8s + `velocity-ring` border 1→2px 2s) | intraday alerting | ✅ |
| 23 | Row highlight flash (`highlight-pulse` 2s) on row events | event cue | 📝 wire to alerts |
| 24 | **King node**: bold + violet inset ring + filled star (lucide-star) | top node marker | ✅ |
| 25 | Significant node: ring ≥ MIN % KING | threshold marking | ✅ |
| 26 | Row left edge bar green/red by row net exposure | row sentiment | ✅ |
| 27 | `data-velocity-key="strike_expiry"` cell keys | velocity tracking | ✅ (attr present) |
| 28 | Server node tiers: king / gatekeeper / pika / barney / significant / normal | classification | 📝 our names: king / wall / gatekeeper / significant / normal |
| 29 | **Cell click → detail panel** (swept 0930): header `Strike N` + expiry + sentiment chip (NEUTRAL), CURRENT VALUE + exposure direction ("Exposure Decreasing"), VALUE OVER TIME mini-chart, **RATE OF CHANGE table: 1/5/10/15 min + EXTENDED 1h/4h/1d** + velocity | per-cell drill-down | 📝 spec captured — v1 component |
| 29b | Cell hover tooltip | RAW HOVER mode only | 🔍 none observed with default settings |
| 29c | **Replay mode (Shift+R)**: scrubber (date + time), Step 1m, Speed 1x, data timestamp, "replay continues across trading sessions", Esc exit | historical playback | ⏭ v2 — spec captured |
| 29d | Movement filter ↑/↓ behavior (chip-only vs cell filtering) | exact semantics | 🔍 dimming not observed — deeper session |
| 29e | VEX mode: cell values swap to VEX scale (larger magnitude format) | metric semantics | ✅ noted (format $-202,907.8K style) |

## Other surfaces (checklists expand at build time)

- **Atlas chart workspace**: layouts, timeframe ladder 1m→1D, exposure/expiry
  filters, nodes, projection modes, watchlist, alerts, trade deck, replay →
  📝 v2 (design-reference §2)
- **Talon AI**: chat + building canvas, prompt chips, stance presets,
  disclaimer → v1 card, v2 canvas (design-reference §3)
- **Flowseeker**: 22-col flow table, filter bar, stat chips, dark feed,
  scanner, compass → v1 feed, v2 rest (design-reference §4)
- Sidebar: collapsible groups + per-group hide + notifications + shortcuts(?)
  → ✅ structure, 📝 behaviors

## Source documents

- Deep RE (palettes, node styles, API, normalization ground truth):
  `SignalForge/docs/SKYLIT_REVERSE_ENGINEERING.md`
- Layout patterns + product map: `docs/design-reference-skylit.md`
- Working demo: `frontend/mockups/dashboard-v3.html`

## Gate

Heatmap rows 1–28 ✅/📝 resolved + one full intraday session comparing
live-vs-demo side by side → parity accepted → THEN architecture freeze +
SignalForge port begins (`docs/migration-from-signalforge.md`).
