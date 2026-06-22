#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MCP_URL="${SORIDORMI_MCP_URL:-http://127.0.0.1:8000/mcp}"
AUTO_CONFIRM=1
BUILD_IMAGES=0
REBUILD_NO_CACHE=0
KEEP_SERVICES=0

usage() {
  cat <<'USAGE'
Usage: ./scripts/start_chromie.sh [options]

Start Chromie after Soridormi is already running.
Image names and tags come only from .env.common/.env.local -> .env.runtime -> Compose.

Options:
  --build                 Build repository-owned images before startup
  --rebuild-no-cache      Rebuild repository-owned images without cache
  --mcp-url URL           Soridormi MCP URL
                          default: http://127.0.0.1:8000/mcp
  --require-confirmation  Require spoken confirmation for simulator skills
  --auto-confirm          Use declared simulator confirmation exemptions (default)
  --keep-services         Leave Chromie containers running after exit
  -h, --help              Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --build) BUILD_IMAGES=1; shift ;;
    --rebuild-no-cache) BUILD_IMAGES=1; REBUILD_NO_CACHE=1; shift ;;
    --mcp-url) MCP_URL="${2:?--mcp-url requires a URL}"; shift 2 ;;
    --require-confirmation) AUTO_CONFIRM=0; shift ;;
    --auto-confirm) AUTO_CONFIRM=1; shift ;;
    --keep-services) KEEP_SERVICES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[chromie][error] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for cmd in docker python3; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "[chromie][error] Required command not found: $cmd" >&2
    exit 1
  }
done

docker info >/dev/null 2>&1 || {
  echo "[chromie][error] Docker daemon is not reachable." >&2
  exit 1
}

for path in scripts/build_runtime_env.sh scripts/start_services.sh scripts/start_orchestrator.sh docker-compose.yml capabilities/soridormi.json; do
  [ -e "$path" ] || {
    echo "[chromie][error] Missing repository file: $path" >&2
    exit 1
  }
done

readarray -t MCP_PARTS < <(python3 - "$MCP_URL" <<'PYURL'
from urllib.parse import urlparse
import sys
u = urlparse(sys.argv[1])
if u.scheme not in {"http", "https"} or not u.hostname:
    raise SystemExit("invalid MCP URL")
port = u.port or (443 if u.scheme == "https" else 80)
path = u.path or "/mcp"
container_host = "host.docker.internal" if u.hostname in {"127.0.0.1", "localhost", "::1"} else u.hostname
print(u.hostname)
print(port)
print(f"{u.scheme}://{u.hostname}:{port}{path}")
print(f"{u.scheme}://{container_host}:{port}{path}")
PYURL
)
MCP_HOST="${MCP_PARTS[0]}"
MCP_PORT="${MCP_PARTS[1]}"
HOST_MCP_URL="${MCP_PARTS[2]}"
CONTAINER_MCP_URL="${MCP_PARTS[3]}"

python_tcp_check() {
  python3 - "$1" "$2" <<'PYTCP' >/dev/null 2>&1
import socket, sys
with socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=1.0):
    pass
PYTCP
}

wait_for_tcp() {
  local host="$1" port="$2" timeout_s="$3" label="$4"
  local deadline=$((SECONDS + timeout_s))
  echo "[chromie] Waiting for $label at $host:$port..."
  until python_tcp_check "$host" "$port"; do
    if (( SECONDS >= deadline )); then
      echo "[chromie][error] Timed out waiting for $label." >&2
      return 1
    fi
    sleep 2
  done
  echo "[chromie] $label is ready."
}

if ! python_tcp_check "$MCP_HOST" "$MCP_PORT"; then
  echo "[chromie][error] Soridormi MCP is not reachable: $HOST_MCP_URL" >&2
  echo "[chromie][hint] Start Soridormi first." >&2
  exit 1
fi

if [ ! -f orchestrator/.env.local ]; then
  cp orchestrator/.env.local.example orchestrator/.env.local
  echo "[chromie] Created orchestrator/.env.local."
fi

mkdir -p .chromie/voice-runtime hf_cache ollama_data recordings
./scripts/build_runtime_env.sh

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

