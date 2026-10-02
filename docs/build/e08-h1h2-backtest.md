# E0.8 — H1/H2 backtest + per-contract daily history (UW remediation)

Generated: 2026-10-02 · card `t_3568ab3b` · clean-room (UW PHX + leandata RE archive + Skylit
public rollup LISTS only — never Skylit internals) · all numbers from real runs in
`data/e08/` · sample sizes reported everywhere.

Hypotheses under test (from `skylit-ticker-selection-model.md` §6):

- **H1** — contract-level RVOL (`min_rvol=2` vs 10d baseline, `min_avg_volume=100`) +
  OI-change (≥500 or ≥25%) recovers Skylit unusual sets at **P@50 ≥ 0.5**
- **H2** — premium percentile vs own trailing 20d ranks "surprising" names **above raw
  premium** within the same day (vs truth B per day)

Ground truth = Skylit `/v1/contract/unusual-volume` + `/v1/contract/unusual-oi` top-100
rows/day (B = union of their tickers), re-pulled for 9 more days via
`scripts/e07_skylit_observed_pull.py` (117 credits, 0x429/402; Skylit rollups reach back
at least to 2025-10-15 — probed — but return 0 rows for 2022).

Full machine-readable numbers: `data/e08/h1h2_backtest_report.{json,md}`.

## 1. Verdicts

| H | verdict | evidence |
|---|---|---|
| H1 | **partially supported / not verifiable at 610-ticker scale on current UW capture** | uncensored 54-ticker track: P@25 0.56–0.76 on all mature days, P@50 0.52 on the one fully-mature day (K=50≈universe-size caveat); 610-ticker top_chains track: P@50 0.26–0.38 vs B — target missed; root causes measured (capture gap + broken per-row OI deltas), not hand-waved |
| H2 | **not supported** | surprise percentile ≈ raw premium on the uncensored track (P@25 0.48–0.68 vs 0.48–0.64) and strictly below raw premium every day on the 610 track (@50 0.24–0.36 vs 0.30–0.44) |

## 2. Track capabilities (what each dataset can actually test)

### T1 — leandata `options_eod` (mechanics only, no P/R possible)

138,071 contract-day rows (SPY/QQQ), 4,452 contracts, 3,642 with ≥11 obs,
95,401 contract-days scored. RVOL flag rate 15.1%; median RVOL 0.70, p90 5.76;
H2 percentile mean 0.53 (≈ uniform — sanity pass).

**No P/R here, honestly:** Skylit daily rollups return 0 rows for 2022 (probed
2022-03-15: 7/7 endpoints empty) and the rich leandata window is 2021-11→2022-11.
`options_eod` also has **no open-interest columns at all** — the OI half of H1 is
untestable on leandata, full stop.

### T2 — leandata `options_minute` (54 liquid tickers, 2026-09-15..25) vs Skylit truth

53,860 per-contract daily aggregates built (`scripts/e08_leandata_contract_daily.py`,
minute bars → day volume/premium; no OI, no side split in source). Coverage is lumpy:
09-15/16/17 carry 6 rows/day (scoring skipped — ranks would be artifacts), dense from
09-18 (1.6k→12.5k contract-days/day). Baselines need ≥5 prior obs (documented deviation;
strict-10 fires 0 flags in this 10-session window).

Mature days (flags firing), vs market-wide B (truth n = 56–68 tickers/day; 19–28 of them
inside the 54-ticker covered universe):

| day | flags (rvol) | h1_rvol P@25 | h2_contract P@25 | h2_ticker P@25 | premium_raw P@25 | h1_rvol P@50 |
|---|---|---|---|---|---|---|
| 09-22 | 1 | **0.76** | 0.76 | 0.64 | 0.64 | 0.46 |
| 09-23 | 4 | **0.68** | 0.56 | 0.56 | 0.56 | 0.46 |
| 09-24 | 32 | **0.56** | 0.48 | 0.48 | 0.48 | 0.36 |
| 09-25 | 463 | **0.64** | 0.60 | 0.68 | 0.60 | **0.52** |

- H1-RVOL clears P@25 ≥ 0.5 against B on every mature day, and P@50 = 0.52 on the one
  day with a full mature baseline — **but K=50 over a 54-ticker universe ≈ truth
  prevalence** (in-universe recall at @25 is 0.56–0.74), so @25 is the informative cut.
