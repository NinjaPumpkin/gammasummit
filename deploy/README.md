# deploy/

Production topology and runbooks-in-code.

## Target topology

| Piece | Where | Form |
|-------|-------|------|
| ingest daemon | VPS (Hostinger srv1234213) | systemd `gammasummit-ingest.service` |
| job workers | VPS | systemd timers (`gammasummit-rollups.timer`, `gammasummit-retention.timer`) |
| API | VPS | docker container behind reverse proxy |
| frontend | VPS or static host | built assets |
| hot DB | Supabase (slim plan) | external |
| cold storage | external disk + B2/R2 | Parquet |

## Layout

```
deploy/
├── systemd/    # gammasummit-<role>.service / .timer units
├── docker/     # Dockerfiles, compose for API
└── vps/        # provisioning notes, release layout, env template
```

## VPS conventions (inherited, proven)

- Release layout: `/opt/gammasummit/releases/<ts>` + `current` symlink
- Env file: `/etc/gammasummit/env` (mode 600, never in git)
- Python 3.10.12 on the VPS — code must stay 3.10-compatible
- Services fail fast on bad config; restart ≠ reload for nginx changes

## Hard rules

- Every new service ships with: health check (deep = data freshness),
  graceful shutdown (finish current batch on SIGTERM), logs to journald.
- Deploy = new release dir + symlink flip + service restart. No in-place edits.
- Rollback = flip `current` back + restart.
- Migrations before writer restart, always (`../db/README.md` rule 1).
