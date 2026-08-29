#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export CHROMIE_OPERATOR_MODE="${CHROMIE_OPERATOR_MODE:-services}"

echo "[start] Project root: $ROOT_DIR"
echo "[start] Preparing hardware/runtime environment..."

./scripts/build_runtime_env.sh

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

if [ -n "${CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE:-}" ]; then
  if [ ! -f "$CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE" ]; then
    echo "[start][error] Service runtime override file not found: $CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE" >&2
    exit 1
  fi
  echo "[start] Loading service runtime overrides: $CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE"
  set +a
fi

ensure_dir() {
  local dir="$1"

  if [ -e "$dir" ] && [ ! -d "$dir" ]; then
    echo "[start][error] $dir exists but is not a directory." >&2
    echo "[start][error] Please rename or remove it, then run this script again." >&2
    exit 1
  fi

  if [ ! -d "$dir" ]; then
    mkdir -p "$dir"
    echo "[start] Created directory: $dir"
  fi
}

ensure_dir hf_cache
ensure_dir "${OLLAMA_DATA_DIR:-ollama_data}"
ensure_dir recordings

# TTS_CUDA_ARCH should normally come from env/profiles/*.env. If it is missing,
# fall back to the legacy detector when available.
if [ -z "${TTS_CUDA_ARCH:-}" ] && [ -x "./scripts/detect-cuda-arch.sh" ]; then
  export TTS_CUDA_ARCH="$(./scripts/detect-cuda-arch.sh)"
  echo "[start] Detected fallback TTS_CUDA_ARCH=${TTS_CUDA_ARCH}"
fi

echo "[start] Hardware profile: ${CHROMIE_ACTIVE_PROFILE:-unknown}"
echo "[start] GPU: ${CHROMIE_NVIDIA_GPU_NAME:-unknown} compute=${CHROMIE_NVIDIA_COMPUTE_CAP:-unknown} cuda_arch=${TTS_CUDA_ARCH:-unset}"
echo "[start] CPU: ${CHROMIE_CPU_MODEL:-unknown} cores=${CHROMIE_CPU_CORES:-unknown} mem=${CHROMIE_MEM_TOTAL_MIB:-unknown}MiB"
echo "[start] Goal Interpreter model: ${AGENT_GOAL_INTERPRETER_MODEL:-unset}"
echo "[start] Agent model: ${AGENT_MODEL:-unset}"
echo "[start] Cognitive models: association=${AGENT_GOAL_ASSOCIATION_MODEL:-unset} fast=${AGENT_FAST_PLANNER_MODEL:-unset} fast_first_response=${AGENT_FAST_FIRST_RESPONSE_MODEL:-unset} deep=${AGENT_DEEP_PLANNER_MODEL:-unset}"
echo "[start] Ollama: max_loaded=${OLLAMA_MAX_LOADED_MODELS:-unset} num_parallel=${OLLAMA_NUM_PARALLEL:-unset}"
echo "[start] ASR: backend=sherpa_onnx mode=${ASR_MODE:-unset} model=${ASR_MODEL:-unset}"
echo "[start] TTS backend: ${CHROMIE_TTS_BACKEND:-cosyvoice3}"

COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)

