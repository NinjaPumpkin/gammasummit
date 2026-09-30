# Security — Look Ahead

Beyond `docs/security.md` checklist. Grounded where freshness matters
(auth landscape verified 2026-09-30).

## Identity — the big move: passkeys

**Supabase Auth Passkeys (Beta) shipped 2026-05-28**: WebAuthn discoverable
credentials — Face ID / Touch ID / Windows Hello / hardware keys. Dashboard →
Authentication → Passkeys; client opt-in via `experimental: { passkey: true }`
(API experimental during beta — pin behavior with tests).

Why it beats magic links for users AND security:

| | Magic link | Passkey |
|---|---|---|
| Phishing resistance | none (bearer link forwardable) | phishing-resistant (origin-bound) |
| UX | email round-trip | one-tap biometric |
| Preview friction (ADR 0002 pain) | high | none |
| Replay risk | token in inbox/forward | private key never leaves device |

Rollout: **passkeys primary + magic-link fallback** → measure adoption →
deprecate magic links for routine sign-in (keep as account-recovery path with
hardened settings: ≤10 min expiry, single-use, no open redirects).

Also near: TOTP MFA for admin/editor roles; session hygiene (rotation,
device list, remote revoke).

## Edge & transport

- Cloudflare proxy in front of `gammasummit.top`: hides VPS IP, DDoS layer,
  managed WAF rules, static asset cache.
- HSTS preload; CSP: start `Content-Security-Policy-Report-Only`, collect
  reports, then enforce (ch.17). If DuckDB-WASM lands: COOP/COEP headers —
  CSP and isolation designed together, not patched twice.
- TLS 1.3; rate limits per user+IP; Turnstile on auth endpoints if abuse shows.

## Supply chain (ch.17 + 21)

| Control | Tool |
|---|---|
| secret scanning pre-commit + CI | gitleaks |
| static analysis CI | Semgrep (OWASP ruleset) |
| image scanning | Trivy (fail CI on HIGH/CRITICAL) |
| SBOM per release | syft |
| dependency updates w/ CI gate | Renovate |
| lockfiles with hashes | `npm ci`, `uv`/`pip-tools` pinned |
| dynamic scan before go-live | OWASP ZAP baseline |

## Runtime & host

- Containers: non-root, read-only FS, dropped caps, `no-new-privileges`.
- VPS: ufw default-deny, SSH keys only (no password auth), fail2ban,
  unattended-upgrades; admin plane via Tailscale only (already our pattern).
- **Secrets → KeyHub** (owner's own project): `keyhubd` deterministic daemon =
  sole secret holder, services get credentials via `keyhub run --` env
  injection, backend = Bitwarden Secrets Manager. No long-lived `.env` files on
  disk → the `.env.bak` incident class dies permanently.

## Authorization & data

- Deny-default grants + **CI regression test** (`has_table_privilege` must fail
  the build if a data table becomes anon-readable) — already in toolkit.
- Defense in depth: RLS AND API-layer authz (ch.04) — one layer failing does
  not expose data.
- Audit log: who queried what, when (API layer), retained ≥ 90d.
- Per-user quotas on expensive endpoints (on-demand backfill triggers).

## Resilience & response

- Quarterly **backup restore drills** (an untested backup is not a backup).
- Incident runbook: severity matrix, comms template, log preservation —
  fill `docs/operations.md` playbooks before go-live, not after first incident.
- Email auth on sending domain: SPF + DKIM + DMARC (magic-link/recovery
  deliverability + anti-spoof).

## Compliance note (inherited owner decision 2026-07-27)

No commercial data redistribution; product is a gated internal demo using
existing sources. UI must not imply licensed redistribution. Revisit if the
product goes public/paid.
