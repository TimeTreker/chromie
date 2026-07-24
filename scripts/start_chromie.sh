#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MCP_URL="${SORIDORMI_MCP_URL:-http://127.0.0.1:8000/mcp}"
AUTO_CONFIRM=1
BUILD_IMAGES=0
REBUILD_NO_CACHE=0
KEEP_SERVICES=0
START_ORCHESTRATOR=1
ARCHITECTURE_VALIDATION=0
TTS_BACKEND="${CHROMIE_TTS_BACKEND:-cosyvoice3}"

usage() {
  cat <<'USAGE'
Usage: ./scripts/start_chromie.sh [options]

Start Chromie after Soridormi is already running.
Hardware is detected automatically; the selected profile generates .env.runtime before build/start.
Image names and tags come from the generated runtime environment.

Options:
  --build                 Build repository-owned images before startup
  --rebuild-no-cache      Rebuild repository-owned images without cache
  --mcp-url URL           Soridormi MCP URL
                          default: http://127.0.0.1:8000/mcp
  --require-confirmation  Require spoken confirmation for simulator skills
  --auto-confirm          Use declared simulator confirmation exemptions (default)
  --keep-services         Leave Chromie containers running after exit
  --no-orchestrator       Start/probe services, then skip the host Orchestrator
  --architecture-validation
                          Use long-context, long-output, long-timeout validation
                          budgets while retaining Social Attention inference
  --tts-backend NAME      Select cosyvoice3 (default), oute, or qwen3
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
    --no-orchestrator) START_ORCHESTRATOR=0; shift ;;
    --architecture-validation) ARCHITECTURE_VALIDATION=1; shift ;;
    --tts-backend) TTS_BACKEND="${2:?--tts-backend requires a provider}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[chromie][error] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ "$ARCHITECTURE_VALIDATION" = "1" ]; then
  export CHROMIE_VALIDATION_PROFILE=architecture
  echo "[chromie] Architecture-validation budgets enabled; Social Attention remains active."
fi

for cmd in docker python3 flock; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "[chromie][error] Required command not found: $cmd" >&2
    exit 1
  }
done

docker info >/dev/null 2>&1 || {
  echo "[chromie][error] Docker daemon is not reachable." >&2
  exit 1
}

for path in scripts/build_runtime_env.sh scripts/check_orchestrator_idle.sh scripts/generate_runtime_env.py scripts/verify_runtime_profile.sh scripts/list_runtime_ollama_models.sh scripts/start_services.sh scripts/start_orchestrator.sh docker-compose.yml capabilities/soridormi.json; do
  [ -e "$path" ] || {
    echo "[chromie][error] Missing repository file: $path" >&2
    exit 1
  }
done

# Rebuilding or recreating services under an already-running host Orchestrator
# leaves the old Python process, microphone session, and in-memory goal state
# attached to the new containers. Fail before any runtime files or containers
# are changed; the operator can then stop the old launcher cleanly and retry.
./scripts/check_orchestrator_idle.sh

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

python_ws_health_check() {
  python3 - "$1" "$2" "$3" <<'PYWSHEALTH' >/dev/null 2>&1
import asyncio
import json
import sys

import websockets


async def main() -> None:
    host, raw_port, expected_service = sys.argv[1:]
    async with websockets.connect(
        f"ws://{host}:{int(raw_port)}",
        open_timeout=5,
        ping_interval=20,
        ping_timeout=20,
    ) as ws:
        await ws.send(json.dumps({"type": "health"}))
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        if not isinstance(raw, str):
            raise RuntimeError("health response was not JSON text")
        payload = json.loads(raw)
        if payload.get("type") != "pong" or payload.get("service") != expected_service:
            raise RuntimeError(f"invalid {expected_service} health response")
        if expected_service == "tts":
            if payload.get("provider_contract_version") != 1:
                raise RuntimeError("TTS provider contract is not ready")
            provider = payload.get("provider")
            provider_health = payload.get("provider_health")
            if not isinstance(provider, dict) or int(provider.get("max_concurrency") or 0) < 1:
                raise RuntimeError("TTS provider capability declaration is invalid")
            if not isinstance(provider_health, dict):
                raise RuntimeError("TTS provider health is missing")
            if "ready" in provider_health and provider_health.get("ready") is not True:
                raise RuntimeError("TTS provider is not ready")
            if (
                "worker_process_alive" in provider_health
                and provider_health.get("worker_process_alive") is not True
            ):
                raise RuntimeError("TTS worker process is not ready")


asyncio.run(main())
PYWSHEALTH
}