TTS_BACKEND="${CHROMIE_TTS_BACKEND:-cosyvoice3}"
TTS_SERVICE=chromie-tts
TTS_VOICE_ROOT="${TTS_VOICE_ROOT:-assets/tts/voices}"
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
    TTS_SERVICE=chromie-tts
    export CHROMIE_TTS_BACKEND=cosyvoice3
    export TTS_VOICE_ROOT
    python3 - "$TTS_VOICE_ROOT" <<'PY_TTS_CATALOG'
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / "tts"))
from voice_catalog import validate_voice_catalog
catalog = validate_voice_catalog(Path(sys.argv[1]))
print(
    f"[tts-voices] valid root={catalog.root} default={catalog.default_speaker_id} "
    f"revision={catalog.revision} speakers={','.join(catalog.speaker_ids())}"
)
PY_TTS_CATALOG
    echo "[start] TTS provider: CosyVoice3 (maintained default)"
    ;;
  oute|outetts)
    TTS_BACKEND=oute
    TTS_SERVICE=chromie-tts-oute
    export CHROMIE_TTS_BACKEND=oute
    COMPOSE_ARGS+=(--profile tts-evaluation)
    echo "[start] TTS provider: OuteTTS (explicit fallback)"
    ;;
  qwen|qwen3|qwen3-tts)
    TTS_BACKEND=qwen3
    TTS_SERVICE=chromie-tts-qwen3
    export CHROMIE_TTS_BACKEND=qwen3
    export TTS_VOICE_ROOT
    COMPOSE_ARGS+=(--profile tts-evaluation)
    python3 scripts/tts_reference.py validate --reference-dir "$TTS_VOICE_ROOT/chromie_mixed"
    echo "[start] TTS provider: Qwen3-TTS (explicit fallback)"
    ;;
  *)
    echo "[start][error] Unsupported CHROMIE_TTS_BACKEND=${CHROMIE_TTS_BACKEND:-}" >&2
    echo "[start][hint] Supported providers: cosyvoice3, oute, qwen3" >&2
    exit 2
    ;;
esac

if [ "$TTS_BACKEND" = "cosyvoice3" ] && [ "${TTS_COSYVOICE_COMPACT_COGNITION:-1}" = "1" ]; then
  COSYVOICE_BRAIN_MODEL="${TTS_COSYVOICE_OLLAMA_MODEL:-qwen3:4b}"
  export AGENT_GOAL_INTERPRETER_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_GOAL_ASSOCIATION_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_FAST_PLANNER_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_FAST_FIRST_RESPONSE_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_DEEP_PLANNER_MODEL="$COSYVOICE_BRAIN_MODEL"
  COSYVOICE_BRAIN_NUM_CTX="${TTS_COSYVOICE_OLLAMA_NUM_CTX:-8192}"
  export AGENT_COGNITIVE_GATEWAY_ATTENTION_NUM_CTX="${AGENT_COGNITIVE_GATEWAY_ATTENTION_NUM_CTX:-$COSYVOICE_BRAIN_NUM_CTX}"
  export AGENT_GOAL_INTERPRETER_LLM_NUM_CTX="${AGENT_GOAL_INTERPRETER_LLM_NUM_CTX:-$COSYVOICE_BRAIN_NUM_CTX}"
  export AGENT_GOAL_ASSOCIATION_NUM_CTX="${AGENT_GOAL_ASSOCIATION_NUM_CTX:-$COSYVOICE_BRAIN_NUM_CTX}"
  export AGENT_FAST_PLANNER_NUM_CTX="${AGENT_FAST_PLANNER_NUM_CTX:-$COSYVOICE_BRAIN_NUM_CTX}"
  export AGENT_DEEP_PLANNER_NUM_CTX="${AGENT_DEEP_PLANNER_NUM_CTX:-$COSYVOICE_BRAIN_NUM_CTX}"
  export OLLAMA_MAX_LOADED_MODELS=1
  echo "[start] CosyVoice shared-GPU cognition: $COSYVOICE_BRAIN_MODEL context_fallback=$COSYVOICE_BRAIN_NUM_CTX (generated role contexts preserved; one resident Ollama model/runner)."
fi

# Optional comma-separated override list, for example:
# CHROMIE_COMPOSE_OVERRIDE_FILES=docker-compose.jetson.yml,docker-compose.local.yml
if [ -n "${CHROMIE_COMPOSE_OVERRIDE_FILES:-}" ]; then
  IFS=',' read -ra override_files <<< "${CHROMIE_COMPOSE_OVERRIDE_FILES}"
  for file in "${override_files[@]}"; do
    file="$(echo "$file" | xargs)"
    [ -n "$file" ] || continue
    if [ ! -f "$file" ]; then
      echo "[start][error] Compose override file not found: $file" >&2
      exit 1
    fi
    COMPOSE_ARGS+=(-f "$file")
  done