- H2 ≈ raw premium, never clearly above it (09-25 ticker-surprise 0.68 vs 0.60 is the
  only win; 09-22/23/24 tie or lose). H2's "above raw premium" claim not supported.

### T3 — UW `top_chains` 610-ticker capture, replay days vs Skylit truth (headline test)

This is the only track that can express "P@50 vs unusual sets" at the intended scale.
Contract-volume history here is **censored** (top-15 per ticker/day, 2 sorts); the per-row
`oi`/`prev_oi` pair turned out to be worse than censored — see §3.

| day | truth B | h1_union P@50 | h1_rvol vs Bvol @50 | h1_oi vs Boi @50 | h2_surprise @50 | premium_raw @50 |
|---|---|---|---|---|---|---|
| 09-29 | 49 | 0.38 (19 hits) | 0.08 | 0.28 | 0.36 | 0.44 |
| 09-30 | 59 | 0.34 (17) | 0.16 | 0.28 | 0.32 | 0.38 |
| 10-01 | 54 | 0.26 (13) | 0.02 | 0.22 | 0.24 | 0.30 |

@25 cuts: h1_union 0.60/0.52/0.36 · h1_oi 0.48/0.44/0.32 · h2 0.48/0.52/0.32 ·
premium 0.56/0.64/0.44. Sample sizes: 610 tickers ranked/day, 166–188 rvol flags +
2,028–2,204 oi flags/day, truth 49–59 tickers (100 unusual-volume + 100 unusual-oi rows).

