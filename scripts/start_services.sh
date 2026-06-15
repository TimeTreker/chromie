#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[start] Project root: $ROOT_DIR"
echo "[start] Preparing hardware/runtime environment..."

./scripts/build_runtime_env.sh

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

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
ensure_dir ollama_data
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
echo "[start] Agent model: ${AGENT_MODEL:-unset}"
echo "[start] ASR model: ${ASR_MODEL:-unset}"
echo "[start] TTS model size: ${TTS_MODEL_SIZE:-unset}"

COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)

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
  chromie-tts
  chromie-router
  chromie-agent
)

BUILD_SERVICES=(
  chromie-asr
  chromie-tts
  chromie-router
  chromie-agent
)

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

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
docker compose "${COMPOSE_ARGS[@]}" up -d --no-build --pull "$PULL_POLICY" "${SERVICES[@]}"

echo
echo "[start] Docker service status:"
docker compose "${COMPOSE_ARGS[@]}" ps

echo
echo "[start] Useful follow-up commands:"
echo " docker compose --env-file .env.runtime logs -f chromie-tts"
echo " docker compose --env-file .env.runtime logs -f chromie-asr"
echo " docker compose --env-file .env.runtime logs -f chromie-router"
echo " docker compose --env-file .env.runtime logs -f chromie-agent"
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