fi

SERVICES=(
  chromie-asr
  chromie-llm
  "$TTS_SERVICE"

  chromie-agent
)

BUILD_SERVICES=(
  chromie-asr
  "$TTS_SERVICE"

  chromie-agent
)

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

echo "[start] Auditing resolved local runtime exposure..."
docker compose "${COMPOSE_ARGS[@]}" config --format json |
  python3 ./scripts/check_local_runtime_exposure.py --resolved-json -

echo "[start] Validating resolved Docker Compose configuration..."
docker compose "${COMPOSE_ARGS[@]}" config --quiet

case "$TTS_SERVICE" in
  chromie-tts)
    docker compose "${COMPOSE_ARGS[@]}" --profile tts-evaluation stop \
      chromie-tts-oute chromie-tts-qwen3 >/dev/null 2>&1 || true
    ;;
  chromie-tts-oute)
    docker compose "${COMPOSE_ARGS[@]}" stop chromie-tts >/dev/null 2>&1 || true
    docker compose "${COMPOSE_ARGS[@]}" --profile tts-evaluation stop \
      chromie-tts-qwen3 >/dev/null 2>&1 || true
    ;;
  chromie-tts-qwen3)
    docker compose "${COMPOSE_ARGS[@]}" stop chromie-tts >/dev/null 2>&1 || true
    docker compose "${COMPOSE_ARGS[@]}" --profile tts-evaluation stop \
      chromie-tts-oute >/dev/null 2>&1 || true
    ;;
esac

if [[ "${REBUILD_NO_CACHE:-0}" == "1" ]]; then
  export BUILD=1
fi

if [[ "${BUILD:-0}" == "1" ]]; then
  if [[ "${REBUILD_NO_CACHE:-0}" == "1" ]]; then
    echo "[start] Building images with --no-cache..."
    docker compose "${COMPOSE_ARGS[@]}" build --no-cache "${BUILD_SERVICES[@]}"
  else
    echo "[start] Building images with Docker cache..."
    docker compose "${COMPOSE_ARGS[@]}" build "${BUILD_SERVICES[@]}"
  fi
else
  echo "[start] Skipping image build. Use BUILD=1 to rebuild."
fi

PULL_POLICY="${CHROMIE_PULL_POLICY:-never}"
echo "[start] Starting containers without building (pull policy: ${PULL_POLICY})..."
UP_ARGS=(-d --no-build --pull "$PULL_POLICY")
if [[ "${BUILD:-0}" == "1" ]]; then
  # A successful image build can replace the image ID beneath an otherwise
  # unchanged running container. Recreate every owned service before profile
  # verification so Docker never has to inspect a removed image reference.
  UP_ARGS+=(--force-recreate)
fi
docker compose "${COMPOSE_ARGS[@]}" up "${UP_ARGS[@]}" "${SERVICES[@]}"

echo "[start] Verifying container environment against the auto-detected profile..."
./scripts/verify_runtime_profile.sh

echo
echo "[start] Docker service status:"
docker compose "${COMPOSE_ARGS[@]}" ps

echo
echo "[start] Useful follow-up commands:"
echo " ./scripts/compose.sh logs -f chromie-llm"
echo " ./scripts/compose.sh logs -f $TTS_SERVICE"
echo " ./scripts/compose.sh logs -f chromie-asr"
echo " ./scripts/compose.sh logs -f"
echo " ./scripts/compose.sh logs -f chromie-agent"
echo " ./scripts/compose.sh ps"
echo " ./scripts/show_profile.sh"
echo " ./scripts/warm_ollama.sh"
echo " ./scripts/start_orchestrator.sh"
echo
echo "[start] Build commands:"
echo " BUILD=1 ./scripts/start_services.sh"
echo " REBUILD_NO_CACHE=1 ./scripts/start_services.sh"

if [[ "${FOLLOW_LOGS:-0}" == "1" ]]; then
  docker compose "${COMPOSE_ARGS[@]}" logs -f "${SERVICES[@]}"
fi
