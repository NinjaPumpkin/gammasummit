# Frontend — Look Ahead

Beyond ADR 0002/0003 and the v1 mock. Prioritized: build-with-v1 → mid → later.
Product goals honored throughout: one mobile UI, TWEATerminal parity, alerts.

## Near — build alongside v1

| Item | What it gives users | Notes |
|---|---|---|
| **Passkey login** | one-tap Face ID/Touch ID sign-in, zero email round-trips | pairs with `docs/ops/security-future.md`; magic-link stays as fallback |
| Skeleton + streamed widget states | instant shell, data fills in | matches design-spec perf budget |
| SSE delta updates | live numbers without refetch storms | ch.24: backpressure + reconnect w/ backoff |
| ⌘K command palette (`cmdk`) | ticker/mode/nav in one keystroke | power-user core for a trading tool |
| Saved layouts | draggable widget arrangement persists per user | ADR 0002 mock already shows drag handles |
| Virtualized grid | MEATSEEKER stays at 60fps with 500+ strikes | TanStack Table + virtualizer |

## Mid — after core widgets stable

- **PWA**: installable home-screen app, offline shell + last-known snapshot →
  the "single mobile UI" goal. Responsive breakpoint already in mock (1100px).
- **Web Push alerts**: user-defined rules — regime flip, OI mover threshold,
  sweep > premium X, GEX flip breach. Needs alert-rules UI + push subscription
  management.
- **View Transitions API**: smooth ticker/mode switches (progressive
  enhancement, non-supporting browsers unaffected).
- **Feature flags** (OpenFeature + self-hosted Unleash, or env flags first):
  ship widgets dark, light up gradually.
- **Visual regression CI**: Playwright screenshots per widget (or lost-pixel
  OSS) — catches layout breakage before preview review.
- **Web Vitals RUM** via GlitchTip frontend SDK — see what users' real loads do.
- **Compare mode**: two tickers side-by-side, or expiry-vs-expiry diff.

## Later / experimental

- **DuckDB-WASM in browser**: on-demand history queries over Parquet on R2 with
  zero backend compute. Requires COOP/COEP headers (cross-origin isolation) +
  signed URLs — coordinate with CSP work (`docs/ops/security-future.md`).
- **WebGL chart path** (uPlot or regl) if real data exceeds ~100k visible
  points; stay on lightweight-charts until measured need (ADR 0003).
- **AI Analyst streaming**: SSE token stream + reasoning panel + source
  citations from T2 rollups.
- **Multi-monitor pop-outs**: detachable widgets via BroadcastChannel.
- **Skylit parity expansion**: Heatseeker / Atlas / Talon / Flowseeker /
  Academy modes as product roadmap (owner product direction).
- Timezone toggle (ET/UTC), half-day/holiday visual markers.

## Anti-goals

- No micro-frontend, no SSR, no global state library until one is forced by a
  real use case. No chart-library churn: one primary (lightweight-charts) + SVG.
