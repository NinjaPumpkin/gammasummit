# Skylit API archive — coverage + credit ledger

Generated: 2026-10-03T01:35:41.521586+00:00 by `scripts/skylit_api_archive.py coverage`.
Archive root (active): `/Volumes/X10 Pro/gammasummit/skylit_api` — X10 healthy
X10 target: `/Volumes/X10 Pro/gammasummit/skylit_api`

## Credit ledger (honest)

- Credits spent (logged sum): **45473**
- Credits spent (balance math, ground truth): **45517** (opening 68611 → remaining 23094)
- Credits remaining (last measured header): **23094**
- Reserve floor: **5000** (ladder stops there)
- Rate-limit incidents: **0**

## Pulls by endpoint

| endpoint | pulls | cost/call |
|---|---|---|
| heatmap | 401 | 1 cr |
| historical | 8587 | 5 cr |
| historical/range | 78 | 25 cr |

## Coverage by day

| date | pulls |
|---|---|
| 2023-03-28 | 1 |
| 2023-06-13 | 1 |
| 2023-09-13 | 1 |
| 2024-03-04 | 390 |
| 2024-03-05 | 390 |
| 2024-03-08 | 391 |
| 2024-03-11 | 390 |
| 2024-03-12 | 390 |
| 2024-08-01 | 390 |
| 2024-08-02 | 390 |
| 2024-08-05 | 390 |
| 2024-08-06 | 390 |
| 2024-08-07 | 390 |
| 2025-01-15 | 1 |
| 2025-04-04 | 390 |
| 2025-04-07 | 390 |
| 2025-04-09 | 390 |
| 2025-04-10 | 390 |
| 2025-04-15 | 1 |
| 2025-08-17 | 1 |
| 2025-12-15 | 1 |
| 2026-02-16 | 1 |
| 2026-04-15 | 1 |
| 2026-06-15 | 1 |
| 2026-08-17 | 1 |
| 2026-09-15 | 1 |
| 2026-09-28 | 1064 |
| 2026-09-29 | 1064 |
| 2026-09-30 | 1064 |
| 2026-10-02 | 269 |
| 2026-10-03 | 132 |

## Coverage by symbol (pulls mentioning symbol)

| symbol | pulls |
|---|---|
| SPY | 7119 |
| SPX | 7119 |
| QQQ | 7119 |
| IWM | 7119 |
| AAPL | 397 |
| AMD | 397 |
| NVDA | 397 |
| TSLA | 397 |
| META | 397 |
| MSFT | 397 |
| GOOGL | 397 |
| GOOG | 397 |
| AMZN | 397 |
| NFLX | 397 |
| COIN | 397 |
| PLTR | 397 |
| INTC | 396 |
| MU | 396 |
| AVGO | 396 |
| SMCI | 396 |
| BABA | 108 |
| BAC | 108 |
| CRWD | 108 |
| CRWV | 108 |
| CVNA | 108 |
| DRAM | 108 |
| F | 108 |
| GLD | 108 |
| GME | 108 |
| HOOD | 108 |
| HYG | 108 |
| IREN | 108 |
| KRE | 108 |
| LQD | 108 |
| MARA | 108 |
| MRVL | 108 |
| MSTR | 108 |
| NIO | 108 |
| NKE | 108 |
| NOW | 108 |
| ORCL | 108 |
| PFE | 108 |
| PYPL | 108 |
| RIVN | 108 |
| SMH | 108 |
| SNAP | 108 |
| SOFI | 108 |
| SPCX | 108 |
| TLT | 108 |
| TSM | 108 |
| VIX | 108 |
| WBD | 108 |
| XLE | 108 |
| XLF | 108 |
| XLU | 108 |

Parquet-mirror rows flattened so far: **438579136**

## Manifest

- `pull_manifest.jsonl`: 9066 records (ts, endpoint, params, credits, rows, sha256) — idempotency key = pull_id
- `credit_ledger.jsonl`: 9068 records
- Rate discipline: pacing at <=50% of 120 rpm with jitter; stop-on-first-sign on any 429/403; daily caps enforced.

