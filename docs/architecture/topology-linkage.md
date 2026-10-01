# Topology & linkage — how every piece connects

Planning doc (2026-09-30, owner: planning phase, code will be on GitHub).
Verified live state first, then target state, then the R2 connection plan
(documented — nothing configured until build).

## Current state (verified 2026-09-30)

| Piece | Reality |
|---|---|
| Domain `gammasummit.top` | registrar **NameSilo** (created 2026-07-08) |
| DNS | delegated to **Vercel DNS** (`ns1/ns2.vercel-dns.com`) — nameservers set at Namesilo |
| Live web endpoint | `www.gammasummit.top` → **72.60.165.37 = Hostinger VPS nginx** → FastAPI + SPA (CSP shows `knszzlbwlnjjbnrlotib.supabase.co` + `localhost:8080` backend) |
| Vercel | SignalForge `dashboard-next` project (previews) |
| DB | Supabase `knszzlbwlnjjbnrlotib` |
| Cold data | X10 Pro only (R2 not connected yet) |

Correction to assumption: the product site is NOT on Vercel today — it is the
VPS. Vercel only hosts the dashboard-next project.

## Target state (linkage map)

```
GitHub (code + CI)                 NameSilo (registrar only)
   │  push → Actions lint/test        │ NS delegation
   │  merge → deploy                  ▼
   │                          Vercel DNS
   ├─► Vercel ── SPA + branch previews (*.preview.gammasummit.top)
   │       │  calls
   │       ▼
   ├─► Hostinger VPS ── api.gammasummit.top (FastAPI + asyncpg)
   │       │  queries                ▲ ingest (UW feeds)
   │       ▼                         │
   └─► Supabase (Postgres, T0-T2 hot/warm)
           │
           ▼ exports/rollups
   Cold tier: X10 Pro (local) ──rclone──► Cloudflare R2 (offsite, httpfs-queryable)
```

## Component decisions

| Component | Choice | Where planned |
|---|---|---|
| Code home | GitHub `gammasummit` repo (public per ADR 0001) | ADR 0001 |
| CI/CD | GitHub Actions: lint + test + migration lint on PR; deploy on merge (Vercel Git integration for SPA; SSH deploy to VPS for API) | this doc |
| Frontend | Vite+React SPA on Vercel; previews `*.preview.gammasummit.top` | ADR 0002/0003 |
| API | FastAPI + raw `asyncpg` on Hostinger VPS | ADR 0003 |
| DB | Supabase Postgres, tiered (T0 24-48h, T1 30d, T2 90d-1yr) | data-tiering.md |
| Cold storage | X10 Pro local + **R2 offsite (zero egress, DuckDB httpfs)** | backup-topology.md |
| Registrar/DNS | NameSilo registrar, Vercel DNS (keep; single registrar renewal) | this doc |
| Domain records (target) | apex/www → Vercel SPA · `api` → VPS A record · `*.preview` → Vercel CNAME | this doc |

## R2 connection plan (planning only — execute at build)

1. Cloudflare dashboard → R2 → create bucket `gammasummit-cold`.
2. R2 → Manage R2 API Tokens → **Object Read & Write**, scoped to that bucket →
   get `Access Key ID` + `Secret Access Key` + `Account ID` (never paste in
   chat; goes straight to `.env`).
3. `.env` keys (gitignored, mirrored in `~/.hermes/.env`):
   `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET=gammasummit-cold`.
4. Configure rclone remote (S3-compatible provider `Cloudflare R2`) with those
   env vars; `rclone.conf` chmod 600. (rclone already installed 2026-09-30.)
5. Jobs: monthly `rclone sync` of `leandata/`, `uw-archive/`, `t3/` + post-export
   triggers; verify = one real DuckDB read via `httpfs` (`SET s3_endpoint=
   <account>.r2.cloudflarestorage.com`) + checksum spot check.
6. Security: token scoped to one bucket, read-write only, never in git; rotation
   documented in security.md.

## GitHub plan (repo hygiene)

- Public repo `gammasummit`; `main` protected (PR + green Actions required).
- Secrets: `.env*` gitignored + a `.env.example` per service; GitHub Actions
  secrets for deploy keys; no credentials in workflow files; pre-commit hook
  scanning for key patterns (gitleaks).
- Migrations: `NNNN_*` SQL, applied by CI with lint (deny-default grants check).
- Releases: tagged `vN` → VPS release symlinks (existing deploy pattern).

## Execution order (when build opens)

1. GitHub repo + Actions skeleton (from scaffold) 
2. Vercel project wired to repo (previews working)
3. DNS records moved to target state (api subdomain etc.)
4. R2 bucket + token + rclone job
5. Then P1 build phases per ultraplan.
