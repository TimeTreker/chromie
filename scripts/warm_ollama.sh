#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

MODEL="${1:-${AGENT_MODEL:-gemma4:26b}}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
WARM_TIMEOUT_SECONDS="${OLLAMA_WARM_TIMEOUT_SECONDS:-600}"
REQUEST_TIMEOUT_SECONDS="${OLLAMA_WARM_REQUEST_TIMEOUT_SECONDS:-300}"

echo "[warm-ollama] Ollama URL: $OLLAMA_URL"
echo "[warm-ollama] Model: $MODEL"
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
echo "[warm-ollama] Warming model. This may take a while for large models..."

payload="$(python3 - <<PY
import json
print(json.dumps({
    "model": "${MODEL}",
    "prompt": "Reply with exactly one word: ready",
    "stream": False,
    "think": False,
    "keep_alive": "24h",
    "options": {
        "num_predict": 8,
        "temperature": 0.0
    }
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
    echo "[warm-ollama] Model warmed successfully."
    echo "[warm-ollama] Response preview:"
    echo "$body" | head -c 500
    echo
    exit 0
  fi

  echo "[warm-ollama][warn] Warm attempt failed. HTTP status=$status"
  echo "$body" | head -c 800
  echo

  if (( SECONDS >= deadline )); then
    echo "[warm-ollama][error] Model did not warm within ${WARM_TIMEOUT_SECONDS}s." >&2
    exit 1
  fi

  echo "[warm-ollama] Retrying in 5s..."
  sleep 5
done
