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
echo "[start] User Meaning Interpreter model: ${AGENT_USER_MEANING_INTERPRETER_MODEL:-unset}"
echo "[start] Agent model: ${AGENT_MODEL:-unset}"
echo "[start] Cognitive models: association=${AGENT_GOAL_ASSOCIATION_MODEL:-unset} planner=${AGENT_PLANNER_MODEL:-unset} deep=${AGENT_DELIBERATIVE_MODEL:-unset}"
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

# shellcheck source=scripts/compact_cognition.sh
source "$ROOT_DIR/scripts/compact_cognition.sh"
if chromie_apply_compact_cognition "$TTS_BACKEND"; then
  echo "[start] CosyVoice shared-GPU cognition: $CHROMIE_COMPACT_COGNITION_MODEL (generated role contexts preserved; one resident Ollama model/runner)."
  # verify_runtime_profile.sh re-sources .env.runtime. Record the effective
  # compact-cognition values as a service override so the verifier compares the
  # containers against what this launcher actually started.
  COMPACT_OVERRIDE="$ROOT_DIR/.chromie/services.compact-cognition.env"
  mkdir -p "$ROOT_DIR/.chromie"
  {
    if [ -n "${CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE:-}" ]; then
      cat "$CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE"
    fi
    for key in "${CHROMIE_COMPACT_COGNITION_MODEL_KEYS[@]}" OLLAMA_MAX_LOADED_MODELS; do
      printf '%s=%q\n' "$key" "${!key}"
    done
  } > "$COMPACT_OVERRIDE.tmp"
  mv "$COMPACT_OVERRIDE.tmp" "$COMPACT_OVERRIDE"
  export CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE="$COMPACT_OVERRIDE"
fi

# Optional comma-separated compose override list, for example:
# CHROMIE_COMPOSE_OVERRIDE_FILES=docker-compose.sglang.yml
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
if [ "${AGENT_LLM_PROVIDER:-ollama}" = "sglang" ]; then
  BUILD_SERVICES+=(chromie-llm)
fi

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
docker compose "${COMPOSE_ARGS[@]}" up "${UP_ARGS[@]}" "${SERVICES[@]}"

if [[ "${BUILD:-0}" == "1" ]]; then
  # A build that changed an image leaves its container on the replaced image ID.
  # Recreate exactly those services before profile verification, so no container
  # keeps a replaced image reference while an unchanged service (the model server
  # above all) keeps running instead of reloading.
  declare -A SERVICE_IMAGES=()
  while IFS=$'\t' read -r service image_ref; do
    SERVICE_IMAGES["$service"]="$image_ref"
  done < <(docker compose "${COMPOSE_ARGS[@]}" config --format json | python3 -c '
import json, sys
for name, spec in json.load(sys.stdin)["services"].items():
    print(name, spec.get("image", ""), sep="\t")')
  STALE_SERVICES=()
  for service in "${SERVICES[@]}"; do
    container="$(docker compose "${COMPOSE_ARGS[@]}" ps -a -q "$service" 2>/dev/null | head -n 1 || true)"
    image_ref="${SERVICE_IMAGES[$service]:-}"
    [[ -n "$container" && -n "$image_ref" ]] || continue
    running_image="$(docker inspect -f '{{.Image}}' "$container" 2>/dev/null || true)"
    current_image="$(docker image inspect -f '{{.Id}}' "$image_ref" 2>/dev/null || true)"
    if [[ -n "$current_image" && "$running_image" != "$current_image" ]]; then
      STALE_SERVICES+=("$service")
    fi
  done
  if (( ${#STALE_SERVICES[@]} > 0 )); then
    echo "[start] Recreating services whose image changed: ${STALE_SERVICES[*]}"
    docker compose "${COMPOSE_ARGS[@]}" up "${UP_ARGS[@]}" --no-deps --force-recreate "${STALE_SERVICES[@]}"
  else
    echo "[start] No service image changed; running containers are kept."
  fi
fi

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
if [ "${AGENT_LLM_PROVIDER:-ollama}" = "ollama" ]; then
  echo " ./scripts/warm_ollama.sh"
fi
echo " ./scripts/start_orchestrator.sh"
echo
echo "[start] Build commands:"
echo " BUILD=1 ./scripts/start_services.sh"
echo " REBUILD_NO_CACHE=1 ./scripts/start_services.sh"

if [[ "${FOLLOW_LOGS:-0}" == "1" ]]; then
  docker compose "${COMPOSE_ARGS[@]}" logs -f "${SERVICES[@]}"
fi
