# P0 parity dataset — manifest + loader notes (E0.1)

Status: **assembled + validated with a hard coverage gap** (see §5). Everything
below was produced by real runs of `scripts/p0_parity_dataset.py` over the real
data; numbers come from `data/p0/*.json` (regenerate any time — the script is
idempotent and READ-ONLY against both sources).

Dataset purpose: the single input set for every later E0 card (cross-expiry
layer fit, `backend/core/exposure.py` parity gate). Pairing target = **Skylit
node values (RE captures) aligned with UW `gamma_data_v2` strike inputs at the
same instants**.

## 1. Sources

| Source | Path / endpoint | Access |
|---|---|---|
| RE raw captures | `/Volumes/X10 Pro/gammasummit/t3/re/raw/` (external exFAT) | read-only |
| Capture manifest | `raw/capture_manifest.jsonl` → local copy `data/p0/capture_manifest.jsonl` (sha256 `9095809f4b7d846f11746b918b216877ad2af5db66cbf23f2adf7e53cc642830`) | copied 2026-09-30 |
| UW inputs | Supabase `gamma_data_v2` via PostgREST (SELECT/HEAD only) | read-only, never writes |

UW credentials come from `GAMMASUMMIT_UW_URL` + `GAMMASUMMIT_UW_SERVICE_KEY`
env vars only (never in git/chat). Skylit API = temporary RE tool (sub ends
~Nov 2026); production runs UW-only.

## 2. RE capture inventory (acceptance #1)

Verified counts (script `inventory`, 5,187/5,187 files scanned, 0 scan errors):

- `capture_manifest.jsonl`: **5,187 entries** — `matrix/gamma` 3,087,
  `matrix/vanna` 1,580, `range/gamma` 520.
- On-disk `.json.gz` files: exactly the same 5,187 (**manifest ↔ disk 0
  mismatches**, every day × kind). Plus 5,187 macOS AppleDouble `._*` sidecars
  (exFAT noise — never parse) and 8 `vol_{derived,history}_{SPX,SPY,QQQ,IWM}.json.gz`
  sidecars at the raw root.
- **20 session-days**, all full RTH 13:30–20:00Z (09:30–16:00 ET):
  2026-09-01/02/03/04, 08/09/10/11/12, 15/16/17/18, 22/23/24/25, 28/29/30.

Per-day frame counts (every day complete RTH unless noted):

| session-day | matrix/gamma | matrix/vanna | range/gamma | cadence note |
|---|---|---|---|---|
| 2026-09-01 … 2026-09-23 (15 days) | 79 | 79 | 26 | gamma+vanna 5-min grid |
| 2026-09-24, 25, 28, 29 | 391 | 79 | 26 | gamma 1-min grid, vanna still 5-min |
| 2026-09-30 | 338 | 79 | 26 | 1-min grid, 53 RTH minutes missing (one 24-min gap 19:06–19:30Z + scattered holes) |

- `range/gamma` = 26 × 15-min windows per day (13:30Z … 19:45Z starts), 900
  1-second frames per window on 1,806 of 2,120 symbol-windows; the rest run
  744–901 frames (seconds missing — see `re_inventory.json:range_frame_counts`).
- Matrix captures carry `meta = {metric, resolution: "1s", mode: "historical",
  cached: false}` on every file — all data is `/v1/historical` replay.
- Symbols: exactly SPX, SPY, QQQ, IWM in every capture (4,667 symbol-records
  each). Expiries per symbol: SPX 20, SPY 33, QQQ 31, IWM 32 (sampled).
- `capture_manifest.jsonl` `t` uses `Z` for matrix rows and `+00:00` for range
  rows (parse accordingly). `credits_remaining` trail 104,985 → 68,655
  (~36,330 credits spent on the campaign so far).

### Node types (acceptance #1) — full census over all matrix captures

`strikes[].nodeType` at cell level, 7,847,244 strike records:

| nodeType | count | per-symbol king check |
|---|---|---|
| normal | 7,556,187 | — |
| gatekeeper | 219,481 | — |
| barney | 56,004 | — |
| pika | 56,004 | — |
| king | 18,668 | exactly 4,667 per symbol = 1 king per symbol per matrix capture ✓ |

