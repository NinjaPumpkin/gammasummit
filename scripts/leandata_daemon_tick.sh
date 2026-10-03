#!/bin/bash
# leandata continuation daemon tick — kanban D3 (t_427942b6) follow-through.
#
# Runs every few hours via Hermes cron (no_agent, script-only). It:
#   1. merges the local staging archive into X10 when the drive responds
#      (leandata_x10_merge.py --execute also re-derives data/missing_*.txt
#      gap lists from the live X10 tree — incl. the stock_1min 128 list);
#   2. launches the throttled extractor if no instance is running (the
#      driver's own flock is the real guard; pgrep just avoids noise).
# All throttle policy (pacing, cooldown, daily cap 20k, abort-on-rate) lives
# in scripts/leandata_extract.py. Empty-ish output is fine: stdout is the
# watchdog signal.
set -u
cd /Users/admin/Desktop/Github-Projects/gammasummit

if python3 scripts/leandata_x10_merge.py --execute >> data/leandata-x10-merge.log 2>&1; then
  echo "x10-merge: ok (see data/leandata-x10-merge.log)"
else
  echo "x10-merge: skipped/unavailable (X10 unresponsive or merge error)"
fi

if pgrep -f "leandata_extract.py" >/dev/null 2>&1; then
  echo "extract: already running"
else
  nohup python3 scripts/leandata_extract.py --max-batches-per-root 12 \
    >> data/leandata-extract-run.log 2>&1 &
  echo "extract: launched pid $!"
fi
