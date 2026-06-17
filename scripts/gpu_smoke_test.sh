#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DRY_RUN="${DRY_RUN:-0}"
START_SERVICES="${START_SERVICES:-0}"
RUN_TTS_SYNTHESIS="${RUN_TTS_SYNTHESIS:-0}"
RUN_OLLAMA_GENERATE="${RUN_OLLAMA_GENERATE:-1}"
SMOKE_TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-300}"
TTS_SMOKE_TEXT="${TTS_SMOKE_TEXT:-Chromie GPU smoke test is ready.}"
TTS_SMOKE_SPEAKER="${TTS_SMOKE_SPEAKER:-default}"

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[gpu-smoke][PASS] %s\n' "$*"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[gpu-smoke][FAIL] %s\n' "$*" >&2
}

skip() {
  SKIP_COUNT=$((SKIP_COUNT + 1))
  printf '[gpu-smoke][SKIP] %s\n' "$*"
}

run_step() {
  local label="$1"
  shift

  printf '\n[gpu-smoke] %s\n' "$label"
  if [ "$DRY_RUN" = "1" ]; then
    printf '[gpu-smoke][DRY-RUN] '
    printf '%q ' "$@"
    printf '\n'
    skip "$label"
    return 0
  fi

  if "$@"; then
    pass "$label"
    return 0
  fi

  fail "$label"
  return 1
}

require_command() {
  local command_name="$1"
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "Found command: $command_name"
    return 0
  fi
  fail "Missing required command: $command_name"
  return 1
}

echo "Chromie GPU smoke test"
echo "======================"
echo "Dry run:             $DRY_RUN"
echo "Start services:      $START_SERVICES"
echo "Ollama generation:   $RUN_OLLAMA_GENERATE"
echo "TTS synthesis:       $RUN_TTS_SYNTHESIS"
echo "Timeout:             ${SMOKE_TIMEOUT_SECONDS}s"

if [ "$DRY_RUN" != "1" ]; then
  require_command docker || true
  require_command curl || true
fi

run_step "Generate hardware-aware runtime configuration" ./scripts/build_runtime_env.sh || true

if [ -f .env.runtime ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.runtime
  set +a
  pass "Loaded .env.runtime"
else
  fail ".env.runtime was not generated"
fi

COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)
if [ -n "${CHROMIE_COMPOSE_OVERRIDE_FILES:-}" ]; then
  IFS=',' read -ra override_files <<< "$CHROMIE_COMPOSE_OVERRIDE_FILES"
  for file in "${override_files[@]}"; do
    file="$(echo "$file" | xargs)"
    [ -n "$file" ] || continue
    if [ ! -f "$file" ]; then
      fail "Compose override file not found: $file"
      continue
    fi
    COMPOSE_ARGS+=(-f "$file")
  done
fi

echo
echo "[gpu-smoke] Selected runtime"
echo "  profile=${CHROMIE_ACTIVE_PROFILE:-unknown}"
echo "  gpu=${CHROMIE_NVIDIA_GPU_NAME:-unknown}"
echo "  compute=${CHROMIE_NVIDIA_COMPUTE_CAP:-unknown}"
echo "  cuda_arch=${TTS_CUDA_ARCH:-unset}"
echo "  agent_model=${AGENT_MODEL:-unset}"
echo "  asr_model=${ASR_MODEL:-unset}"

check_host_gpu() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader
    return
  fi

  if [ "${CHROMIE_IS_JETSON:-0}" = "1" ] || [ -r /proc/device-tree/model ]; then
    printf 'Jetson GPU detected from device tree: %s\n' "${CHROMIE_JETSON_MODEL:-unknown}"
    return
  fi

  echo "No NVIDIA GPU tool or Jetson device-tree detection available." >&2
  return 1
}

run_step "Detect NVIDIA GPU on host" check_host_gpu || true
run_step "Validate Docker Compose configuration" docker compose "${COMPOSE_ARGS[@]}" config --quiet || true

