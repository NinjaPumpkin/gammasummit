# Security

Per Backend Bible ch.17 (security) + ch.14 (config) + ch.04 (auth). Data from
users/inputs is never trusted; the database is never a public read surface.

## Model

```
frontend ──(HTTPS)──► API (authn + authz + rate limit) ──(service role)──► Postgres
```

- The frontend holds **no** database credentials. No anon key in browser code.
- Database grants: deny-by-default. Service role lives only in server env.
- SignalForge lesson (measured 2026-09-30): 1,257/1,382 tables without RLS and
  anon SELECT on gamma tables = strangers can burn our compute. Never again.

## Checklist (must hold before any endpoint ships)

- [ ] Input validation on every parameter (ticker, dates, ranges) — ch.05
- [ ] Parameterized SQL only; no string-built queries — ch.17 §injection
- [ ] Authn on all non-public endpoints; authz checked per resource (BOLA) — ch.17
- [ ] Rate limiting per client at the edge — ch.17
- [ ] Security headers + TLS only — ch.17
- [ ] Error responses never leak internals (SQL, stack, paths) — ch.12
- [ ] Secrets in env files (mode 600, gitignored) — never in code or git — ch.14
- [ ] Dependency pinning + minimal dependency set

## Secrets handling

- Env files outside the repo on servers (`/etc/gammasummit/env`, mode 600).
- `.env*` gitignored; `.env.example` holds names only, never values.
- Rotation runbook in `docs/operations.md`.
- Log scrubbing: never log tokens, full request bodies, or connection strings.

## Data protection

- Cold exports (Parquet) contain market data only — no user PII anywhere in
  this system's data tier.
- Backups encrypted at rest (B2/R2 server-side encryption; disk-level on
  external drive).
