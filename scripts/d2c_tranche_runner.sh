#!/bin/bash
# D2c post-midnight tranche runner (t_bc5a0f12).
# Waits for fresh UTC day (daily caps reset), then:
#   1. pull --batch all   — Tier-A accrual (any newly aligned session-day) +
#                           probe re-check + the daily heatmap cadence burst
#   2. pull --batch sweep — big-move days, rank order, 2 runs of 4 days
#                           (run caps stay under 3,000 req / 12,000 cr each)
#   3. mover --execute    — merge any staging back to X10
# Chain STOPS on any non-zero pull rc (rate discipline: incident = pause).
set -u
cd /Users/admin/Desktop/Github-Projects/gammasummit
LOG="data/d2b/d2c_tranche.log"

echo "=== D2c tranche runner armed $(date -u +%FT%TZ) ===" > "$LOG"
python3 - >> "$LOG" 2>&1 <<'PYEOF'
import time
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc)
target = now.replace(hour=0, minute=0, second=15, microsecond=0)
if target <= now:
    target += timedelta(days=1)
wait = (target - now).total_seconds()
print(f"sleeping {wait:.0f}s until {target.isoformat()}", flush=True)
time.sleep(wait)
print(f"window open: {datetime.now(timezone.utc).isoformat()}", flush=True)
PYEOF

python3 scripts/skylit_api_archive.py pull --batch all --execute >> "$LOG" 2>&1
RC_ALL=$?
echo "=== batch all rc=$RC_ALL $(date -u +%FT%TZ) ===" >> "$LOG"

RC_A=99; RC_B=99
if [ "$RC_ALL" = "0" ]; then
  python3 scripts/skylit_api_archive.py pull --batch sweep \
    --sweep-days 2024-08-06,2024-03-08,2025-04-10,2024-03-04 \
    --execute >> "$LOG" 2>&1
  RC_A=$?
  echo "=== sweep run A (ranks 7-10) rc=$RC_A $(date -u +%FT%TZ) ===" >> "$LOG"
else
  echo "=== sweep run A SKIPPED: all-batch non-zero rc (owner rule: pause) ===" >> "$LOG"
fi

if [ "$RC_A" = "0" ]; then
  python3 scripts/skylit_api_archive.py pull --batch sweep \
    --sweep-days 2024-03-05,2024-08-07,2024-03-12,2024-03-11 \
    --execute >> "$LOG" 2>&1
  RC_B=$?
  echo "=== sweep run B (ranks 11-14) rc=$RC_B $(date -u +%FT%TZ) ===" >> "$LOG"
else
  echo "=== sweep run B SKIPPED: run A non-zero rc ===" >> "$LOG"
fi

python3 scripts/skylit_api_archive.py mover --execute >> "$LOG" 2>&1
echo "=== mover rc=$? $(date -u +%FT%TZ) ===" >> "$LOG"

echo "--- daily caps ---" >> "$LOG"
cat "/Volumes/X10 Pro/gammasummit/skylit_api/state/daily_caps.json" >> "$LOG"
echo "--- ledger tail ---" >> "$LOG"
tail -2 "/Volumes/X10 Pro/gammasummit/skylit_api/credit_ledger.jsonl" >> "$LOG"
echo "=== D2c tranche end all=$RC_ALL A=$RC_A B=$RC_B $(date -u +%FT%TZ) ===" >> "$LOG"
