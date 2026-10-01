#!/usr/bin/env bash
# smoke.sh — post-deploy smoke: /healthz + /readyz + 3 key endpoints +
# one real heatmap read (docs/build/code-structure-and-release.md §5).
# Non-zero exit triggers auto-rollback.
#
# PLACEHOLDER (card E1.1 scaffold) — endpoints land with the API workstream;
# this stub only proves the harness shape. Read-only: safe to run anywhere.
set -euo pipefail

BASE_URL="${GAMMASUMMIT_SMOKE_BASE_URL:-http://127.0.0.1:8100}"

echo "smoke.sh: checking $BASE_URL/healthz"
if ! curl -fsS "$BASE_URL/healthz" > /dev/null 2>&1; then
  echo "smoke.sh: FAIL — /healthz unreachable at $BASE_URL" >&2
  exit 1
fi
echo "smoke.sh: /healthz OK"
echo "smoke.sh: placeholder — /readyz + key endpoints + heatmap read land with the API workstream"
exit 0