## Storage status

X10 Pro healthy — archive lives on the external disk.

Incident history: 2026-10-02 ~09:00–10:30 PDT the volume wedged (all I/O hung; recovered only after clean unmount/remount cycles; ~30 pulls staged locally first and merged back via `mover` once healthy). If I/O hangs again: `diskutil unmount "X10 Pro"` then `diskutil mount disk4s2`, never force-unmount mid-write.

## API history depth (probed 2026-10-02, D2b + D2c bisect)

- 2023-03-28: 12,493 matrix rows
- 2023-06-13: 26,554 matrix rows
- 2023-09-13: 27,779 matrix rows
- 2024-03-08: 37,255 matrix rows
- 2024-08-05: 40,211 matrix rows
- 2025-01-15: 38,219 matrix rows
- 2025-04-15: 47,194 matrix rows
- 2025-08-17: 39,165 matrix rows
- 2025-12-15: 41,968 matrix rows
- 2026-02-16: 42,480 matrix rows
- 2026-04-15: 43,163 matrix rows
- 2026-06-15: 51,316 matrix rows
- 2026-08-17: 48,236 matrix rows
- 2026-09-15: 45,916 matrix rows

Depth boundary (2026-10-02 D2c, refined — supersedes D2b's 2023-03 → 2024-03 range): the API states the floor directly — pre-2023-03-28 timestamps return HTTP 400: "The 'at' timestamp may not be before 2023-03-28, where heatmap history begins." Bisect probes 2023-09-13 (27,779 rows), 2023-06-13 (26,554 rows) and the boundary day 2023-03-28 itself (12,493 rows) all return real strike×expiry cells; 2023-03-13 and 2022-05-12 stay HTTP 400. Every day >= 2023-03-28 is buyable at 5 cr/call for sweeps — ~11 months deeper than the D2b assumption of 2024-03-08 (boundary-day rows are partial).

## Big-move day sweep (D2b/D2c, ranked by leandata realized range)

Core profile (60s RTH, calibration quartet) per swept day. Since D2c the RTH window is DST-aware (America/New_York): EDT-day pull_ids are byte-identical to D2b's, EST days (2024-03-04..08) now map to 14:30-21:00Z instead of a 1-hour-offset window:

| swept day | core pulls archived |
|---|---|
| 2025-04-07 | 390 |
| 2025-04-04 | 390 |
| 2025-04-09 | 390 |
| 2024-08-02 | 390 |
| 2024-08-01 | 390 |
| 2024-08-06 | 390 |
| 2024-03-08 | 390 |
| 2025-04-10 | 390 |
| 2024-03-04 | 390 |
| 2024-03-05 | 390 |
| 2024-08-07 | 390 |
| 2024-03-12 | 390 |
| 2024-03-11 | 390 |
| 2024-08-05 | 389 |

Next in ranked queue (unswept, buyable — one day per tranche at core profile):

- 2024-03-06: mean RTH range 6.6844% (n=54, core archived 0/390)
- 2024-03-25: mean RTH range 6.6644% (n=54, core archived 0/390)
- 2024-03-14: mean RTH range 6.6146% (n=53, core archived 0/390)
- 2025-04-08: mean RTH range 6.5989% (n=55, core archived 0/390)
- 2024-05-14: mean RTH range 6.549% (n=54, core archived 0/390)
- 2024-03-27: mean RTH range 6.3119% (n=54, core archived 0/390)
- 2024-03-15: mean RTH range 6.3052% (n=54, core archived 0/390)
- 2024-03-21: mean RTH range 6.3029% (n=53, core archived 0/390)
- 2024-03-20: mean RTH range 6.2838% (n=54, core archived 0/390)
- 2024-03-07: mean RTH range 6.2692% (n=54, core archived 0/390)

Ranking source: `/Users/admin/Desktop/Github-Projects/gammasummit/data/d2b/bigmove_day_rank.csv` (scripts/skylit_bigmove_rank.py, leandata stock_1min, read-only).
