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

OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
WARM_TIMEOUT_SECONDS="${OLLAMA_WARM_TIMEOUT_SECONDS:-600}"
REQUEST_TIMEOUT_SECONDS="${OLLAMA_WARM_REQUEST_TIMEOUT_SECONDS:-300}"
KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:-24h}"
NUM_CTX="${OLLAMA_NUM_CTX:-${OLLAMA_CONTEXT_LENGTH:-2048}}"
NUM_PREDICT="${OLLAMA_NUM_PREDICT:-16}"

if [ "$#" -gt 0 ]; then
  MODELS=("$@")
else
  MODELS=("${AGENT_MODEL:-${OLLAMA_MODEL:-gemma4:e2b}}")
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

echo "[warm-ollama] Waiting for Ollama server..."
until curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "[warm-ollama][error] Ollama server did not become ready in ${WARM_TIMEOUT_SECONDS}s." >&2
    exit 1
  fi
  sleep 2
done

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

    if [ "$status" = "404" ] && echo "$body" | grep -qi "not found"; then
      echo "[warm-ollama][error] Ollama model is not present locally: $model" >&2
      echo "[warm-ollama][hint] Pull it first:" >&2
      echo "[warm-ollama][hint]   docker exec chromie-llm ollama pull $model" >&2
      echo "[warm-ollama][hint] Or set a local override such as ROUTER_MODEL=qwen3:4b in .env.local, then rerun ./scripts/build_runtime_env.sh." >&2
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