if [ "$START_SERVICES" = "1" ]; then
  run_step "Start Chromie services from existing images" ./scripts/start_services.sh || true
else
  skip "Service startup disabled; set START_SERVICES=1 to start existing images"
fi

check_compose_health() {
  local service
  local container_id
  local status
  local health
  local pending
  local deadline=$((SECONDS + SMOKE_TIMEOUT_SECONDS))

  while true; do
    pending=0
    for service in chromie-asr chromie-tts chromie-llm chromie-router chromie-agent; do
      container_id="$(docker compose "${COMPOSE_ARGS[@]}" ps -q "$service")"
      if [ -z "$container_id" ]; then
        printf '%s: container is not running\n' "$service"
        pending=1
        continue
      fi
      status="$(docker inspect --format '{{.State.Status}}' "$container_id")"
      health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id")"
      printf '%s: status=%s health=%s\n' "$service" "$status" "$health"
      if [ "$status" != "running" ] || { [ "$health" != "healthy" ] && [ "$health" != "none" ]; }; then
        pending=1
      fi
    done

    if [ "$pending" -eq 0 ]; then
      return 0
    fi
    if (( SECONDS >= deadline )); then
      return 1
    fi
    echo "Waiting for services to become healthy..."
    sleep 3
  done
}

run_step "Check all container states and healthchecks" check_compose_health || true

check_container_gpu() {
  local service="$1"
  docker exec "$service" sh -c '
    if command -v nvidia-smi >/dev/null 2>&1; then
      exec nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader
    fi
    for device in /dev/nvidia0 /dev/nvhost-gpu /dev/nvhost-ctrl-gpu; do
      if [ -e "$device" ]; then
        echo "NVIDIA device visible: $device"
        exit 0
      fi
    done
    echo "No NVIDIA GPU device is visible in this container." >&2
    exit 1
  '
}

run_step "Verify GPU visibility in ASR container" check_container_gpu chromie-asr || true
run_step "Verify GPU visibility in TTS container" check_container_gpu chromie-tts || true
run_step "Verify GPU visibility in Ollama container" check_container_gpu chromie-llm || true

run_step "Check Router HTTP health" curl -fsS --max-time "$SMOKE_TIMEOUT_SECONDS" http://127.0.0.1:8091/health || true
run_step "Check Agent HTTP health" curl -fsS --max-time "$SMOKE_TIMEOUT_SECONDS" http://127.0.0.1:8092/health || true
run_step "Check Ollama model registry" curl -fsS --max-time "$SMOKE_TIMEOUT_SECONDS" http://127.0.0.1:11434/api/tags || true

check_control_plane_http() {
  python3 - <<'PY'
import json
import urllib.request

def post(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)

route = post(
    "http://127.0.0.1:8091/route",
    {"sid": "gpu-smoke-control", "text": "turn left", "language": "en-US", "context": {}},
)
assert route.get("route") == "chat", route
assert route.get("intent") == "general_conversation", route
assert route.get("actions") == [], route

agent = post(
    "http://127.0.0.1:8092/run",
    {
        "sid": "gpu-smoke-control",
        "text": "turn left",
        "route_decision": route,
        "language": "en-US",
        "context": {"robot_state": {"emergency_stop": False}},
        "history": [],
    },
)
assert agent.get("status") == "ok", agent
assert agent.get("actions") == [], agent
assert agent.get("speak_immediate"), agent
print(json.dumps({"route": route, "agent": agent}, ensure_ascii=False))
PY
}

run_step "Run deployed Router-to-Agent safe chat control-plane round trip" check_control_plane_http || true

check_asr_websocket() {
  docker exec -i chromie-asr python - <<'PY'
import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:9001", open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "health"}))
        response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert response.get("type") == "pong", response
        print(response)

asyncio.run(main())
PY
}

check_tts_websocket() {
  docker exec -i chromie-tts /opt/venv/bin/python - <<'PY'
import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:5000", open_timeout=10) as ws:
        await ws.send(json.dumps({"type": "health"}))
        response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert response.get("type") == "pong", response
        assert response.get("gpu_layers") == -1, response
        print(response)

asyncio.run(main())
PY
}