wait_for_ws_health() {
  local host="$1" port="$2" service="$3" timeout_s="$4" label="$5"
  local deadline=$((SECONDS + timeout_s))
  echo "[chromie] Waiting for $label application health at ws://$host:$port..."
  until python_ws_health_check "$host" "$port" "$service"; do
    if (( SECONDS >= deadline )); then
      echo "[chromie][error] Timed out waiting for $label WebSocket health." >&2
      return 1
    fi
    sleep 2
  done
  echo "[chromie] $label application is healthy."
}

warm_tts_candidate() {
  local host="$1" port="$2" expected_provider="$3" text="$4" timeout_s="$5" label="$6"
  local output
  echo "[chromie] Warming $label with a no-playback synthesis under the full service load..."
  output="$(python3 - "$host" "$port" "$expected_provider" "$text" "$timeout_s" <<'PYTTSWARM'
import asyncio
import json
import sys
import uuid

import websockets


async def synthesize() -> tuple[int, str]:
    host, raw_port, expected_provider, text, _raw_timeout = sys.argv[1:]
    audio_bytes = 0
    observed_provider = ""
    async with websockets.connect(
        f"ws://{host}:{int(raw_port)}",
        max_size=10**7,
        open_timeout=10,
        ping_interval=20,
        ping_timeout=20,
    ) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "synthesize_stream",
                    "request_id": f"startup-warm-{uuid.uuid4().hex}",
                    "text": text,
                    "speaker_id": "default",
                    "language_hint": "zh",
                },
                ensure_ascii=False,
            )
        )
        async for raw in ws:
            if isinstance(raw, bytes):
                audio_bytes += len(raw)
                continue
            payload = json.loads(raw)
            message_type = payload.get("type")
            if message_type == "error":
                raise RuntimeError(str(payload.get("message") or "TTS warm-up failed"))
            if message_type != "end":
                continue
            provider = payload.get("provider")
            if isinstance(provider, dict):
                observed_provider = str(provider.get("provider_id") or "")
            if observed_provider != expected_provider:
                raise RuntimeError(
                    f"expected provider {expected_provider!r}, got {observed_provider!r}"
                )
            if audio_bytes <= 0:
                raise RuntimeError("TTS warm-up completed without PCM audio")
            return audio_bytes, observed_provider
    raise RuntimeError("TTS warm-up socket closed before completion")


async def main() -> None:
    timeout_s = max(1.0, float(sys.argv[5]))
    audio_bytes, provider = await asyncio.wait_for(synthesize(), timeout=timeout_s)
    print(f"provider={provider} pcm_bytes={audio_bytes}")


asyncio.run(main())
PYTTSWARM
)" || {
    echo "[chromie][error] $label failed its full synthesis readiness probe." >&2
    return 1
  }
  echo "[chromie] $label is synthesis-ready ($output)."
}

python_http_check() {
  python3 - "$1" "$2" "$3" <<'PYHTTP' >/dev/null 2>&1
import http.client
import sys

connection = http.client.HTTPConnection(sys.argv[1], int(sys.argv[2]), timeout=2.0)
try:
    connection.request("GET", sys.argv[3])
    response = connection.getresponse()
    response.read()
    if not 200 <= response.status < 300:
        raise SystemExit(1)
finally:
    connection.close()
PYHTTP
}