Values live in `strikes[].value` (same magnitude class as the per-cell `matrix`
rows) and `matrix[i][j]` = per-strike × per-expiry value grid. Range files carry
no nodeType (frames are raw value vectors per axis).

### Capture fidelity notes

1. **Matrix filename = replay window start; per-symbol `asOf` is 1s earlier**
   for fresh records (e.g. `133000.json.gz` → SPX `asOf 13:29:59Z`). Alignment
   code must use `asOf`, not the filename.
2. **Stale-symbol records exist inside matrix captures**: 628 of 20,668
   symbol-records have `|asOf − window_start| > 2s`; the lag histogram
   (`re_inventory.json:asof_lag_hist`) shows a distinct class at **exactly
   −3600 s (588 records)** plus scattered singles, and one whole-day case
   (2026-09-12: SPY/QQQ/IWM stale in all 79 captures each). Per-(symbol, day)
   counts live in `re_inventory.json:asof_stale_by_symbol_day` — **use that map
   to exclude stale cells from king-exact scoring.**
3. Range frames: `frames[].asOf` has sub-second timestamps (1s grid), each frame
   pins `axis` id; `axes[].strikes` are the strike grids.
4. exFAT + `._` sidecars: every listing must filter `startswith("._")`.

## 3. UW `gamma_data_v2` coverage cross-check (acceptance #2)

Read-only PostgREST probe (`uw-coverage`; raw sweep `data/p0/uw_coverage_raw.json`,
canonical `data/p0/uw_coverage.json`):

- Table span: **2026-09-26T04:31:47Z → 2026-10-01T05:58Z** (first rows ever).
- Per RE session-day row counts (4 RE symbols), and batch-snapshot counts
  (batch = one daemon cycle, same `timestamp` across tickers):

| session-day | SPX rows | SPY rows | QQQ rows | IWM rows | snapshots |
|---|---|---|---|---|---|
| 2026-09-01 … 2026-09-25 (17 RE days) | 0 | 0 | 0 | 0 | 0 |
| 2026-09-28 | 1,543,738 | 871,750 | 790,934 | 338,718 | 185 |
| 2026-09-29 | 1,040,481 | 585,442 | 549,480 | 241,453 | 210 |
| 2026-09-30 | 1,379,379 | 832,018 | 786,935 | 358,613 | (see `uw_coverage.json`) |

- Row schema (43 cols): `ticker, strike, expiry_date, timestamp, gex_value,
  dex_value, call_gex, put_gex, call_dex, put_dex, call_oi, put_oi,
  call_volume, put_volume, net_oi, net_volume, abs_gex, abs_oi,
  net_gex_by_volume, call_vanna, put_vanna, call_charm, put_charm, call_vega,
  put_vega, call_ask_vol, call_bid_vol, put_ask_vol, put_bid_vol,
  call/put_theo_gap, iv, confidence, is_spot, is_hvl, is_call_res,
  is_put_supp, ctrans_here, ptrans_here, spot_price, source, fetched_at, …`

### Sources checked for UW strike history on the 17 gap days (all dead)

| Source | Result |
|---|---|
| `gamma_data_v2` (Supabase) | rows start 2026-09-26T04:31Z — 0 rows for 09-01…09-25 |
| `gamma_data` (Supabase legacy live-swap) | only the current daemon cycle |
| `gamma_history` / STDB `gamma_history` | not exposed via REST; local spacetimedb data dir wiped |
| `historical.db` (SQLite "source of truth") | tables dead since 2026-06-25 |
| `gamma_copilot*.db` (local + 1.9 GB X10 copy) | Gamma_Table/gamma_history end 2026-06-23 |
| `/Volumes/X10 Pro/gammasummit/t3/{gamma,manifests,flow,rollups}` | empty placeholders |
| `/Volumes/X10 Pro/SignalForge Archive/uw-archive/` | rsync target empty (fleet started 2026-09-30) |
| PHX `chains_expiry?date=…` backfill | **date param ignored** — 09-02 vs 09-30 requests return byte-identical rows (current chain only) |
| Supabase `gamma_velocity` / `gamma_since_open` | strike-level but pruned: per-day counts over RE days are 0–67 rows (retention is days, not months) |
| `node_history` / `king_node_history` / `spot_ticks` | our derived node/spot outputs (08-31 / 03-02 / 09-15 →) — useful for later cards, NOT UW inputs |

