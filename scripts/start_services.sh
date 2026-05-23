#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[start] Project root: $ROOT_DIR"
echo "[start] Starting Chromie Docker services..."

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

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

if [ -x "./scripts/detect-cuda-arch.sh" ]; then
  export TTS_CUDA_ARCH="$(./scripts/detect-cuda-arch.sh)"
  echo "[start] Detected TTS_CUDA_ARCH=${TTS_CUDA_ARCH}"
else
  echo "[start][warn] ./scripts/detect-cuda-arch.sh not found or not executable; using TTS_CUDA_ARCH=${TTS_CUDA_ARCH:-unset}"
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

if [[ "${REBUILD_NO_CACHE:-0}" == "1" ]]; then
  export BUILD=1
fi

if [[ "${BUILD:-0}" == "1" ]]; then
  if [[ "${REBUILD_NO_CACHE:-0}" == "1" ]]; then
    echo "[start] Building images with --no-cache..."
    docker compose build --no-cache "${BUILD_SERVICES[@]}"
  else
    echo "[start] Building images with Docker cache..."
    docker compose build "${BUILD_SERVICES[@]}"
  fi
else
  echo "[start] Skipping image build. Use BUILD=1 to rebuild."
fi

echo "[start] Starting containers without building..."
docker compose up -d --no-build "${SERVICES[@]}"

echo
echo "[start] Docker service status:"
docker compose ps

echo
echo "[start] Useful follow-up commands:"
echo " docker compose logs -f chromie-tts"
echo " docker compose logs -f chromie-asr"
echo " docker compose logs -f chromie-router"
echo " docker compose logs -f chromie-agent"
echo " ./scripts/verify_tts_gpu.sh"
echo " ./scripts/warm_ollama.sh"
echo
echo "[start] Build commands:"
echo " BUILD=1 ./scripts/start_services.sh                  # rebuild using Docker cache"
echo " REBUILD_NO_CACHE=1 ./scripts/start_services.sh       # rebuild from scratch"
echo
echo "[start] To run the host orchestrator:"
echo " cd orchestrator && source .venv/bin/activate && python orchestrator.py"

if [[ "${FOLLOW_LOGS:-0}" == "1" ]]; then
  docker compose logs -f "${SERVICES[@]}"
fi
