#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p hf_cache ollama_data recordings tts/speakers

echo "[start] Project root: $ROOT_DIR"
echo "[start] Starting Chromie Docker services..."

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

if [[ "${REBUILD_NO_CACHE:-0}" == "1" ]]; then
  docker compose build --no-cache chromie-asr chromie-tts
fi

docker compose up -d --build chromie-asr chromie-llm chromie-tts

echo
echo "[start] Docker service status:"
docker compose ps

echo
echo "[start] Useful follow-up commands:"
echo "  docker compose logs -f chromie-tts"
echo "  docker compose logs -f chromie-asr"
echo "  ./scripts/verify_tts_gpu.sh"
echo "  REBUILD_NO_CACHE=1 ./scripts/start_services.sh  # rebuild CUDA services from scratch"
echo "  ./scripts/warm_ollama.sh"
echo
echo "[start] To run the host orchestrator:"
echo "  cd orchestrator && source .venv/bin/activate && python orchestrator.py"

if [[ "${FOLLOW_LOGS:-0}" == "1" ]]; then
  docker compose logs -f chromie-asr chromie-tts chromie-llm
fi
