# Frontend Design Spec — Dashboard v1

> ⚠ STATUS 2026-09-30: mock visuals **rejected by owner**. UI source of truth
> is now `docs/design-reference-skylit.md` (skylit.ai layout patterns). This
> spec's interaction rules, perf budgets, and accessibility baseline remain
> valid; the visual/layout sections will be rewritten from the design
> reference when UI build starts. Mock file kept as history only.

Companion to `frontend/mockups/dashboard-v1.html` (open in browser to view).

## Information hierarchy

1. **Ticker context** (always visible): symbol, spot, change, GEX flip, net GEX,
   OI, IV rank — one horizontal strip under the header.
2. **MEATSEEKER grid** (primary widget, largest): strike-level gamma/OI truth
   table. Strikes descending, ATM row highlighted amber.
3. **Time-series context**: DDOI intraday chart (≥350px), zero-line reference.
4. **Interpretation**: AI Analyst card — regime banner, conviction bar, thesis.
5. **Surfacing**: GEX profile (by-strike bars), OI Movers, Flow Triage.

## Color semantics (locked)

| Color | Meaning |
|-------|---------|
| green | positive net / adds / bullish |
| red | negative net / drops / bearish |
| amber | key levels (GEX flip, ATM), warnings |
| violet | mode accent (Cloutseeker/SpotGamma/FATTE = product modes) |
| blue | active selection, block prints |

Heat cells: green/red tinted backgrounds on NET GEX column only — text color
carries sign elsewhere (avoids visual noise).

## Interaction rules

- Mode toggles (CLOUTSEEKER / SPOTGAMMA / FATTE) switch widget set/behavior
  globally; ticker chips switch instrument without reload.
- Expiry tabs: first 3 expiries default; `ALL` opt-in (aggregated view).
- Widgets draggable (grid layout persisted per user); drag handles in headers.
- Every data surface shows `Last updated` — freshness is UX, not an ops detail.
- Long-tail tickers: lazy-load with loading state + cached timestamp shown.

## Performance budgets

- Initial shell < 2s on broadband; widgets stream in.
- Widget re-render < 100ms after data arrival.
- Table virtualization above 200 rows.
- Charts lazy-loaded (code splitting); mock/DOM stays light.

## Data presentation rules

- Numbers right-aligned, tabular-nums monospace; strikes centered.
- K/M/B suffixes for counts; sign always explicit (+/−).
- Δ columns always show session delta, not absolute.
- Tooltips on chart points: timestamp, value, spot at time.

## Accessibility baseline

- Contrast ≥ 4.5:1 for text (dark theme verified in mock).
- Keyboard: tab through chips/tabs; charts have text summaries.
- Never encode sign by color alone (± symbol mandatory).

## Mobile

Single column, widgets stack in hierarchy order (mock responsive breakpoint at
1100px). MEATSEEKER grid horizontally scrollable with sticky strike column in
production build.
