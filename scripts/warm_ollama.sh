#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Direct warm-up also refreshes automatic hardware detection. When called from
# start_orchestrator.sh, explicit model arguments preserve its already-resolved
# inventory while this check confirms the generated files remain valid.
./scripts/build_runtime_env.sh >/dev/null

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
WARM_TIMEOUT_SECONDS="${OLLAMA_WARM_TIMEOUT_SECONDS:-600}"
REQUEST_TIMEOUT_SECONDS="${OLLAMA_WARM_REQUEST_TIMEOUT_SECONDS:-300}"
KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-24h}"
NUM_CTX="${OLLAMA_NUM_CTX:-${OLLAMA_CONTEXT_LENGTH:-2048}}"
NUM_PREDICT="${OLLAMA_WARM_NUM_PREDICT:-1}"
AUTO_RESTART_ON_CRASH="${OLLAMA_AUTO_RESTART_ON_CRASH:-1}"
OLLAMA_SERVICE_NAME="${OLLAMA_SERVICE_NAME:-chromie-llm}"
restart_attempted=0

if [ "$#" -gt 0 ]; then
  MODELS=("$@")
else
  mapfile -t MODELS < <(./scripts/list_runtime_ollama_models.sh)
fi

deduped_models=()
for model in "${MODELS[@]}"; do
  [ -n "$model" ] || continue
  duplicate=0
  for existing in "${deduped_models[@]}"; do
    if [ "$existing" = "$model" ]; then
      duplicate=1
      break
    fi
  done
  [ "$duplicate" = "0" ] && deduped_models+=("$model")
done

if [ "${#deduped_models[@]}" -eq 0 ]; then
  echo "[warm-ollama][error] No Ollama model selected to warm." >&2
  exit 1
fi

echo "[warm-ollama] Hardware profile: ${CHROMIE_ACTIVE_PROFILE:-unknown}"
echo "[warm-ollama] Ollama URL: $OLLAMA_URL"
echo "[warm-ollama] Models: ${deduped_models[*]}"
echo "[warm-ollama] Max wait: ${WARM_TIMEOUT_SECONDS}s"

deadline=$((SECONDS + WARM_TIMEOUT_SECONDS))

wait_for_ollama_server() {
  local phase="$1"
  echo "[warm-ollama] Waiting for Ollama server (${phase})..."
  until curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "[warm-ollama][error] Ollama server did not become ready in ${WARM_TIMEOUT_SECONDS}s." >&2
      exit 1
    fi
    sleep 2
  done
}

body_indicates_runner_crash() {
  local body="$1"
  echo "$body" | grep -Eiq "llama-server process has terminated|segmentation fault|core dumped"
}

restart_ollama_after_crash() {
  local model="$1"
  if ! [[ "$AUTO_RESTART_ON_CRASH" =~ ^(1|true|yes|on)$ ]]; then
    return 1
  fi
  if [ "$restart_attempted" = "1" ]; then
    return 1
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "[warm-ollama][warn] docker is unavailable; cannot restart ${OLLAMA_SERVICE_NAME} after runner crash." >&2
    return 1
  fi

  restart_attempted=1
  echo "[warm-ollama][warn] Ollama runner crashed while warming ${model}; restarting ${OLLAMA_SERVICE_NAME} once."
  if ! docker compose restart "$OLLAMA_SERVICE_NAME"; then
    echo "[warm-ollama][warn] Could not restart ${OLLAMA_SERVICE_NAME}; continuing with normal warmup failure handling." >&2
    return 1
  fi
  wait_for_ollama_server "after ${OLLAMA_SERVICE_NAME} restart"
  return 0
}

wait_for_ollama_server "initial startup"

echo "[warm-ollama] Ollama server is reachable."
echo "[warm-ollama] Warming model(s). Large models may take several minutes on first load..."

warm_one_model() {
  local model="$1"
  local payload
  payload="$(python3 - "$model" "$KEEP_ALIVE" "$NUM_CTX" "$NUM_PREDICT" <<'PY'
import json
import sys

model, keep_alive, num_ctx, num_predict = sys.argv[1:5]
print(json.dumps({
    "model": model,
    "prompt": "Reply with exactly one word: ready",
    "stream": False,
    "think": False,
    "keep_alive": keep_alive,
    "options": {
        "num_ctx": int(num_ctx),
        "num_predict": int(num_predict),
        "temperature": 0.0,
    },
}))
PY
)"

  while true; do
    body_file="$(mktemp)"
    status="$(
      curl -sS \
        --max-time "$REQUEST_TIMEOUT_SECONDS" \
        -o "$body_file" \
        -w "%{http_code}" \
        "${OLLAMA_URL}/api/generate" \
        -H "Content-Type: application/json" \
        -d "$payload" || true
    )"

    body="$(cat "$body_file" || true)"
    rm -f "$body_file"

    if [ "$status" = "200" ]; then
      echo "[warm-ollama] Model warmed successfully: $model"
      echo "[warm-ollama] Response preview:"
      echo "$body" | head -c 800
      echo
      return 0
    fi

    echo "[warm-ollama][warn] Warm attempt failed for $model. HTTP status=$status"
    echo "$body" | head -c 1200
    echo

    if [ "$status" = "500" ] && body_indicates_runner_crash "$body"; then
      if restart_ollama_after_crash "$model"; then
        echo "[warm-ollama] Retrying $model after ${OLLAMA_SERVICE_NAME} restart..."
        continue
      fi
      echo "[warm-ollama][error] Ollama native runner crashed while warming $model." >&2
      echo "[warm-ollama][hint] Try restarting the LLM service and checking GPU visibility:" >&2
      echo "[warm-ollama][hint]   docker compose restart ${OLLAMA_SERVICE_NAME}" >&2
      echo "[warm-ollama][hint]   docker exec ${OLLAMA_SERVICE_NAME} nvidia-smi" >&2
      exit 1
    fi

    if [ "$status" = "404" ] && echo "$body" | grep -qi "not found"; then
      echo "[warm-ollama][error] Ollama model is not present locally: $model" >&2
      echo "[warm-ollama][hint] Pull it first:" >&2
      echo "[warm-ollama][hint]   docker exec chromie-llm ollama pull $model" >&2
      echo "[warm-ollama][hint] Pull the model selected by env/profiles/${CHROMIE_ACTIVE_PROFILE}.env, or update that committed profile deliberately." >&2
      exit 1
    fi

    if (( SECONDS >= deadline )); then
      echo "[warm-ollama][error] Model did not warm within ${WARM_TIMEOUT_SECONDS}s: $model" >&2
      exit 1
    fi

    echo "[warm-ollama] Retrying in 5s..."
    sleep 5
  done
}

for model in "${deduped_models[@]}"; do
  warm_one_model "$model"
done

echo "[warm-ollama] All selected models warmed successfully."