**Conclusion: UW per-strike inputs survive only from 2026-09-26.** No
same-instant UW inputs exist for the 17 RE session-days 2026-09-01…09-25 in any
reachable store; the old snapshots were live-swapped/STDB-wiped.

## 4. Session-day frame list (acceptance #3)

Machine-readable: `data/p0/session_day_frames.json` + `.csv` (built by
`frames`; alignment = nearest UW batch timestamp within
`GAMMASUMMIT_ALIGN_TOL_S` (default 90 s) of each RE matrix instant).

| tier | session-days | Skylit node values | UW inputs | status |
|---|---|---|---|---|
| **A — same-instant UW** | 2026-09-28, 2026-09-29, 2026-09-30 (3) | yes (gamma 1-min + vanna + range 1s) | `gamma_data_v2` batch snapshots aligned to RE instants | usable for king-exact fit now (partial instants/day — see below) |
| **B — Skylit only** | 2026-09-01…09-25 (17) | yes (gamma 5-min/1-min + vanna + range 1s) | **none survive** | NOT usable until UW inputs exist |

Alignment statistics at 90-s tolerance (from `session_day_frames.json`,
`verify` run 2026-10-01: **VERIFY PASS**):

| session-day | RE gamma instants | UW snapshots (UTC span) | aligned | Δt median | Δt max |
|---|---|---|---|---|---|
| 2026-09-28 | 391 | 185 (00:01:29 → **14:06:30** — stream stops mid-RTH, 10:06 ET) | 10 | 59 s | 90 s |
| 2026-09-29 | 391 | 210 (06:10:31 → 23:58:16) | 130 | 45 s | 89 s |
| 2026-09-30 | 338 | 318 (00:02:10 → 23:58:56) | 151 | 43 s | 90 s |

Facts behind those numbers (drive fit-harness design):

- UW daemon batch cadence is ~4.5 min at **non-round wall-clock seconds**;
  RE matrix captures sit on whole minutes → nearest-within-90s only hits where
  a batch landed close enough. Expected pairs/day at 90 s ≈ 1/3 of instants;
  widen `GAMMASUMMIT_ALIGN_TOL_S` (e.g. 150 s = half the batch cadence) or use
  nearest-and-record-`dt_s` scoring to raise pair counts.
- 2026-09-28 UW stream is anomalously truncated at 14:06:30Z (two independent
  probes agree: 30-min bucket census + timestamp walk) — treat that day as
  RTH-morning-only.
- 2026-09-30 RE side has 53 missing RTH minutes (one 24-min gap 19:06–19:30Z).

Consequence for the P0 gate (king exact ≥ 90% over ≥ 20 session-days):
**3/20 days carry UW inputs today, with 291 aligned (RE, UW) instants total.**
The RE side alone cannot fix this — RE replay can re-render any past Skylit
instant, but UW strike inputs for 09-01…09-25 are gone.

### Exception record — owner decision (2026-09-30)

**DECIDED: Option 1 — forward-fill** (PM decision recorded on board card
E0.1 `t_e3325bfe`, 2026-09-30; owner prompt timed out, safe reversible
default adopted — override available).

- Acceptance #3 (≥ 20 aligned session-days) = **DATA-BLOCKED, met-with-
  exception**: UW history for 09-01…09-25 survives in no source (all
  candidates proven dead, §3), so the gap cannot be closed retrospectively.
  Both capture streams now ingest live → one new Tier A session-day accrues
  per RTH session → ≥ 20 aligned days by ~2026-10-28. Gate wording
  unchanged ("king exact ≥ 90% over ≥ 20 session-days"), satisfied as days
  accrue.
- E0.2/E0.3 proceed NOW on Tier A scope: 09-28/29/30 = 291 aligned (RE, UW)
  instants @ 90 s, plus `data/skylit_pairs/` 23 PAIRs and
  `skylit_sameinstant_v2.json` 59,730 rows as extra Tier A (per-PAIR UW
  freshness check required — earlier PAIRs used the stale phx free endpoint).