**Target P@50 ≥ 0.5: not met on this track.** Even raw premium rank (E0.7's best scorer)
sits at 0.30–0.44 vs B — B is an unusualness set, not a premium list, so this is the
harder truth set by construction.

Contract level (the §7-gap-1 smoking gun): only **9–26 of the 200 truth rows/day are
captured at all** by top_chains (top-15 truncation); on those captured, our flags hit
P≈0.005, R≈0.02–0.055.

## 3. Root causes measured (why H1 can't be settled on current UW capture)

1. **Capture gap.** Skylit's top-100 unusual contracts/day barely intersect top_chains:
   21/26/9 of 200 truth rows present on the replay days. Unusual contracts are ranked by
   *relative* volume / OI change — they usually aren't a ticker's top-15 by absolute
   volume/OI. Contract-level recall ceiling on top_chains ≈ 0.05–0.13.
2. **Per-row OI deltas are structurally wrong.** `captured_truth_diag` (report §contract
   level) shows Skylit publishing oiChange of ±15k–42k for contracts whose top_chains
   `oi - prev_oi` reads ±1–178 on the same date (e.g. `NVDA261120C00230000`: Skylit
   −42,057 vs our +172). top_chains `prev_oi` is not a day-over-day OI snapshot → the
   OI half of H1 cannot be computed from it at all.
3. **Date-label noise.** top_chains `trade_date=2026-10-01` rows carry 09-29-expiry SPY
   0DTE contracts at 821k volume (and `fetched_at` precedes `trade_date` in samples) —
   same-day alignment with Skylit truth is approximate; measured P/R inherits this noise.
4. **PHX `chains_expiry?date=` is a no-op** (verified: identical rows with and without
   the param, and for two different dates) — no historical backfill via the live chain
   endpoint. History can only accumulate forward, one session at a time. Hence
   deliverable 2.

## 4. Deliverable 2 — per-contract daily persistence (the remediation)

- **Migration** `db/migrations/0002_contract_daily_stats.sql` (expand-only,
  migration-lint clean): `contract_daily_stats` + `underlying_daily_stats` in the
  ContractStats/UnderlyingStats public row shapes + `prev_oi` (H1 needs raw deltas) and
  provenance columns. Honest NULLs for fields UW does not serve per-contract
  (sweep/multi-leg splits, trade_count).
- **Collector** `scripts/e08_contract_daily_persist.py` (dry-run default; 4 unit tests in
  `backend/tests/test_e08_contract_daily_persist.py` green): full-chain capture per
  ticker/expiry from PHX `chains_expiry` (the 25-key rows incl. volume, oi, prev_oi,
  bid/ask/mid split) + spot from `price/v2`, universe = UW-captured tickers (5-day
  top_chains union + T0/T1). Writes parquet `data/e08/contract_daily/dt=YYYY-MM-DD/`
  ALWAYS, and with `--execute` an **insert-only** PostgREST upsert
  (`resolution=ignore-duplicates` — an existing (date, occ) row is never overwritten).
- **DB DDL application is a manual one-liner** (blocked from automation here: no Supabase
  SQL path on this fleet — the VPS duckle pipelines are REST-only and no access token /
  DB password exists in any env): paste `0002_contract_daily_stats.sql` into the Supabase
  SQL editor (or `supabase db query` after `supabase link`), then the scheduled run's
  `--execute` activates. Until then the parquet plane carries the history.
- **Schedule**: daily cron `e08-contract-daily-persist` (job `3e3057b08b4c`, Mon–Fri
  23:35 local, `no_agent` script `e08_persist_tick.py`) runs the collector with
  `--execute` for the latest completed session — history accumulates going forward,
  which is exactly what H1 needs (RVOL baselines + real per-day OI).
- **First full run (verified, 2026-10-02):** 610 tickers (exactly the UW captured
  universe), **719,573 per-contract rows + 610 underlying rows**, 8,654 PHX calls
  @~2.2 rps effective, 0 auth fallbacks, 0 errors, 64 min.
  `data/e08/contract_daily/dt=2026-09-30/` — session label derived from data, not
  calendar: the run's max `last_tape_time` = `2026-09-30T21:36:18Z` proves the served
  snapshot is the 09-30 session (PHX chains is one session stale as of this capture),
  so rows were relabeled `2026-10-01` → `2026-09-30` (dte recomputed; the original
  `dt=2026-10-01/` output is preserved verbatim as the run record). The collector now
  self-corrects labels to tape ground truth on every run (`label_source` in
  `run_report.json`), so a lagging endpoint can never poison the history.

## 5. Deliverable 3 — `e07_validate.py` re-run with richer features

`scripts/e08_uw_features_rich.py` adds the H1/H2 contract aggregates (censored rvol max,
flag counts, |Δoi| sum, premium pctile-20d) to the E0.7 per-ticker rows; `e07_validate.py`
gained `--features-dir/--features-prefix/--out-stem/--rank-field` (defaults unchanged).
Reports in `data/e08/validation_report_rich_{h1,h2,blend}.*` — V3 = vs unusual sets B,
V4 = vs attention set C, 3 replay days × (100+100 truth rows, 49–59/58–70 truth tickers):

| rank | V3 P@50 (09-29/30, 10-01) | V4 P@50 | V2 P@25 vs top-premium A |
|---|---|---|---|
| E0.7 `score_v0` (baseline) | 0.28 / 0.34 / 0.22 | 0.36 / 0.40 / 0.36 | 0.92–1.00 (premium ceiling) |
| rich `score_h1` | 0.34 / 0.30 / 0.20 | 0.40 / 0.32 / 0.32 | 0.60 / 0.48 / 0.56 |
| rich `score_h2` | 0.08 / 0.16 / 0.08 | 0.10 / 0.18 / 0.10 | 0.28 / 0.12 / 0.20 |
| rich `score_v0_rich` | **0.36 / 0.36 / 0.26** | **0.44 / 0.40 / 0.42** | 0.52 / 0.44 / 0.44 |

The richer blended features improve on E0.7's score_v0 by +0.02..+0.08 at V3@50 and
+0.04..+0.08 at V4@50 — real but modest, and still below 0.5. The blend still dilutes the
premium ceiling on truth A, consistent with E0.7's "never blend the premium rank" rule.

## 6. Provenance & rules

- leandata `/Volumes/X10 Pro/leandata` read-only throughout (byte-level writes only to
  the repo's `data/e08/`).
- Skylit API used strictly as the temporary RE truth source: 132 credits this card
  (probe 2022-03-15 13cr, depth probes 18cr, 9 truth days 117cr minus overlaps), paced
  ≥3s, 0x429/402. No Skylit internals claimed — only its published top-100 lists.
- UW PHX reads for features/truth alignment; the only writes anywhere are the new
  `0002` tables (insert-only) and repo files. `top_chains`/other existing tables never
  modified.
- Artifacts: `data/e08/leandata_contract_daily.parquet` (191,931 rows),
  `data/e08/h1h2_backtest_report.{json,md}`, `data/e08/uw_features_rich_*.json`,
  `data/e08/validation_report_rich_*.{json,md}`, `data/e08/contract_daily/dt=2026-09-30/`
  (719,573 contract rows, first full capture), `data/e08/topchains_*.json` (42-day UW cache).
