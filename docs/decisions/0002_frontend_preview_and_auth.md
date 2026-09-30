# 0002 — Frontend preview, staging, and auth-for-previews

Date: 2026-09-30 · Status: accepted

## Context

Frontend will change continuously (widget parity work, TWEATerminal modes).
Current SignalForge flow on Vercel: changes reach production directly, and
magic-link login makes previewing painful — the auth redirect lands on the
production URL, so looking at a change forces a live login. Owner wants to
inspect builds safely before they go live.

## Decision

### 1. Environment matrix

| Env | Trigger | URL | Data | Auth |
|-----|---------|-----|------|------|
| Development | local `npm run dev` | localhost | local/mock | fixed test account (no email) |
| Preview | push to any non-`main` branch (Vercel Preview Deployment) | `*-<hash>.preview.gammasummit.top` | staging API / mock mode | test accounts only |
| Production | merge to `main` | `gammasummit.top` | live API | real magic-link login |

`main` is the **only** production path. No direct deploys to prod.

### 2. Preview URL suffix (magic-link fix)

Use Vercel **Preview URL suffix** bound to a custom wildcard under a domain we
own: `*.preview.gammasummit.top`. Then Supabase Auth redirect allow-list gets
one tight entry `https://*.preview.gammasummit.top/**` instead of the risky
`*.vercel.app` wildcard (any Vercel customer can claim a `*.vercel.app`
subdomain — never allow-list that for auth redirects).

Fallback if suffix unavailable on plan: keep previews on `*.vercel.app` but do
**not** route real magic links through them (rule 3 instead).

### 3. Previews never send real magic links

- Preview/Development auth uses **test accounts or fixed OTP** — no email
  sending from previews, ever.
- Real magic-link login = production only.
- This is what makes previews click-through-able in seconds instead of
  mailbox round-trips that land on the wrong URL.

### 4. Two preview modes (both first-class)

- **Mock mode** (`DATA_MODE=mock`): full UI against fixtures — fastest design
  review, no backend, no login. Default for UI work.
- **Staging mode**: preview talks to staging API with staging data —
  integration review before merge.

### 5. Vercel Deployment Protection on previews

Previews are password-protected (Vercel Deployment Protection + bypass secret
for automation/CI). Share link + password in the PR — no accidental public
exposure of half-built UI.

### 6. Component-level preview

Storybook (or equivalent) for the widget set (MEATSEEKER grid, DDOI chart, OI
Movers, mode toggles): review widgets in isolation without any deploy.

## Consequences

- Every push to a feature branch = a private, shareable, login-free preview.
- Production changes only via merge to `main` + production auth flow.
- Two data modes to maintain (mock + live) — small cost, big review speedup.
- Supabase Auth config gets one wildcard entry per environment; documented in
  `docs/security.md` (auth redirect allow-list is security-sensitive).

## Rejected alternatives

- Direct Vercel CLI deploys to production (`vercel deploy --prod`):
  reproduces the current problem — no review step.
- `*.vercel.app` auth-redirect wildcard: too broad for credential delivery.
- Real magic links on previews: mailbox round-trips + wrong-URL redirects =
  exactly the pain we are removing.
