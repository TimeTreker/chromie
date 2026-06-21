#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STATE_DIR="${CHROMIE_VOICE_MUJOCO_STATE_DIR:-$ROOT_DIR/.chromie/voice-mujoco}"
LOG_DIR="${CHROMIE_VOICE_MUJOCO_LOG_DIR:-$STATE_DIR/logs}"
SORIDORMI_REPO="${SORIDORMI_REPO:-$ROOT_DIR/../soridormi}"
SINCE="${VOICE_MUJOCO_LOG_SINCE:-10m}"
TAIL_LINES=160
FAILED=0

usage() {
  cat <<'USAGE'
Usage: ./scripts/check_voice_mujoco_logs.sh [options]

Collect recent Chromie/Soridormi logs and fail on startup-crash patterns.

Options:
  --soridormi-repo DIR  Soridormi checkout; default: ../soridormi
  --since DURATION      Docker log window; default: 10m
  --tail N              Lines to keep per service; default: 160
  -h, --help            Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --soridormi-repo) SORIDORMI_REPO="${2:?--soridormi-repo requires a directory}"; shift 2 ;;
    --since) SINCE="${2:?--since requires a duration}"; shift 2 ;;
    --tail) TAIL_LINES="${2:?--tail requires a number}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[voice-mujoco-logs][error] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"
if [ -d "$SORIDORMI_REPO" ]; then
  SORIDORMI_REPO="$(cd "$SORIDORMI_REPO" && pwd)"
fi

fatal_pattern='Traceback|ModuleNotFoundError|FileNotFoundError|Segmentation fault|segmentation fault|panic:|Fatal Python error|Address already in use'

capture_container_log() {
  local service="$1" output="$2"
  if docker ps --format '{{.Names}}' | grep -Fxq "$service"; then
    docker logs --since "$SINCE" "$service" 2>&1 | tail -n "$TAIL_LINES" > "$output"
    printf '[LOG ] %-24s %s\n' "$service" "$output"
    if grep -E "$fatal_pattern" "$output" >/dev/null 2>&1; then
      printf '[FAIL] %-24s fatal pattern found\n' "$service"
      FAILED=1
    else
      printf '[OK  ] %-24s no fatal startup pattern\n' "$service"
    fi
  else
    printf '[MISS] %-24s container is not running\n' "$service"
    FAILED=1
  fi
}

capture_file_log() {
  local label="$1" path="$2"
  if [ -s "$path" ]; then
    tail -n "$TAIL_LINES" "$path" > "$LOG_DIR/${label}.tail.log"
    printf '[LOG ] %-24s %s\n' "$label" "$LOG_DIR/${label}.tail.log"
    if grep -E "$fatal_pattern" "$LOG_DIR/${label}.tail.log" >/dev/null 2>&1; then
      printf '[FAIL] %-24s fatal pattern found\n' "$label"
      FAILED=1
    else
      printf '[OK  ] %-24s no fatal startup pattern\n' "$label"
    fi
  else
    printf '[MISS] %-24s log file missing or empty: %s\n' "$label" "$path"
  fi
}

echo "[voice-mujoco-logs] Capturing recent logs into $LOG_DIR"
capture_file_log chromie-launcher "$LOG_DIR/chromie.log"
capture_file_log soridormi-launcher "$LOG_DIR/soridormi.log"

for service in chromie-asr chromie-tts chromie-router chromie-agent chromie-llm; do
  capture_container_log "$service" "$LOG_DIR/${service}.docker.log"
done

if [ -d "$SORIDORMI_REPO" ] && [ -f "$SORIDORMI_REPO/compose.sim.yaml" ]; then
  if docker ps --format '{{.Names}}' | grep -Fxq soridormi-runtime-mcp; then
    (
      cd "$SORIDORMI_REPO"
      docker compose -f compose.sim.yaml --profile mcp-runtime logs --since "$SINCE" --tail "$TAIL_LINES" mcp-runtime
    ) > "$LOG_DIR/soridormi-runtime-mcp.compose.log" 2>&1
    printf '[LOG ] %-24s %s\n' "soridormi-runtime-mcp" "$LOG_DIR/soridormi-runtime-mcp.compose.log"
    if grep -E "$fatal_pattern" "$LOG_DIR/soridormi-runtime-mcp.compose.log" >/dev/null 2>&1; then
      printf '[FAIL] %-24s fatal pattern found\n' "soridormi-runtime-mcp"
      FAILED=1
    else
      printf '[OK  ] %-24s no fatal startup pattern\n' "soridormi-runtime-mcp"
    fi
  else
    printf '[MISS] %-24s container is not running\n' "soridormi-runtime-mcp"
    FAILED=1
  fi
fi

if [ -s "$LOG_DIR/orchestrator-events.jsonl" ]; then
  tail -n "$TAIL_LINES" "$LOG_DIR/orchestrator-events.jsonl" > "$LOG_DIR/orchestrator-events.tail.jsonl"
  printf '[LOG ] %-24s %s\n' "orchestrator-events" "$LOG_DIR/orchestrator-events.tail.jsonl"
else
  printf '[INFO] %-24s no event log yet; speak or run a text case first\n' "orchestrator-events"
fi

exit "$FAILED"
