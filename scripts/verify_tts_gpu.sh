#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env.runtime ]; then
  ./scripts/build_runtime_env.sh
fi

SERVICE="${TTS_SERVICE:-chromie-tts}"
PYTHON_BIN="${TTS_PYTHON_BIN:-/opt/venv/bin/python}"

echo "[verify] Checking Docker service: $SERVICE"
docker compose --env-file .env.runtime ps "$SERVICE"

echo
echo "[verify] Checking NVIDIA visibility inside container..."
docker exec "$SERVICE" bash -lc 'nvidia-smi || true'

echo
echo "[verify] Checking TTS GPU env inside container..."
docker exec "$SERVICE" bash -lc 'echo "NVIDIA_VISIBLE_DEVICES=${NVIDIA_VISIBLE_DEVICES:-}"; echo "NVIDIA_DRIVER_CAPABILITIES=${NVIDIA_DRIVER_CAPABILITIES:-}"; echo "TTS_N_GPU_LAYERS=${TTS_N_GPU_LAYERS:-}"; echo "TTS_AUDIO_CODEC_DEVICE=${TTS_AUDIO_CODEC_DEVICE:-}"; echo "TTS_QUANTIZATION=${TTS_QUANTIZATION:-}"; echo "TTS_CONTEXT_SIZE=${TTS_CONTEXT_SIZE:-}"; echo "TTS_N_BATCH=${TTS_N_BATCH:-}"; echo "TTS_CUDA_ARCH is build-time only: check docker compose build args"'

echo
echo "[verify] Checking llama-cpp-python CUDA backend..."
docker exec -i "$SERVICE" "$PYTHON_BIN" - <<'PY'
from llama_cpp import llama_cpp
info = llama_cpp.llama_print_system_info().decode(errors="ignore")
print(info)
upper = info.upper()
if "CUDA" not in upper and "CUBLAS" not in upper:
    raise SystemExit("ERROR: llama-cpp-python was built without CUDA/CUBLAS backend")
print("OK: llama-cpp-python CUDA backend detected")
PY

echo
echo "[verify] Checking TTS websocket health on localhost:5000 from inside container..."
docker exec -i "$SERVICE" "$PYTHON_BIN" - <<'PY'
import asyncio
import json
import websockets

async def main():
    try:
        async with websockets.connect("ws://127.0.0.1:5000", open_timeout=5) as ws:
            await ws.send(json.dumps({"type": "health"}))
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            print(msg)
            data = json.loads(msg)
            workers = data.get("workers") or []
            codec = workers[0].get("audio_codec") if workers else None
            print(f"Resolved audio codec: {codec}")
            expected = data.get("audio_codec_device")
            effective = codec.get("effective") if isinstance(codec, dict) else None
            if expected == "cuda" and not str(effective or "").startswith("cuda"):
                raise SystemExit(
                    f"ERROR: audio codec expected CUDA but effective device is {effective!r}"
                )
            print("OK: TTS websocket health responded with runtime device metadata")
    except Exception as exc:
        raise SystemExit(f"ERROR: TTS websocket health check failed: {exc}")

asyncio.run(main())
PY

if [ "${RUN_TTS_BENCHMARK:-0}" = "1" ]; then
  echo
  echo "[verify] Running short TTS performance benchmark..."
  python scripts/benchmark_tts.py --warmup 0 --repeat 1 \
    --output .chromie/evidence/tts-benchmark.json
fi

echo
echo "[verify] Done. Confirm full layer offload, the effective DAC device, and benchmark RTF."