wait_for_http() {
  local host="$1" port="$2" path="$3" timeout_s="$4" label="$5"
  local deadline=$((SECONDS + timeout_s))
  echo "[chromie] Waiting for $label health at http://$host:$port$path..."
  until python_http_check "$host" "$port" "$path"; do
    if (( SECONDS >= deadline )); then
      echo "[chromie][error] Timed out waiting for $label health endpoint." >&2
      return 1
    fi
    sleep 2
  done
  echo "[chromie] $label is healthy."
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

./scripts/build_runtime_env.sh

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

TTS_READY_PORT=5000
TTS_READY_LABEL="CosyVoice3 TTS"
TTS_REFERENCE_SHA=""
TTS_CATALOG_REVISION=""
TTS_EXPECTED_PROVIDER="fun-cosyvoice3-0.5b"
TTS_VOICE_ROOT="${TTS_VOICE_ROOT:-$ROOT_DIR/assets/tts/voices}"
TTS_VOICE_ROOT="$(python3 - "$ROOT_DIR" "$TTS_VOICE_ROOT" <<'PY_TTS_VOICE_ROOT'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
voice_root = Path(sys.argv[2]).expanduser()
if not voice_root.is_absolute():
    voice_root = root / voice_root
print(voice_root.resolve())
PY_TTS_VOICE_ROOT
)"
case "${TTS_BACKEND,,}" in
  cosyvoice|cosyvoice3)
    TTS_BACKEND=cosyvoice3
    export CHROMIE_TTS_BACKEND=cosyvoice3
    export TTS_VOICE_ROOT
    TTS_CATALOG_OUTPUT=""
    if ! TTS_CATALOG_OUTPUT="$(python3 - "$TTS_VOICE_ROOT" <<'PY_TTS_CATALOG'
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / "tts"))
from voice_catalog import validate_voice_catalog
catalog = validate_voice_catalog(Path(sys.argv[1]))
print(catalog.revision)
print(catalog.default_speaker_id)
print(",".join(catalog.speaker_ids()))
PY_TTS_CATALOG
)"; then
      echo "[chromie][error] CosyVoice3 voice catalog is missing or invalid: $TTS_VOICE_ROOT" >&2
      echo "[chromie][hint] Generate it from the local AI-generated voices:" >&2
      echo "  python scripts/promote_builtin_tts_voices.py --source-dir .chromie/private/tts-voice" >&2
      echo "[chromie][hint] Then commit assets/tts/voices so clean clones remain runnable." >&2
      exit 1
    fi
    readarray -t TTS_CATALOG_PARTS <<<"$TTS_CATALOG_OUTPUT"
    if [ "${#TTS_CATALOG_PARTS[@]}" -lt 3 ] \
      || [ -z "${TTS_CATALOG_PARTS[0]:-}" ] \
      || [ -z "${TTS_CATALOG_PARTS[1]:-}" ] \
      || [ -z "${TTS_CATALOG_PARTS[2]:-}" ]; then
      echo "[chromie][error] CosyVoice3 voice catalog validation returned incomplete identity." >&2
      exit 1
    fi
    TTS_CATALOG_REVISION="${TTS_CATALOG_PARTS[0]}"
    TTS_REFERENCE_SHA="$TTS_CATALOG_REVISION"
    TTS_READY_PORT=5000
    TTS_READY_LABEL="CosyVoice3 TTS"
    TTS_EXPECTED_PROVIDER="fun-cosyvoice3-0.5b"
    echo "[chromie] Default TTS: CosyVoice3 catalog=${TTS_CATALOG_REVISION:0:12} default=${TTS_CATALOG_PARTS[1]} speakers=${TTS_CATALOG_PARTS[2]}"
    ;;
  oute|outetts)
    TTS_BACKEND=oute
    export CHROMIE_TTS_BACKEND=oute
    TTS_READY_PORT=5001
    TTS_READY_LABEL="OuteTTS fallback"
    TTS_EXPECTED_PROVIDER="oute"
    echo "[chromie] Explicit TTS fallback: OuteTTS"
    ;;
  qwen|qwen3|qwen3-tts)
    TTS_BACKEND=qwen3
    export CHROMIE_TTS_BACKEND=qwen3
    export TTS_VOICE_ROOT
    TTS_REFERENCE_SHA="$(python3 - "$TTS_VOICE_ROOT/chromie_mixed" <<'PY_TTS_REFERENCE'
from pathlib import Path
import sys
from scripts.tts_reference import validate_reference_dir
print(validate_reference_dir(Path(sys.argv[1]))["audio_sha256"])
PY_TTS_REFERENCE
)"
    TTS_READY_PORT=5002
    TTS_READY_LABEL="Qwen3-TTS fallback"
    TTS_EXPECTED_PROVIDER="qwen3-tts-0.6b-base"
    echo "[chromie] Explicit TTS fallback: Qwen3-TTS reference_sha256=${TTS_REFERENCE_SHA:0:12}"
    ;;
  *)
    echo "[chromie][error] Unsupported --tts-backend value: $TTS_BACKEND" >&2
    echo "[chromie][hint] Supported providers: cosyvoice3, oute, qwen3" >&2
    exit 2
    ;;
