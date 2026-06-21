#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SORIDORMI_REPO="${SORIDORMI_REPO:-$ROOT_DIR/../soridormi}"
STATE_DIR="${CHROMIE_VOICE_MUJOCO_STATE_DIR:-$ROOT_DIR/.chromie/voice-mujoco}"
if [ -f "$STATE_DIR/run.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$STATE_DIR/run.env"
  set +a
fi
SIM_PID_FILE="$STATE_DIR/simulator.pid"
SIM_GROUP_FILE="$STATE_DIR/simulator.process_group"
SORIDORMI_LAUNCHER_PID_FILE="$STATE_DIR/soridormi-launcher.pid"
CHROMIE_LAUNCHER_PID_FILE="$STATE_DIR/chromie-launcher.pid"

if [ -d "$SORIDORMI_REPO" ]; then
  SORIDORMI_REPO="$(cd "$SORIDORMI_REPO" && pwd)"
fi

echo "[voice-mujoco] Stopping Chromie Orchestrator..."
pkill -TERM -f 'python -m orchestrator\.orchestrator' 2>/dev/null || true

for launcher_file in "$CHROMIE_LAUNCHER_PID_FILE" "$SORIDORMI_LAUNCHER_PID_FILE"; do
  if [ -f "$launcher_file" ]; then
    pid="$(cat "$launcher_file" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "[voice-mujoco] Stopping launcher process $pid..."
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 1 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.25
      done
    fi
    rm -f "$launcher_file"
  fi
done

if [ -f "$SIM_PID_FILE" ]; then
  pid="$(cat "$SIM_PID_FILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "[voice-mujoco] Stopping Soridormi MuJoCo simulator..."
    if [ -f "$SIM_GROUP_FILE" ] && [ "$(cat "$SIM_GROUP_FILE")" = "1" ]; then
      kill -TERM -- "-$pid" 2>/dev/null || true
    else
      kill -TERM "$pid" 2>/dev/null || true
    fi
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
  fi
fi
rm -f "$SIM_PID_FILE" "$SIM_GROUP_FILE"

if [ -d "$SORIDORMI_REPO" ] && [ -f "$SORIDORMI_REPO/compose.sim.yaml" ]; then
  echo "[voice-mujoco] Stopping Soridormi runtime MCP..."
  (cd "$SORIDORMI_REPO" && \
    docker compose -f compose.sim.yaml --profile mcp-runtime \
      stop mcp-runtime >/dev/null 2>&1 || true)
fi

if [ -f .env.runtime ]; then
  echo "[voice-mujoco] Stopping Chromie containers..."
  docker compose --env-file .env.runtime down
fi

echo "[voice-mujoco] Stopped."
