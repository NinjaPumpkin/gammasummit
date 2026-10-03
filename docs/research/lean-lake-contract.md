# lean-lake-contract — leandata → ContractStats-shape handoff (E0.8)

Card t_1fc1ffc8. Field-mapped per-contract daily aggregates from the leandata
RE reference archive, shaped like Skylit's `ContractStats` row
(`docs/re/skylit-docs/llms.txt` → GET /v1/contract/bulk/stats) so the
ticker-selection H1/H2 tests and later UW accumulation share one contract.

## Build

```
python3 scripts/e08_leandata_contract_daily.py            # build + report
python3 scripts/e08_leandata_contract_daily.py --out <p>  # custom out
```

- Source: `/Volumes/X10 Pro/leandata/parquet` — **READ-ONLY** (standing rule).
- Out: `data/e08/leandata_contract_daily.parquet` +
  `data/e08/leandata_contract_daily_report.json`.
- Verified run 2026-10-02: 191,931 rows total.
  - `source='eod'` (options_eod): 4 files, 138,071 rows, SPY+QQQ only,
    2021-11-22 → 2026-09-24 (thin windows — coverage is spotty).
  - `source='minute'` (options_minute aggregated to day): 54 files,
    21,058,870 raw minute rows → 53,860 contract-days, 54 tickers,
    2026-09-15 → 2026-09-25 (only ~10 sessions — RVOL baselines are short).

## Field map (ContractStats-shape ← leandata)

| output col | eod source | minute source |
|---|---|---|
| `occ` | derived bare OCC `{ticker}{YYMMDD}{C|P}{strike*1000:08d}` | `occ` column |
| `ticker` | `ticker=` path segment | `ticker=` path segment |
| `expiry` | `expiration` (date part) | `expiry` |
| `right` | `right` CALL/PUT → C/P | `right` → C/P |
| `date` | `created` date part | `t` date part |
| `volume` | `volume` | sum(`v`) |
| `trade_count` | `count` | sum(`n`) |
| `premium` | `close*volume*100`; fallback `mid(bid,ask)*volume*100` when `close<=0 & vol>0` | sum(`v*c*100`), zero-price bars contribute 0 |
| `close_price` | `close` (mid fallback as above) | volume-weighted `c` (v*c sum / v sum) |
| `bid`, `ask` | `bid`, `ask` | NULL (no quote columns in minute bars) |
| `oi`, `prev_oi`, `bid_volume`, `ask_volume`, `mid_volume` | NULL | NULL |

## Honest gaps (NULL by design, not dropped)

`oi`, `prev_oi`, `bid_volume`, `ask_volume`, `mid_volume` are NULL in every
row: neither leandata source carries open interest or execution-side splits.
Premium columns are documented **proxies** (`px * vol * 100`), not vendor
premium. Skylit's own `ContractStats` has richer fields (IV, 30D baselines);
absent fields must not be invented — fill from UW `gamma_data_v2` /
top_chains accumulation (sibling card t_5b4a2147) when available.

## Consumers

- `data/e08/h1h2_backtest_report.{json,md}` — H1 (RVOL+OI) / H2 (premium
  surprise) tests vs Skylit Flowseeker daily lists (t_5b4a2147).
- Any future contract-level RE against Skylit `/v1/contract/bulk/stats`
  (SKYLIT_API_KEY = temporary RE tool, sub ends ~Nov 2026; production is
  UW-only).

## Provenance rules

- leandata tree stays read-only; local staging (`data/leandata-parquet/`)
  merges back via `scripts/leandata_x10_merge.py --execute` only.
- Gap lists `data/missing_*.txt` + request ledger
  `docs/data/leandata-pull-manifest.json` track extraction coverage;
  do not treat the parquet as complete history.
