#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SORIDORMI_REPO="${SORIDORMI_REPO:-$ROOT_DIR/../soridormi}"
STATE_DIR="${CHROMIE_VOICE_MUJOCO_STATE_DIR:-$ROOT_DIR/.chromie/voice-mujoco}"
LOG_DIR="$STATE_DIR/logs"
PROFILE="${SORIDORMI_SIM_POLICY_PROFILE:-open_duck_forward}"
MCP_PORT="${SORIDORMI_MCP_PORT:-8000}"
MCP_PATH="${SORIDORMI_MCP_PATH:-/mcp}"
VIEWER=1
FOLLOW_CAMERA=1
BUILD_IMAGES=0
REBUILD_NO_CACHE=0
KEEP_RUNNING=0
AUTO_CONFIRM=1

usage() {
  cat <<'USAGE'
Usage: ./scripts/start_voice_mujoco.sh [options]

Start the paired operator loop:
  microphone -> Chromie ASR/Router/Agent -> Soridormi MCP -> MuJoCo viewer
  speaker <- Chromie TTS

Options:
  --soridormi-repo DIR  Soridormi checkout; default: ../soridormi
  --build               Build repository-owned images before startup
  --rebuild-no-cache    Rebuild Chromie images without cache; implies --build
  --profile NAME        Soridormi policy profile; default: open_duck_forward
  --mcp-port PORT       Host Soridormi MCP port; default: 8000
  --viewer              Open MuJoCo viewer; default
  --no-viewer           Run MuJoCo headless
  --follow-camera       Keep the viewer centered on the robot; default
  --no-follow-camera    Disable viewer follow camera
  --require-confirmation
                        Require spoken confirmation for simulator skills
  --auto-confirm        Use simulator confirmation exemptions; default
  --keep-running        Leave containers/simulator running after launcher exits
  -h, --help            Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --soridormi-repo) SORIDORMI_REPO="${2:?--soridormi-repo requires a directory}"; shift 2 ;;
    --build) BUILD_IMAGES=1; shift ;;
    --rebuild-no-cache) BUILD_IMAGES=1; REBUILD_NO_CACHE=1; shift ;;
    --profile) PROFILE="${2:?--profile requires a value}"; shift 2 ;;
    --mcp-port) MCP_PORT="${2:?--mcp-port requires a value}"; shift 2 ;;
    --viewer) VIEWER=1; shift ;;
    --no-viewer) VIEWER=0; shift ;;
    --follow-camera) FOLLOW_CAMERA=1; shift ;;
    --no-follow-camera) FOLLOW_CAMERA=0; shift ;;
    --require-confirmation) AUTO_CONFIRM=0; shift ;;
    --auto-confirm) AUTO_CONFIRM=1; shift ;;
    --keep-running) KEEP_RUNNING=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[voice-mujoco][error] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -d "$SORIDORMI_REPO" ]; then
  SORIDORMI_REPO="$(cd "$SORIDORMI_REPO" && pwd)"
else
  echo "[voice-mujoco][error] Soridormi repo not found: $SORIDORMI_REPO" >&2
  echo "[voice-mujoco][hint] Pass --soridormi-repo /absolute/path/to/soridormi" >&2
  exit 1
fi

for path in \
  "$SORIDORMI_REPO/scripts/start_soridormi_mujoco.sh" \
  "$ROOT_DIR/scripts/start_chromie.sh" \
  "$ROOT_DIR/scripts/status_voice_mujoco.sh" \
  "$ROOT_DIR/scripts/check_voice_mujoco_logs.sh"; do
  [ -e "$path" ] || {
    echo "[voice-mujoco][error] Missing required file: $path" >&2
    exit 1
  }
done

mkdir -p "$LOG_DIR"
SORIDORMI_LOG="$LOG_DIR/soridormi.log"
CHROMIE_LOG="$LOG_DIR/chromie.log"
EVENT_LOG="$LOG_DIR/orchestrator-events.jsonl"
SORIDORMI_PID_FILE="$STATE_DIR/soridormi-launcher.pid"
CHROMIE_PID_FILE="$STATE_DIR/chromie-launcher.pid"
RUN_ENV_FILE="$STATE_DIR/run.env"

cat > "$RUN_ENV_FILE" <<EOF_ENV
SORIDORMI_REPO=$SORIDORMI_REPO
SORIDORMI_MCP_PORT=$MCP_PORT
SORIDORMI_MCP_PATH=$MCP_PATH
SORIDORMI_MCP_URL=http://127.0.0.1:${MCP_PORT}${MCP_PATH}
CHROMIE_VOICE_MUJOCO_STATE_DIR=$STATE_DIR
CHROMIE_VOICE_MUJOCO_LOG_DIR=$LOG_DIR
EOF_ENV

python_tcp_check() {
  python3 - "$1" "$2" <<'PY' >/dev/null 2>&1
import socket
import sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=1.0):
    pass
PY
}

wait_for_tcp() {
  local host="$1" port="$2" timeout_s="$3" label="$4"
  local deadline=$((SECONDS + timeout_s))
  echo "[voice-mujoco] Waiting for $label at $host:$port..."
  until python_tcp_check "$host" "$port"; do
    if (( SECONDS >= deadline )); then
      echo "[voice-mujoco][error] Timed out waiting for $label." >&2
      return 1
    fi
    sleep 2
  done
  echo "[voice-mujoco] $label is ready."
}

