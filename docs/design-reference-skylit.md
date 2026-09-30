# Design Reference — skylit.ai layout patterns

Owner directive 2026-09-30: GammaSummit UI follows skylit.ai layout patterns;
mock v1 visuals rejected. This document records **structural layout patterns**
observed from the live product (account: owner's own subscription).

IP note: we emulate layout structure, density, and interaction patterns.
Their branding, copy, naming, and visual assets stay their property — our
naming (MEATSEEKER/Cloutseeker etc.) and our own visual identity remain ours.

## Global frame (all pages)

```
┌────────┬──────────────────────────────────────────────────────┐
│ SIDEBAR│ TOP BAR: ticker selector + ⌘K palette + universe count│
│ (nav)  │ metric tabs (GEX/VEX/…) · spot + Δ% · timeframe chips │
│        ├──────────────────────────────────────────────────────┤
│        │ MAIN WORKSPACE (per-product)                         │
└────────┴──────────────────────────────────────────────────────┘
```

- Sidebar: grouped nav tree, product sections expandable, current section
  highlighted, user chip + settings pinned at bottom.
- ⌘K command palette = first-class, always visible in top bar.
- Ticker context (symbol, spot, change) always visible — switches workspace
  content without page reload.
- Dark theme, dense tabular data, small type, color = sign/heat only.

## Page layouts observed

### 1. Heatmap dashboard (main)
- **Strike × expiry matrix as THE primary view**: rows = strikes (descending),
  columns = expiries (dates across top), cells = signed dollar values, red/green
  heat. Sticky header row + strike column.
- Metric segmented control (GEX / VEX / SPXW…) switches cell semantics.
- Timeframe quick-switch (All / 1m / …).

### 2. Chart workspace (Atlas-class)
- Configuration rail (left): layouts, metric mode, timeframe ladder
  (1m/3m/5m/10m/15m/1H/4H/1D), exposure/expiration filters, node markers,
  color scheme, projection mode (heatmap / trinity), watchlist, alerts,
  trade-deck, alert lines, crosshair, replay.
- Multi-ticker strip: mini-cards per instrument (price + key dollar values).
- Big chart canvas center; saved named layouts per user.

### 3. AI analyst (Talon-class)
- Top: index tape (SPX/SPY/QQQ/VIX + Δ%).
- Chat input with **suggested prompt chips** ("What is a king node?" style).
- Right/center: **analysis canvas that BUILDS as the conversation proceeds**
  (ticker → levels → flow → read → trinity), not a static card.
- Stance presets (Balanced / Scalp / Favorites), disclaimer line mandatory.

### 4. Flow feed (Flowseeker-class)
- Filter bar: saved views, shared view chips, LIVE badge, result count,
  sort, column picker, share.
- Summary stat chips row: sentiment, premium totals, C/P volume, P/C ratio,
  RVOL.
- Wide data table (the works): Date/Time, Ticker, Strike, C/P, OTM, Exp, DTE,
  Fill, Spread, Side, Flow Score, Contract Ratio, Size, Prem, Vol, OI, ΔOI,
  Spot, IV, V/OI, Strategy, Earnings. Color-coded fill/side cells.

## Product map (theirs → ours)

| Skylit area | GammaSummit equivalent | Scope |
|---|---|---|
| Heatmaps | Dashboard (MEATSEEKER-class matrix) | v1 |
| Atlas | Chart workspace w/ saved layouts | v2 |
| Talon | AI Analyst (chat + building canvas) | v1 card → v2 full |
| Flowseeker feeds/scanner | Flow module (triage, live feed) | v1 feed → v2 scanner |
| Tempest / Trinity | Mode presets (Cloutseeker/SpotGamma/FATTE) | v2 |
| Alerts | Alert rules + Web Push | v2 |
| Academy | Education content | later |
| Nexus (trades/leaderboard) | out of scope | never v1 |

## Interaction patterns to keep

- Everything reachable via ⌘K.
- Saved, named, shareable layouts/views per user.
- LIVE badge + result counts + freshness everywhere data streams.
- Segmented metric controls switch one workspace between data semantics.
- Disclaimers on any AI-generated interpretation.

## Design tokens (ours, to be finalized when UI build starts)

Dark, high-contrast; sign color green/red; amber = key levels; violet = modes;
monospace tabular numbers; ≥350px charts; strikes descending — product
conventions stay owner-locked (see `frontend/README.md`).