run_step "Check ASR WebSocket health" check_asr_websocket || true
run_step "Check TTS WebSocket health and full GPU-layer setting" check_tts_websocket || true
run_step "Verify TTS llama.cpp CUDA backend" ./scripts/verify_tts_gpu.sh || true

ollama_generate() {
  python3 - <<'PY' | curl -fsS --max-time "$SMOKE_TIMEOUT_SECONDS" \
    http://127.0.0.1:11434/api/generate \
    -H 'Content-Type: application/json' \
    --data-binary @- \
    | python3 -c 'import json, sys; data=json.load(sys.stdin); response=str(data.get("response") or "").strip(); assert response, data; print(response)'
import json
import os

print(json.dumps({
    "model": os.environ["AGENT_MODEL"],
    "prompt": "Reply with exactly one word: ready",
    "stream": False,
    "think": False,
    "keep_alive": os.environ.get("OLLAMA_KEEP_ALIVE", "24h"),
    "options": {
        "num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", os.environ.get("OLLAMA_CONTEXT_LENGTH", "2048"))),
        "num_predict": 8,
        "temperature": 0.0,
    },
}))
PY
}

if [ "$RUN_OLLAMA_GENERATE" = "1" ]; then
  run_step "Run one Ollama generation with the selected Agent model" ollama_generate || true
  run_step "Confirm Ollama loaded the Agent model on GPU" \
    bash -c 'docker exec chromie-llm ollama ps | tee /dev/stderr | grep -qi gpu' || true
else
  skip "Ollama generation disabled"
fi

tts_synthesize() {
  docker exec -i \
    -e TTS_SMOKE_TEXT="$TTS_SMOKE_TEXT" \
    -e TTS_SMOKE_SPEAKER="$TTS_SMOKE_SPEAKER" \
    chromie-tts /opt/venv/bin/python - <<'PY'
import asyncio
import json
import os
import websockets

async def main():
    request_id = "gpu-smoke-tts"
    audio_bytes = 0
    start = None
    end = None

    async with websockets.connect("ws://127.0.0.1:5000", open_timeout=10, max_size=10**7) as ws:
        await ws.send(json.dumps({
            "type": "synthesize_stream",
            "request_id": request_id,
            "text": os.environ["TTS_SMOKE_TEXT"],
            "speaker_id": os.environ["TTS_SMOKE_SPEAKER"],
        }))

        while True:
            message = await asyncio.wait_for(ws.recv(), timeout=300)
            if isinstance(message, bytes):
                audio_bytes += len(message)
                continue
            payload = json.loads(message)
            if payload.get("type") == "start":
                start = payload
            elif payload.get("type") == "error":
                raise RuntimeError(payload.get("message") or payload)
            elif payload.get("type") == "end":
                end = payload
                break

    assert start is not None, "TTS did not send start metadata"
    assert end is not None, "TTS did not send end metadata"
    assert audio_bytes > 0, "TTS returned no PCM audio"
    print(json.dumps({"audio_bytes": audio_bytes, "start": start, "end": end}, ensure_ascii=False))

asyncio.run(main())
PY
}

if [ "$RUN_TTS_SYNTHESIS" = "1" ]; then
  run_step "Generate non-empty TTS PCM audio on GPU" tts_synthesize || true
else
  skip "TTS synthesis disabled; set RUN_TTS_SYNTHESIS=1 for a real generation"
fi

echo
echo "Chromie GPU smoke-test summary"
echo "=============================="
echo "PASS=$PASS_COUNT FAIL=$FAIL_COUNT SKIP=$SKIP_COUNT"

if [ "$DRY_RUN" = "1" ]; then
  echo "Dry run completed; no GPU or service checks were executed."
  exit 0
fi

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "GPU smoke test failed. Review the failed steps and service logs." >&2
  exit 1
fi

echo "GPU smoke test passed."