RUNTIME_DIR="$ROOT_DIR/.chromie/voice-runtime"
COMPOSE_OVERRIDE="$RUNTIME_DIR/compose.voice-mujoco.yaml"
ORCH_OVERRIDE="$RUNTIME_DIR/orchestrator.env"

cat > "$COMPOSE_OVERRIDE" <<EOF_COMPOSE
services:
  chromie-agent:
    environment:
      AGENT_CAPABILITY_MANIFESTS: /app/capabilities/soridormi.json
      SORIDORMI_MCP_URL: ${CONTAINER_MCP_URL}
      AGENT_EXPRESSIVE_BODY_CUES: ${AGENT_EXPRESSIVE_BODY_CUES:-sim_only}
      AGENT_INTERACTION_OUTPUT_MODE: native
      AGENT_NATIVE_INTERACTION_FALLBACK: "0"
EOF_COMPOSE

cat > "$ORCH_OVERRIDE" <<EOF_ORCH
ORCH_AUDIO_INPUT_MODE=device
ORCH_AUDIO_OUTPUT_MODE=device
ORCH_ENABLE_ROUTER=1
ORCH_ENABLE_AGENT=1
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
ORCH_AUTO_CONFIRM_SIM_SKILLS=${AUTO_CONFIRM}
ORCH_SORIDORMI_MANIFEST=capabilities/soridormi.json
AGENT_INTERACTION_OUTPUT_MODE=native
AGENT_NATIVE_INTERACTION_FALLBACK=0
SORIDORMI_MCP_URL=${HOST_MCP_URL}
EOF_ORCH

export CHROMIE_COMPOSE_OVERRIDE_FILES="${CHROMIE_COMPOSE_OVERRIDE_FILES:+${CHROMIE_COMPOSE_OVERRIDE_FILES},}${COMPOSE_OVERRIDE}"
export CHROMIE_PULL_POLICY=never

if [ "$BUILD_IMAGES" = "1" ]; then
  if [ "$REBUILD_NO_CACHE" = "1" ]; then
    REBUILD_NO_CACHE=1 ./scripts/start_services.sh
  else
    BUILD=1 ./scripts/start_services.sh
  fi
else
  ./scripts/start_services.sh
fi

COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)
IFS=',' read -ra override_files <<< "${CHROMIE_COMPOSE_OVERRIDE_FILES:-}"
for file in "${override_files[@]}"; do
  file="$(echo "$file" | xargs)"
  [ -n "$file" ] && COMPOSE_ARGS+=(-f "$file")
done

CLEANED=0
cleanup() {
  local rc=$?
  [ "$CLEANED" = "0" ] || return "$rc"
  CLEANED=1
  if [ "$KEEP_SERVICES" = "1" ]; then
    echo "[chromie] Leaving Chromie containers running."
    return "$rc"
  fi
  echo
  echo "[chromie] Stopping Chromie containers..."
  docker compose "${COMPOSE_ARGS[@]}" down >/dev/null 2>&1 || true
  return "$rc"
}
trap cleanup EXIT INT TERM

wait_for_tcp 127.0.0.1 9001 900 "ASR"
wait_for_tcp 127.0.0.1 5000 900 "TTS"
wait_for_tcp 127.0.0.1 8091 300 "Router"
wait_for_tcp 127.0.0.1 8092 300 "Agent"
wait_for_tcp 127.0.0.1 11434 300 "Ollama"

echo "[chromie] Checking Soridormi capabilities..."
docker compose "${COMPOSE_ARGS[@]}" exec -T \
  -e "SORIDORMI_MCP_URL=$CONTAINER_MCP_URL" \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json \
  --exclude-effect test_control

cat <<EOF_READY

======================================================================
Chromie voice interaction is ready
======================================================================
Soridormi MCP: ${HOST_MCP_URL}
Images: defined once in .env.common/.env.local and consumed by Compose
Pull policy: never

Speak normally, for example:
  Hello Chromie.
  What is the robot status?
  Please nod twice.
  Look at me for three seconds.
  Stop.

Press Ctrl+C to stop Chromie.
======================================================================
EOF_READY

ORCH_RUNTIME_OVERRIDE_FILE="$ORCH_OVERRIDE" \
  ./scripts/start_orchestrator.sh
