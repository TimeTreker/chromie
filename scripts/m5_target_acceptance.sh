#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SUPERVISED_ACCEPTANCE="${SUPERVISED_ACCEPTANCE:-0}"
M5_DRY_RUN="${M5_DRY_RUN:-0}"
START_SERVICES="${START_SERVICES:-0}"
RUN_TTS_SYNTHESIS="${RUN_TTS_SYNTHESIS:-1}"
M5_EVIDENCE_ROOT="${M5_EVIDENCE_ROOT:-.chromie/acceptance}"
M5_ACCEPTANCE_ID="${M5_ACCEPTANCE_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVIDENCE_DIR="${M5_EVIDENCE_DIR:-${M5_EVIDENCE_ROOT}/${M5_ACCEPTANCE_ID}}"
SUMMARY_FILE="${EVIDENCE_DIR}/summary.env"
STATUS="failed"
FAILED_PHASE="initialization"
RECOVERY_STATE="not_exercised"

if [ "$SUPERVISED_ACCEPTANCE" != "1" ]; then
  echo "[m5-acceptance][error] Set SUPERVISED_ACCEPTANCE=1 with a safety operator present." >&2
  exit 2
fi

mkdir -p "$EVIDENCE_DIR"

write_summary() {
  local exit_code="$?"
  local commit
  commit="$(git rev-parse HEAD 2>/dev/null || printf unknown)"
  {
    printf 'M5_ACCEPTANCE_STATUS=%q\n' "$STATUS"
    printf 'M5_ACCEPTANCE_FAILED_PHASE=%q\n' "$FAILED_PHASE"
    printf 'M5_ACCEPTANCE_EXIT_CODE=%q\n' "$exit_code"
    printf 'M5_ACCEPTANCE_ID=%q\n' "$M5_ACCEPTANCE_ID"
    printf 'M5_ACCEPTANCE_COMMIT=%q\n' "$commit"
    printf 'M5_ACCEPTANCE_ENDPOINT=%q\n' "${SORIDORMI_MCP_URL:-}"
    printf 'M5_ACCEPTANCE_PROFILE=%q\n' "${CHROMIE_ACTIVE_PROFILE:-unknown}"
    printf 'M5_ACCEPTANCE_GPU=%q\n' "${CHROMIE_NVIDIA_GPU_NAME:-unknown}"
    printf 'M5_ACCEPTANCE_COMPUTE_CAP=%q\n' "${CHROMIE_NVIDIA_COMPUTE_CAP:-unknown}"
    printf 'M5_ACCEPTANCE_RECOVERY_STATE=%q\n' "$RECOVERY_STATE"
  } > "$SUMMARY_FILE"
}
trap write_summary EXIT

run_logged() {
  local phase="$1"
  local log_file="$2"
  shift 2

  FAILED_PHASE="$phase"
  printf '\n[m5-acceptance] %s\n' "$phase"
  if [ "$M5_DRY_RUN" = "1" ]; then
    printf '[m5-acceptance][DRY-RUN] '
    printf '%q ' "$@"
    printf '\n'
    printf 'DRY-RUN: ' > "$log_file"
    printf '%q ' "$@" >> "$log_file"
    printf '\n' >> "$log_file"
    return 0
  fi

  "$@" 2>&1 | tee "$log_file"
}

run_json_logged() {
  local phase="$1"
  local json_file="$2"
  local stderr_file="$3"
  shift 3

  FAILED_PHASE="$phase"
  printf '\n[m5-acceptance] %s\n' "$phase"
  if [ "$M5_DRY_RUN" = "1" ]; then
    printf '[m5-acceptance][DRY-RUN] '
    printf '%q ' "$@"
    printf '\n'
    printf '{"dry_run":true}\n' > "$json_file"
    printf 'DRY-RUN: ' > "$stderr_file"
    printf '%q ' "$@" >> "$stderr_file"
    printf '\n' >> "$stderr_file"
    return 0
  fi

  if ! "$@" > "$json_file" 2> "$stderr_file"; then
    cat "$stderr_file" >&2
    cat "$json_file"
    return 1
  fi
  cat "$stderr_file" >&2
  cat "$json_file"
  python3 -c 'import json, sys; json.load(open(sys.argv[1], encoding="utf-8"))' \
    "$json_file"
}

if [ "$M5_DRY_RUN" != "1" ]; then
  run_logged \
    "Generate runtime configuration" \
    "$EVIDENCE_DIR/runtime-env.log" \
    ./scripts/build_runtime_env.sh
  set -a
  # shellcheck disable=SC1091
  source .env.runtime
  set +a
fi

if [ -z "${SORIDORMI_MCP_URL:-}" ]; then
  echo "[m5-acceptance][error] SORIDORMI_MCP_URL is required." >&2
  exit 2
fi

COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)
if [ -n "${CHROMIE_COMPOSE_OVERRIDE_FILES:-}" ]; then
  IFS=',' read -ra override_files <<< "$CHROMIE_COMPOSE_OVERRIDE_FILES"
  for file in "${override_files[@]}"; do
    file="$(echo "$file" | xargs)"
    [ -n "$file" ] || continue
    COMPOSE_ARGS+=(-f "$file")
  done
fi

run_json_logged \
  "Preflight runtime-backed Soridormi endpoint" \
  "$EVIDENCE_DIR/runtime-preflight.json" \
  "$EVIDENCE_DIR/runtime-preflight.stderr.log" \
  docker compose "${COMPOSE_ARGS[@]}" run -T --rm --no-deps chromie-agent \
  python -m app.soridormi_acceptance \
  --manifest /app/capabilities/soridormi.json \
  --runtime-preflight

run_logged \
  "Run target GPU smoke test" \
  "$EVIDENCE_DIR/gpu-smoke.log" \
  env START_SERVICES="$START_SERVICES" RUN_TTS_SYNTHESIS="$RUN_TTS_SYNTHESIS" \
  ./scripts/gpu_smoke_test.sh

RECOVERY_STATE="emergency_stop_may_be_active_verify_before_motion"
run_logged \
  "Exercise runtime cancellation and emergency fallback" \
  "$EVIDENCE_DIR/runtime-cancellation.log" \
  docker compose "${COMPOSE_ARGS[@]}" run -T --rm --no-deps chromie-agent \
  python -m app.soridormi_acceptance \
  --manifest /app/capabilities/soridormi.json \
  --exercise-runtime-cancellation

RECOVERY_STATE="emergency_stop_active_requires_recovery"
STATUS="passed"
FAILED_PHASE=""
if [ "$M5_DRY_RUN" = "1" ]; then
  STATUS="dry_run"
  RECOVERY_STATE="not_exercised"
fi

echo
echo "[m5-acceptance] Evidence: $EVIDENCE_DIR"
echo "[m5-acceptance] Soridormi remains emergency-stopped. Complete its recovery procedure before more motion."