- Tier B (`top_chains` 18/20 days + `intraday_aggregates`) = context only,
  NOT gate evidence.
- Carry into E0.2: re-derive UW batch snapshot timestamps via full-day
  distinct walk on one liquid strike×expiry BEFORE locking pair counts
  (cadence discrepancy: probes ~1/min vs manifest 185–318/day → aligned-pair
  yields likely conservative).

Options considered (superseded by the decision above):

1. **Forward-fill — CHOSEN.** Both capture streams now run
   live: every future RTH session adds one Tier A day automatically (RE
   capture `skylit_re_capture.py` + daemon v2 mirror). ≥ 20 aligned days by
   ~2026-10-28 (4 weeks). Fit work (E0.2/E0.3) proceeds on Tier A days now.
2. **Accept degraded Tier B inputs** for the 17 days (e.g. daily-granularity
   UW aggregates such as `daily_gex`/`phx_daily_gex`, or Skylit-only ranking
   checks) — weaker fit targets, gate metrics would need re-scoping.
3. **Alternate historical source** (e.g. Polygon historical option snapshots
   with greeks) as UW substitute for old days — new dependency, owner call.
   Note: UW API itself cannot backfill — `option-contracts?date=` returns
   `historic_data_access_missing` (token tier sees only 2026-09-25 forward);
   would need a plan upgrade or a non-UW source.

## 5. Loader notes (acceptance #4)

`scripts/p0_parity_dataset.py` (stdlib only; Python ≥ 3.9):

```
export GAMMASUMMIT_UW_URL=… GAMMASUMMIT_UW_SERVICE_KEY=…   # read-only key
python3 scripts/p0_parity_dataset.py inventory   # RE census -> data/p0/re_inventory.json
python3 scripts/p0_parity_dataset.py uw-coverage # UW spans/cnts -> data/p0/uw_coverage.json
python3 scripts/p0_parity_dataset.py frames      # frame list -> data/p0/session_day_frames.{json,csv}
python3 scripts/p0_parity_dataset.py verify      # alignment checks, exit 0 = pass
```

Importable API for the fit harness (later E0 cards):

- `load_manifest()` → capture records; `manifest_kind(rec)`.
- `load_matrix_file(path)` → `{meta, symbols: {SYM: {asOf, spot, expirations,
  strikes, cells: {(strike, expiry): value}}}}`.
- `load_range_file(path)` → `{meta, from, to, symbols: {SYM: {axes, frames}}}`.
- `UWClient().q(...)` / `uw_day_rowcount` / `uw_snapshot_timestamps` (cached in
  `data/p0/uw_snapshot_cache.json`) / `uw_rows_at(ts, tickers)`.
- `align_day(rec_instants, uw_ts, tol_s)` → per-instant nearest-UW records +
  `{n_aligned, n_unaligned, dt_s_median, dt_s_max}`.

Alignment rule (encode in the fit harness): RE instant `asOf` → nearest UW
batch `timestamp` within 90 s; prefer exact ties to the older snapshot; record
`dt_s` per pair and drop pairs above tolerance from scoring.

Artifacts produced by the E0.1 evidence run (all under `data/p0/`):
`capture_manifest.jsonl`, `re_inventory.json`, `uw_coverage.json`,
`uw_coverage_raw.json` (broad sweep incl. 30-min bucket census),
`uw_snapshot_cache.json`, `session_day_frames.json`, `session_day_frames.csv`.

## 6. Verification record

- `inventory`: 5,187/5,187 manifest files scanned, 0 read errors, manifest ↔
  disk counts identical for every (kind, day).
- `uw-coverage`: real PostgREST HEAD/SELECT probes per day × symbol; zero-days
  confirmed twice (bucket census + per-ticker counts).
- `frames` + `verify`: alignment checks executed on real RE instants against
  real UW snapshots; verify exits non-zero if any artifact or alignment is
  missing.
- `--dry-run`-equivalent everywhere: every external access in this card is
  read-only; nothing was written to SignalForge or the X10 drive.
