#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STATE_DIR="${CHROMIE_VOICE_MUJOCO_STATE_DIR:-$ROOT_DIR/.chromie/voice-mujoco}"
if [ -f "$STATE_DIR/run.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$STATE_DIR/run.env"
  set +a
fi

SIM_PORT="${SIM_PORT:-5555}"
MCP_PORT="${SORIDORMI_MCP_PORT:-8000}"
FAILED=0

check_tcp() {
  local label="$1"
  local host="$2"
  local port="$3"
  if python3 - "$host" "$port" <<'PY' >/dev/null 2>&1
import socket
import sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=1.0):
    pass
PY
  then
    printf '[READY] %-24s %s:%s\n' "$label" "$host" "$port"
  else
    printf '[DOWN ] %-24s %s:%s\n' "$label" "$host" "$port"
    FAILED=1
  fi
}

check_http() {
  local label="$1"
  local url="$2"
  if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
    printf '[READY] %-24s %s\n' "$label" "$url"
  else
    printf '[DOWN ] %-24s %s\n' "$label" "$url"
    FAILED=1
  fi
}

check_tcp "Soridormi MuJoCo" 127.0.0.1 "$SIM_PORT"
check_tcp "Soridormi MCP" 127.0.0.1 "$MCP_PORT"
check_tcp "Chromie ASR" 127.0.0.1 9001
check_tcp "Chromie TTS" 127.0.0.1 5000
check_http "Chromie Router" http://127.0.0.1:8091/health
check_http "Chromie Agent" http://127.0.0.1:8092/health
check_http "Chromie Ollama" http://127.0.0.1:11434/api/tags

if pgrep -f 'python -m orchestrator\.orchestrator' >/dev/null 2>&1; then
  printf '[READY] %-24s running\n' "Chromie Orchestrator"
else
  printf '[DOWN ] %-24s not running\n' "Chromie Orchestrator"
  FAILED=1
fi

exit "$FAILED"