cleanup() {
  local rc=$?
  if [ "$KEEP_RUNNING" = "1" ]; then
    echo "[voice-mujoco] Leaving paired services running."
    return "$rc"
  fi
  echo
  echo "[voice-mujoco] Stopping paired services..."
  "$ROOT_DIR/scripts/stop_voice_mujoco.sh" >/dev/null 2>&1 || true
  return "$rc"
}
trap cleanup EXIT INT TERM

echo "[voice-mujoco] Logs: $LOG_DIR"
echo "[voice-mujoco] Starting Soridormi MuJoCo + runtime MCP..."
: > "$SORIDORMI_LOG"

soridormi_args=(--profile "$PROFILE")
if [ "$KEEP_RUNNING" = "1" ]; then soridormi_args+=(--keep-running); fi
if [ "$BUILD_IMAGES" = "1" ]; then soridormi_args+=(--build); fi
if [ "$VIEWER" = "1" ]; then soridormi_args+=(--viewer); else soridormi_args+=(--no-viewer); fi
if [ "$FOLLOW_CAMERA" = "1" ]; then
  soridormi_args+=(--follow-camera)
else
  soridormi_args+=(--no-follow-camera)
fi

(
  cd "$SORIDORMI_REPO"
  SORIDORMI_MCP_PORT="$MCP_PORT" \
    SORIDORMI_MCP_PATH="$MCP_PATH" \
    ./scripts/start_soridormi_mujoco.sh "${soridormi_args[@]}"
) >>"$SORIDORMI_LOG" 2>&1 &
SORIDORMI_PID=$!
echo "$SORIDORMI_PID" > "$SORIDORMI_PID_FILE"

if ! wait_for_tcp 127.0.0.1 "$MCP_PORT" 420 "Soridormi MCP"; then
  tail -n 180 "$SORIDORMI_LOG" >&2 || true
  exit 1
fi

echo "[voice-mujoco] Starting Chromie voice stack..."
: > "$CHROMIE_LOG"
chromie_args=(--mcp-url "http://127.0.0.1:${MCP_PORT}${MCP_PATH}")
if [ "$KEEP_RUNNING" = "1" ]; then chromie_args+=(--keep-services); fi
if [ "$BUILD_IMAGES" = "1" ]; then chromie_args+=(--build); fi
if [ "$REBUILD_NO_CACHE" = "1" ]; then chromie_args+=(--rebuild-no-cache); fi
if [ "$AUTO_CONFIRM" = "1" ]; then
  chromie_args+=(--auto-confirm)
else
  chromie_args+=(--require-confirmation)
fi

ORCH_EVENT_LOG_PATH="$EVENT_LOG" \
  ORCH_SESSION_TIMING_LOGS=1 \
  ./scripts/start_chromie.sh "${chromie_args[@]}" 2>&1 | tee "$CHROMIE_LOG" &
CHROMIE_PID=$!
echo "$CHROMIE_PID" > "$CHROMIE_PID_FILE"

wait_for_tcp 127.0.0.1 8092 420 "Chromie Agent"
wait_for_tcp 127.0.0.1 8091 420 "Chromie Router"
wait_for_tcp 127.0.0.1 9001 420 "Chromie ASR"
wait_for_tcp 127.0.0.1 5000 420 "Chromie TTS"
wait_for_tcp 127.0.0.1 11434 420 "Chromie Ollama"

echo "[voice-mujoco] Waiting for Chromie Orchestrator..."
for _ in $(seq 1 180); do
  if pgrep -f 'python -m orchestrator\.orchestrator' >/dev/null 2>&1; then
    echo "[voice-mujoco] Chromie Orchestrator is ready."
    break
  fi
  if ! kill -0 "$CHROMIE_PID" 2>/dev/null; then
    echo "[voice-mujoco][error] Chromie launcher exited before Orchestrator started." >&2
    tail -n 180 "$CHROMIE_LOG" >&2 || true
    exit 1
  fi
  sleep 2
done
if ! pgrep -f 'python -m orchestrator\.orchestrator' >/dev/null 2>&1; then
  echo "[voice-mujoco][error] Timed out waiting for Chromie Orchestrator." >&2
  tail -n 180 "$CHROMIE_LOG" >&2 || true
  exit 1
fi

cat <<EOF_READY

======================================================================
Chromie voice-to-MuJoCo is ready
======================================================================
Speak into the configured microphone, for example:
  Hello Chromie.
  What is the robot status?
  Please nod twice.
  Look at me for three seconds.
  Stop.

Visual check:
  Watch the MuJoCo viewer for safe, simulator-bounded motion only.

Speaker check:
  You should hear Chromie answer through the configured output device.

Log check from another terminal:
  ./scripts/status_voice_mujoco.sh
  ./scripts/check_voice_mujoco_logs.sh

No-microphone checks from another terminal:
  ./scripts/run_voice_mujoco_text_case.sh "Please nod twice." --speaker
  ./scripts/run_voice_mujoco_text_case.sh "Look at me for three seconds." --no-speaker

Logs:
  $LOG_DIR

Press Ctrl+C here to stop the paired stack.
======================================================================
EOF_READY

wait "$CHROMIE_PID"