esac

mkdir -p .chromie/voice-runtime hf_cache "${OLLAMA_DATA_DIR:-ollama_data}" recordings

RUNTIME_DIR="$ROOT_DIR/.chromie/voice-runtime"
COMPOSE_OVERRIDE="$RUNTIME_DIR/compose.voice-mujoco.yaml"
ORCH_OVERRIDE="$RUNTIME_DIR/orchestrator.env"
SERVICE_OVERRIDE="$RUNTIME_DIR/services.env"

EFFECTIVE_ROUTER_MODEL="${ROUTER_MODEL}"
EFFECTIVE_ROUTER_REVIEW_MODEL="${ROUTER_REVIEW_MODEL}"
EFFECTIVE_AGENT_MODEL="${AGENT_MODEL}"
EFFECTIVE_GOAL_ASSOCIATION_MODEL="${AGENT_GOAL_ASSOCIATION_MODEL}"
EFFECTIVE_FAST_PLANNER_MODEL="${AGENT_FAST_PLANNER_MODEL}"
EFFECTIVE_DEEP_PLANNER_MODEL="${AGENT_DEEP_PLANNER_MODEL}"
EFFECTIVE_RESPONSE_COMPOSER_MODEL="${AGENT_RESPONSE_COMPOSER_MODEL}"
EFFECTIVE_TASK_CONTINUITY_MODEL="${AGENT_TASK_CONTINUITY_MODEL}"
EFFECTIVE_SOCIAL_ATTENTION_MODEL="${AGENT_SOCIAL_ATTENTION_MODEL}"
EFFECTIVE_RESPONSE_REVIEW_MODEL="${AGENT_RESPONSE_REVIEW_MODEL}"
EFFECTIVE_OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-2}"

if [ "$TTS_BACKEND" = "cosyvoice3" ] && [ "${TTS_COSYVOICE_COMPACT_COGNITION:-1}" = "1" ]; then
  COSYVOICE_BRAIN_MODEL="${TTS_COSYVOICE_OLLAMA_MODEL:-qwen3:4b}"
  EFFECTIVE_ROUTER_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_ROUTER_REVIEW_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_AGENT_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_GOAL_ASSOCIATION_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_FAST_PLANNER_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_DEEP_PLANNER_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_RESPONSE_COMPOSER_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_TASK_CONTINUITY_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_SOCIAL_ATTENTION_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_RESPONSE_REVIEW_MODEL="$COSYVOICE_BRAIN_MODEL"
  EFFECTIVE_OLLAMA_MAX_LOADED_MODELS=1
  echo "[chromie] CosyVoice shared-GPU cognition: ${COSYVOICE_BRAIN_MODEL} (one resident Ollama model)."
fi

cat > "$SERVICE_OVERRIDE" <<EOF_SERVICE
CHROMIE_TTS_BACKEND=${TTS_BACKEND}
TTS_VOICE_ROOT=${TTS_VOICE_ROOT}
TTS_DEFAULT_SPEAKER=${TTS_DEFAULT_SPEAKER:-chromie_mixed}
ROUTER_MODEL=${EFFECTIVE_ROUTER_MODEL}
ROUTER_REVIEW_MODEL=${EFFECTIVE_ROUTER_REVIEW_MODEL}
AGENT_MODEL=${EFFECTIVE_AGENT_MODEL}
AGENT_GOAL_ASSOCIATION_MODEL=${EFFECTIVE_GOAL_ASSOCIATION_MODEL}
AGENT_FAST_PLANNER_MODEL=${EFFECTIVE_FAST_PLANNER_MODEL}
AGENT_DEEP_PLANNER_MODEL=${EFFECTIVE_DEEP_PLANNER_MODEL}
AGENT_RESPONSE_COMPOSER_MODEL=${EFFECTIVE_RESPONSE_COMPOSER_MODEL}
AGENT_TASK_CONTINUITY_MODEL=${EFFECTIVE_TASK_CONTINUITY_MODEL}
AGENT_SOCIAL_ATTENTION_MODEL=${EFFECTIVE_SOCIAL_ATTENTION_MODEL}
AGENT_RESPONSE_REVIEW_MODEL=${EFFECTIVE_RESPONSE_REVIEW_MODEL}
OLLAMA_MAX_LOADED_MODELS=${EFFECTIVE_OLLAMA_MAX_LOADED_MODELS}
EOF_SERVICE

