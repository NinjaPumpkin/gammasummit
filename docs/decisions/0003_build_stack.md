# 0003 — Build stack: Vite SPA, TanStack, lightweight-charts, FastAPI, SQL-first migrations

Date: 2026-09-30 · Status: accepted

## Context

Frontend design mock (`frontend/mockups/dashboard-v1.html`) is settled enough
to lock presentation tooling. Backend must stay Python 3.10 (VPS), lean, and
testable. Weighted by past failures: preview/auth pain (ADR 0002), tz bugs,
schema anti-patterns.

## Decisions

1. **Frontend: Vite + React SPA.** No SSR — the app lives behind auth and data
   is dynamic; SSR adds nothing but complexity. Deployed on Vercel with the
   ADR 0002 preview workflow.
2. **Data fetching: TanStack Query** (cache, stale-while-revalidate, refetch
   windows). No global state library until proven needed.
3. **Charts: TradingView lightweight-charts** (Apache-2.0) for time series
   (DDOI, spot); custom SVG for GEX profile and heat grid (full control, tiny).
   **TanStack Table + virtualization** for MEATSEEKER grid.
4. **Validation: Zod** on the client, **pydantic** on the server, types
   generated from the OpenAPI spec (`openapi-typescript`) — one contract.
5. **API: FastAPI + uvicorn** (async, OpenAPI from code per ch.25), plain SQL
   via `asyncpg` — no ORM layer between us and the tiering schema (ch.08:
   transaction boundaries stay visible).
6. **Migrations: SQL-first** (`db/migrations/NNNN_*.sql`) applied by a thin
   runner (dbmate or custom) — schema is reviewed as SQL, not generated.
7. **Mocks: MSW** implements `DATA_MODE=mock` (ADR 0002); Storybook for
   widget-level review; Playwright for E2E smoke.

## Consequences

- New widget = React component + Zod-typed endpoint + Storybook story —
  consistent path, reviewable in preview before merge.
- No ORM means SQL knowledge required per contributor — acceptable for a
  small team where schema discipline is the product.
- lightweight-charts is canvas-based: text summaries for accessibility
  (design spec requirement).

## Rejected

- Next.js/SSR: complexity without benefit behind auth (revisit only if SEO
  marketing pages join this app).
- Recharts/visx as primary: weaker for dense financial time series.
- SQLAlchemy: obscures partition/rollup SQL; raw SQL + typed models is leaner.
