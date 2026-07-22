#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE="${ORCH_LOCK_FILE:-/tmp/chromie-orchestrator.lock}"

if flock -n "$LOCK_FILE" -c ':'; then
  exit 0
fi

echo "[chromie][error] A host Orchestrator is already running: $LOCK_FILE" >&2
echo "[chromie][hint] Stop the old Chromie launcher with Ctrl+C before rebuilding or restarting services." >&2
exit 1