cat > "$COMPOSE_OVERRIDE" <<EOF_COMPOSE
services:
  chromie-agent:
    environment:
      AGENT_MODEL: "${EFFECTIVE_AGENT_MODEL}"
      AGENT_GOAL_ASSOCIATION_MODEL: "${EFFECTIVE_GOAL_ASSOCIATION_MODEL}"
      AGENT_FAST_PLANNER_MODEL: "${EFFECTIVE_FAST_PLANNER_MODEL}"
      AGENT_DEEP_PLANNER_MODEL: "${EFFECTIVE_DEEP_PLANNER_MODEL}"
      AGENT_RESPONSE_COMPOSER_MODEL: "${EFFECTIVE_RESPONSE_COMPOSER_MODEL}"
      AGENT_TASK_CONTINUITY_MODEL: "${EFFECTIVE_TASK_CONTINUITY_MODEL}"
      AGENT_RESPONSE_REVIEW_MODEL: "${EFFECTIVE_RESPONSE_REVIEW_MODEL}"
      AGENT_CAPABILITY_MANIFESTS: /app/capabilities/soridormi.json
      SORIDORMI_MCP_URL: ${CONTAINER_MCP_URL}
      AGENT_EXPRESSIVE_BODY_CUES: off
      # Honor the resolved runtime profile: normal startup defaults Social
      # Attention to off, while the architecture-validation overlay explicitly
      # selects sim_only. Optional inference never delays the primary response.
      AGENT_SOCIAL_ATTENTION_MODE: ${CHROMIE_SOCIAL_ATTENTION_MODE:-${AGENT_SOCIAL_ATTENTION_MODE:-off}}
      AGENT_SOCIAL_ATTENTION_MODEL: "${EFFECTIVE_SOCIAL_ATTENTION_MODEL}"
      AGENT_SOCIAL_ATTENTION_FALLBACK_TARGET: ${AGENT_SOCIAL_ATTENTION_FALLBACK_TARGET:-calibrated_right_side}
      AGENT_SOCIAL_ATTENTION_FALLBACK_DIRECTION: ${AGENT_SOCIAL_ATTENTION_FALLBACK_DIRECTION:-right}
      AGENT_SOCIAL_ATTENTION_FALLBACK_YAW_RAD: ${AGENT_SOCIAL_ATTENTION_FALLBACK_YAW_RAD:-0.35}
      AGENT_SOCIAL_ATTENTION_FALLBACK_CONFIDENCE: ${AGENT_SOCIAL_ATTENTION_FALLBACK_CONFIDENCE:-0.7}
      AGENT_INTERACTION_OUTPUT_MODE: native
      AGENT_NATIVE_INTERACTION_FALLBACK: "0"
      AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED: "0"
  chromie-router:
    environment:
      ROUTER_MODEL: "${EFFECTIVE_ROUTER_MODEL}"
      ROUTER_REVIEW_MODEL: "${EFFECTIVE_ROUTER_REVIEW_MODEL}"
  chromie-llm:
    environment:
      OLLAMA_MAX_LOADED_MODELS: "${EFFECTIVE_OLLAMA_MAX_LOADED_MODELS}"
EOF_COMPOSE

