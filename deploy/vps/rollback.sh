#!/usr/bin/env bash
# rollback.sh — flip `current` back to the previous release (seconds).
# docs/build/code-structure-and-release.md §6.
#
# PLACEHOLDER (card E1.1 scaffold) — real implementation lands with the
# release-engineering card. Dry-run by default; --execute to apply.
set -euo pipefail

EXECUTE=0
if [[ "${1:-}" == "--execute" ]]; then
  EXECUTE=1
fi

if [[ "$EXECUTE" -eq 0 ]]; then
  echo "rollback.sh dry-run: would flip /opt/gammasummit/current -> previous release under /opt/gammasummit/releases/"
  echo "rollback.sh dry-run: nothing changed (use --execute to apply)"
  exit 0
fi

echo "rollback.sh: placeholder — real symlink flip not implemented yet." >&2
exit 2
