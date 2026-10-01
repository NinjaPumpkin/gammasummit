#!/usr/bin/env bash
# deploy.sh — VPS release deploy: build into /opt/gammasummit/releases/<sha>/,
# run expand-phase migrations, atomically flip the `current` symlink, then run
# smoke.sh with auto-rollback on failure (docs/build/code-structure-and-release.md §5).
#
# PLACEHOLDER (card E1.1 scaffold): the real release flow lands with the
# release-engineering card. This stub exists so the tree matches the plan and
# so the dry-run contract is enforced from day one.
#   default   = dry-run (print the plan, touch nothing)
#   --execute = apply (refuses while still a placeholder)
set -euo pipefail

EXECUTE=0
if [[ "${1:-}" == "--execute" ]]; then
  EXECUTE=1
fi

PLAN="build /opt/gammasummit/releases/<sha> -> run expand migrations -> \
flip 'current' symlink -> smoke.sh -> keep last 5 releases for rollback"

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "deploy.sh dry-run: would $PLAN"
  echo "deploy.sh dry-run: nothing changed (use --execute to apply)"
  exit 0
fi

echo "deploy.sh: placeholder — full release flow not implemented yet." >&2
echo "deploy.sh: planned flow: $PLAN" >&2
exit 2