cat > "$ORCH_OVERRIDE" <<EOF_ORCH
CHROMIE_TTS_BACKEND=${TTS_BACKEND}
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
AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED=0
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat,robot_action
ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed
ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=0
SORIDORMI_MCP_URL=${HOST_MCP_URL}
OLLAMA_MODEL=${EFFECTIVE_AGENT_MODEL}
ROUTER_MODEL=${EFFECTIVE_ROUTER_MODEL}
ROUTER_REVIEW_MODEL=${EFFECTIVE_ROUTER_REVIEW_MODEL}
AGENT_MODEL=${EFFECTIVE_AGENT_MODEL}
AGENT_GOAL_ASSOCIATION_MODEL=${EFFECTIVE_GOAL_ASSOCIATION_MODEL}
AGENT_FAST_PLANNER_MODEL=${EFFECTIVE_FAST_PLANNER_MODEL}
AGENT_DEEP_PLANNER_MODEL=${EFFECTIVE_DEEP_PLANNER_MODEL}
AGENT_RESPONSE_COMPOSER_MODEL=${EFFECTIVE_RESPONSE_COMPOSER_MODEL}
AGENT_TASK_CONTINUITY_MODEL=${EFFECTIVE_TASK_CONTINUITY_MODEL}
AGENT_SOCIAL_ATTENTION_MODEL=${EFFECTIVE_SOCIAL_ATTENTION_MODEL}
AGENT_RESPONSE_REVIEW_MODEL=${EFFECTIVE_RESPONSE_REVIEW_MODEL}
OLLAMA_MAX_LOADED_MODELS=${EFFECTIVE_OLLAMA_MAX_LOADED_MODELS}
EOF_ORCH

case "$TTS_BACKEND" in
  cosyvoice3)
    {
      echo "TTS_URL=ws://127.0.0.1:5000"
      echo "TTS_SPEAKER_ID=default"
      echo "ORCH_FAST_FIRST_AUDIO_CACHE_REVISION=cosyvoice3-catalog-${TTS_CATALOG_REVISION}"
      echo "ORCH_FAST_FIRST_AUDIO_CONTENT_GATE_ENABLED=1"
      echo "ORCH_FAST_FIRST_AUDIO_PRIME_ON_STARTUP=0"
      echo "ORCH_TTS_CONCURRENCY=1"
    } >> "$ORCH_OVERRIDE"
    echo "[chromie] CosyVoice TTS: one host request for the provider's one model worker."
    echo "[chromie] CosyVoice fast-first cache: load validated entries only; startup generation disabled."
    ;;
  oute)
    {
      echo "TTS_URL=ws://127.0.0.1:5001"
      echo "TTS_SPEAKER_ID=${TTS_SPEAKER_ID:-default}"
    } >> "$ORCH_OVERRIDE"
    ;;
  qwen3)
    {
      echo "TTS_URL=ws://127.0.0.1:5002"
      echo "TTS_SPEAKER_ID=default"
      echo "ORCH_FAST_FIRST_AUDIO_CACHE_REVISION=qwen3-tts-${TTS_REFERENCE_SHA}"
      echo "ORCH_FAST_FIRST_AUDIO_CONTENT_GATE_ENABLED=1"
      echo "ORCH_FAST_FIRST_AUDIO_PRIME_ON_STARTUP=0"
      echo "ORCH_TTS_CONCURRENCY=1"
    } >> "$ORCH_OVERRIDE"
    ;;
esac

export CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE="$SERVICE_OVERRIDE"
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
if [ "$TTS_BACKEND" != "cosyvoice3" ]; then
  COMPOSE_ARGS+=(--profile tts-evaluation)
fi
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

check_soridormi_from_agent_container() {
  echo "[chromie] Checking Soridormi MCP reachability from chromie-agent..."
  local output rc
  set +e
  output="$(docker compose "${COMPOSE_ARGS[@]}" exec -T \
    -e "SORIDORMI_MCP_URL=$CONTAINER_MCP_URL" \
    chromie-agent \
    python - "$CONTAINER_MCP_URL" <<'PY_MCP_REACH' 2>&1
from __future__ import annotations

from urllib.parse import urlparse
import socket
import sys

url = sys.argv[1]
parsed = urlparse(url)
host = parsed.hostname
port = parsed.port or (443 if parsed.scheme == "https" else 80)
if not host:
    print(f"[chromie][error] Invalid Soridormi MCP URL for container: {url}", file=sys.stderr)
    raise SystemExit(2)
try:
    with socket.create_connection((host, port), timeout=3.0):
        pass
except OSError as exc:
    print(
        f"[chromie][error] chromie-agent cannot reach Soridormi MCP at {url}: {exc}",
        file=sys.stderr,
    )
    print(
        "[chromie][hint] The host-side TCP check already passed. If the URL was "
        "127.0.0.1/localhost on the host, Chromie rewrites it to "
        "host.docker.internal for containers.",
        file=sys.stderr,
    )
    print(
        "[chromie][hint] This commonly means Soridormi is bound only to 127.0.0.1 "
        "on the host. Bind Soridormi MCP to 0.0.0.0 or provide a container-reachable "
        "--mcp-url, then rerun the check.",
        file=sys.stderr,
    )
    raise SystemExit(1)
print(f"[chromie] chromie-agent can reach Soridormi MCP TCP endpoint: {host}:{port}")
PY_MCP_REACH
  )"
  rc=$?
  set -e
  [ -z "$output" ] || printf '%s\n' "$output"
  return "$rc"
}

