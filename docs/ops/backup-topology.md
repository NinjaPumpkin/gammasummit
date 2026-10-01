# Backup topology — what survives an unplugged disk

Owner question 2026-09-30: what happens if the X10 external disk gets
unplugged? Should DB backups live on the MacBook Air and MacBook Pro?

Answer: yes — with role-based copies (they have different sizes), plus the
offsite copy that covers the case the laptops can't (house fire / theft takes
X10 + both MacBooks at once).

## What an unplugged X10 actually breaks

| System | Impact |
|---|---|
| Live product (Supabase, VPS ingest, website) | **none** — hot tier never touches X10 |
| Backtests / T3 / history reads (DuckDB) | fail until remount (read-only, no data loss) |
| RE capture burn | used to stall — **now falls back to local staging** (`data/re-staging/`), rsync to X10 when mounted |
| uw-archive pull | already skips safely when unmounted (checks mount first) |
| Nothing is lost | provided the copies below exist — which is this plan |

## Copy roles (3-2-1: 3 copies, 2 media, 1 offsite)

| Copy | Holds | Cadence |
|---|---|---|
| **X10 Pro** (primary) | full cold tier: `leandata/` (152 GB), `uw-archive/`, `gammasummit/t3/`, legacy, RE raw | live writes |
| **MacBook Air** | **compact-critical set**: Postgres logical dumps (weekly, compressed GBs), code repos + git bundles, export manifests, fit constants, docs, encrypted config backups | weekly rsync/launchd |
| **MacBook Pro** | compact-critical + **t3 subset** (last 90d Parquet + RE fit datasets) — the "keep working through an X10 outage" copy | weekly + post-capture |
| **B2/R2 (offsite)** | full archives (`leandata/`, `uw-archive/`, `t3/`) — the only copy that survives fire/theft | monthly + after big exports |
| VPS | live DB + UW heavy archive source | continuous |

Rule: **compact-critical fits on both laptops** (target < 20 GB) so it can be
everywhere; heavy archives respect laptop disk budgets (Pro gets the subset
that keeps research alive).

## Laptop sizing guardrails

- Before any laptop copy lands: check free space (`df -h`), keep ≥ 100 GB
  headroom; skip cleanly when tight (same pattern as the uwarchive mount check).
- MacBooks are not archival storage — they churn (reinstalls, travel). The
  authoritative copies are X10 + B2/R2; laptops are the convenience layer.

## Cloud object storage instead of laptop copies? (owner 2026-09-30)

Yes for the offsite/authoritative layer — and it upgrades the architecture:
**DuckDB `httpfs` reads Parquet straight from object storage** (extension
already adopted in the audit) → cold tier queryable from ANY machine with no
X10 attached, and `cache_httpfs` keeps hot slices local.

Monthly cost at ~370 GB (leandata 152 + migration 162 + archive 5.5 + t3):

| Option | Storage/mo | Egress on full restore | Remote DuckDB reads | Verdict |
|---|---|---|---|---|
| **Cloudflare R2** | ~$5.55 | **$0** | free (zero egress) | ✅ **preferred** — queryable cold tier |
| **Backblaze B2** | ~$2.20 | free up to 3× stored, then $0.01/GB | cheap | ✅ cheapest pure archive |
| AWS S3 Standard | ~$8.50 | **$0.09/GB ≈ $33** per full restore | costly | ❌ 4× B2 + punitive egress |
| AWS Glacier Deep Archive | ~$0.37 | $0.02/GB + 12–48h wait | unusable (slow) | ❌ dead-archive only |

Revised topology (simpler than 4 copies):

| Copy | Role |
|---|---|
| **X10** | fast local cold tier (backtests, RE datasets) |
| **R2 (or B2)** | authoritative offsite + **remote-queryable** (DuckDB httpfs) |
| **MacBook Pro compact set** | optional convenience (code + manifests + fit constants — <5 GB); skip Air entirely if you want less to manage |

Laptops become optional, not required. Rule unchanged: quarterly restore drill
(test a real Parquet read from R2 via DuckDB — one query proves the chain).

## To wire (planning mode — listed for P1/P5f execution)

1. `scripts/backup_compact_critical.sh` — dumps + manifests + git bundles →
   Air + Pro (launchd weekly, skip-if-tight).
2. B2/R2 sync job for `leandata/` + `uw-archive/` + `t3/` (rclone, monthly +
   post-export triggers).
3. RE capture staging mover: `rsync data/re-staging/` → X10 when mounted.
4. Restore drill quarterly (a backup not restore-tested is a hope).
