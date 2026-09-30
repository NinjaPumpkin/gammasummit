# frontend/

Dashboard web app (TWEATerminal-style). Reads the **API only** — never the
database directly, never a Supabase key in browser code.

## Product conventions (owner-locked)

- Dark, high-contrast theme
- Strikes displayed descending
- Charts ≥ 350px height
- Draggable widget layout
- First 3 expiries shown by default
- "Last updated" freshness indicator on every data surface
- Works on mobile — single pane, no terminal-jumping

## Widget set (parity target)

MEATSEEKER grid, DDOI chart, OI Movers, Cloutseeker / SpotGamma / FATTE modes,
AI Analyst card, regime banner, flow triage.

## Rules

- All data via `backend/api` endpoints (OpenAPI contract in `../db/../docs`
  once the API exists).
- On-demand loading: long-tail tickers lazy-load through the API's backfill
  path; show loading state + cached timestamp.
- No secrets, no service credentials, no direct DB URLs in frontend code.
- Loading/error/freshness states are mandatory on every widget (ch.12: the
  frontend must fail loudly and recoverably).

## Environments & previews (ADR 0002)

| Env | Trigger | Data | Auth |
|-----|---------|------|------|
| dev | `npm run dev` local | mock / local | fixed test account, no email |
| preview | push to non-`main` branch → Vercel Preview | mock mode default, staging optional | test accounts only — no real magic links |
| production | merge to `main` | live API | real magic-link login |

- Previews on `*.preview.gammasummit.top` (Vercel Preview URL suffix),
  Deployment Protection on (share link + password in the PR).
- Mock mode: `DATA_MODE=mock` renders full UI from fixtures — no login, no
  backend. Default for design review.
- Storybook (or equivalent) for widget-level review without deploys.
- Hard rule: **only `main` reaches production.** No direct prod deploys.

## Build order

Start after `backend/api` has: ticker list, T1 series, T2 history, freshness
endpoint. Mock against the OpenAPI spec before the API lands.