run_soridormi_capability_probe() {
  echo "[chromie] Checking Soridormi capabilities..."
  local output rc
  set +e
  output="$(docker compose "${COMPOSE_ARGS[@]}" exec -T \
    -e "SORIDORMI_MCP_URL=$CONTAINER_MCP_URL" \
    chromie-agent \
    python -m app.probe_capabilities \
    --manifest /app/capabilities/soridormi.json \
    --exclude-effect test_control 2>&1)"
  rc=$?
  set -e
  [ -z "$output" ] || printf '%s\n' "$output"
  if [ "$rc" -ne 0 ]; then
    echo "[chromie][error] Soridormi capability probe failed with exit code $rc." >&2
    echo "[chromie][hint] Chromie services are up, but the agent could not verify the Soridormi MCP contract." >&2
    echo "[chromie][hint] Inspect the probe output above first; then run:" >&2
    echo "[chromie][hint]   docker compose ${COMPOSE_ARGS[*]} logs --tail=120 chromie-agent" >&2
  fi
  return "$rc"
}

wait_for_ws_health 127.0.0.1 9001 asr 900 "ASR"
wait_for_ws_health 127.0.0.1 "$TTS_READY_PORT" tts 1200 "$TTS_READY_LABEL"
wait_for_http 127.0.0.1 8091 /health 300 "Router"
wait_for_http 127.0.0.1 8092 /health 300 "Agent"
wait_for_tcp 127.0.0.1 11434 300 "Ollama"

if [ "$TTS_BACKEND" = "cosyvoice3" ]; then
  COSYVOICE_WARMUP_TEXT="${TTS_COSYVOICE_WARMUP_TEXT:-你好，我是 Chromie。现在语音系统已经准备好了，很高兴和你一起探索这个世界。Hello, I am ready to talk with you.}"
  warm_tts_candidate \
    127.0.0.1 "$TTS_READY_PORT" "$TTS_EXPECTED_PROVIDER" \
    "$COSYVOICE_WARMUP_TEXT" 300 "$TTS_READY_LABEL"
elif [ "$TTS_BACKEND" = "qwen3" ]; then
  QWEN3_TTS_WARMUP_TEXT="${QWEN3_TTS_WARMUP_TEXT:-你好，我是 Chromie。语音系统已经准备好了。}"
  warm_tts_candidate \
    127.0.0.1 "$TTS_READY_PORT" "$TTS_EXPECTED_PROVIDER" \
    "$QWEN3_TTS_WARMUP_TEXT" 300 "$TTS_READY_LABEL"
fi

check_soridormi_from_agent_container
run_soridormi_capability_probe

if [ "$START_ORCHESTRATOR" = "1" ]; then
  READY_NEXT_STEP='The host Orchestrator starts next; wait for "Microphone started" before speaking.'
else
  READY_NEXT_STEP='Host Orchestrator: not started (--no-orchestrator).'
fi

cat <<EOF_READY

======================================================================
Chromie services are ready
======================================================================
Soridormi MCP: ${HOST_MCP_URL}
Images: defined once in .env.common/.env.local and consumed by Compose
Pull policy: never
TTS: ${TTS_BACKEND} (${TTS_EXPECTED_PROVIDER})

Speak normally, for example:
  Hello Chromie.
  What is the robot status?
  Please nod twice.
  Look at me for three seconds.
  Stop.

${READY_NEXT_STEP}
Press Ctrl+C to stop Chromie.
======================================================================
EOF_READY

if [ "$START_ORCHESTRATOR" = "0" ]; then
  echo "[chromie] Skipping host Orchestrator (--no-orchestrator)."
  exit 0
fi

ORCH_RUNTIME_OVERRIDE_FILE="$ORCH_OVERRIDE" \
  ./scripts/start_orchestrator.sh
