#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env.runtime ]; then
  ./scripts/build_runtime_env.sh
fi

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

BACKEND="${CHROMIE_TTS_BACKEND:-cosyvoice3}"
SERVICE="${TTS_SERVICE:-chromie-tts}"
EXPECTED_PROVIDER="fun-cosyvoice3-0.5b"
HOST_PORT=5000
COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)
case "${BACKEND,,}" in
  cosyvoice|cosyvoice3)
    BACKEND=cosyvoice3
    ;;
  oute|outetts)
    BACKEND=oute
    SERVICE="${TTS_SERVICE:-chromie-tts-oute}"
    EXPECTED_PROVIDER=oute
    HOST_PORT=5001
    COMPOSE_ARGS+=(--profile tts-evaluation)
    ;;
  qwen|qwen3|qwen3-tts)
    BACKEND=qwen3
    SERVICE="${TTS_SERVICE:-chromie-tts-qwen3}"
    EXPECTED_PROVIDER=qwen3-tts-0.6b-base
    HOST_PORT=5002
    COMPOSE_ARGS+=(--profile tts-evaluation)
    ;;
  *)
    echo "[verify][error] Unsupported CHROMIE_TTS_BACKEND=$BACKEND" >&2
    exit 2
    ;;
esac

PYTHON_BIN="${TTS_PYTHON_BIN:-/opt/venv/bin/python}"

echo "[verify] Checking TTS backend=$BACKEND service=$SERVICE provider=$EXPECTED_PROVIDER"
docker compose "${COMPOSE_ARGS[@]}" ps "$SERVICE"

echo
echo "[verify] Checking NVIDIA visibility inside container..."
docker exec "$SERVICE" bash -lc 'nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader'

echo
echo "[verify] Checking framework GPU runtime..."
if [ "$BACKEND" = "oute" ]; then
  docker exec -i "$SERVICE" "$PYTHON_BIN" - <<'PY'
from llama_cpp import llama_cpp
info = llama_cpp.llama_print_system_info().decode(errors="ignore")
print(info)
if "CUDA" not in info.upper() and "CUBLAS" not in info.upper():
    raise SystemExit("ERROR: Oute llama.cpp backend lacks CUDA/CUBLAS")
PY
else
  docker exec -i "$SERVICE" "$PYTHON_BIN" - "$BACKEND" <<'PY'
import sys
import torch

backend = sys.argv[1]
print({"torch_cuda_available": torch.cuda.is_available(), "device_count": torch.cuda.device_count()})
if not torch.cuda.is_available():
    raise SystemExit("ERROR: TTS framework cannot see CUDA")
if backend == "cosyvoice3":
    import onnxruntime as ort
    providers = ort.get_available_providers()
    print({"onnxruntime_providers": providers})
    if "CUDAExecutionProvider" not in providers:
        raise SystemExit("ERROR: CosyVoice normalizer lacks CUDAExecutionProvider")
PY
fi

echo
echo "[verify] Checking TTS websocket health..."
docker exec -i "$SERVICE" "$PYTHON_BIN" - "$EXPECTED_PROVIDER" <<'PY'
import asyncio
import json
import sys
import websockets

expected = sys.argv[1]

async def main():
    async with websockets.connect("ws://127.0.0.1:5000", open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "health"}))
        payload = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        print(json.dumps(payload, ensure_ascii=False))
        assert payload.get("type") == "pong", payload
        assert payload.get("provider", {}).get("provider_id") == expected, payload
        provider_health = payload.get("provider_health") or {}
        if "ready" in provider_health:
            assert provider_health["ready"] is True, payload

asyncio.run(main())
PY

if [ "${RUN_TTS_BENCHMARK:-0}" = "1" ]; then
  echo
  echo "[verify] Running short TTS performance benchmark..."
  python scripts/benchmark_tts.py \
    --url "ws://127.0.0.1:${HOST_PORT}" \
    --warmup 0 --repeat 1 \
    --output .chromie/evidence/tts-benchmark.json
fi

echo
echo "[verify] TTS GPU and provider health checks passed."
