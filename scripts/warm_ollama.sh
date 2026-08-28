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
REQUIRE_ALL_WARM_MODELS_RESIDENT="${OLLAMA_REQUIRE_ALL_WARM_MODELS_RESIDENT:-0}"
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

context_for_model() {
  local model="$1"
  python3 - "$model" "$NUM_CTX" <<'PYCTX'
import os
import sys

model = sys.argv[1]
fallback = int(sys.argv[2])

# Warm each model with the largest context actually assigned to that model by
# the active profile. This matters for asymmetric Fast/Deep profiles: warming
# every model with the global OLLAMA_NUM_CTX would either over-allocate the Fast
# runner or under-qualify the deliberate runner.
role_contexts = (
    ("OLLAMA_MODEL", "OLLAMA_NUM_CTX"),
    ("AGENT_MODEL", "OLLAMA_NUM_CTX"),
    ("AGENT_GOAL_INTERPRETER_MODEL", "AGENT_GOAL_INTERPRETER_LLM_NUM_CTX"),
    (
        "AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL",
        "AGENT_COGNITIVE_GATEWAY_ATTENTION_NUM_CTX",
    ),
    ("AGENT_GOAL_ASSOCIATION_MODEL", "AGENT_GOAL_ASSOCIATION_NUM_CTX"),
    ("AGENT_FAST_PLANNER_MODEL", "AGENT_FAST_PLANNER_NUM_CTX"),
    # Fast first-response shares the Fast Planner topology when it uses the same model.
    ("AGENT_FAST_FIRST_RESPONSE_MODEL", "AGENT_FAST_PLANNER_NUM_CTX"),
    ("AGENT_DEEP_PLANNER_MODEL", "AGENT_DEEP_PLANNER_NUM_CTX"),
    ("AGENT_TASK_CONTINUITY_MODEL", "AGENT_TASK_CONTINUITY_NUM_CTX"),
    ("AGENT_SOCIAL_ATTENTION_MODEL", "AGENT_SOCIAL_ATTENTION_NUM_CTX"),
    ("AGENT_SKILL_SELECTION_MODEL", "AGENT_SKILL_SELECTION_NUM_CTX"),
    ("TTS_COSYVOICE_OLLAMA_MODEL", "TTS_COSYVOICE_OLLAMA_NUM_CTX"),
)

contexts = []
for model_key, context_key in role_contexts:
    if os.environ.get(model_key, "") != model:
        continue
    raw = os.environ.get(context_key, "")
    try:
        value = int(raw) if raw else fallback
    except ValueError:
        value = fallback
    if value > 0:
        contexts.append(value)

print(max(contexts or [fallback]))
PYCTX
}

echo "[warm-ollama] Hardware profile: ${CHROMIE_ACTIVE_PROFILE:-unknown}"
echo "[warm-ollama] Ollama URL: $OLLAMA_URL"
echo "[warm-ollama] Models: ${deduped_models[*]}"
echo "[warm-ollama] Flash attention: ${OLLAMA_FLASH_ATTENTION:-0}; KV cache: ${OLLAMA_KV_CACHE_TYPE:-f16}"
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
  local model_num_ctx
  local payload
  model_num_ctx="$(context_for_model "$model")"
  echo "[warm-ollama] Warming model topology: model=$model num_ctx=$model_num_ctx"
  payload="$(python3 - "$model" "$KEEP_ALIVE" "$model_num_ctx" "$NUM_PREDICT" <<'PY'
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
      if ! printf '%s' "$body" | python3 -c 'import json, sys; from shared.chromie_runtime.ollama_non_thinking import enforce_non_thinking_ollama_response; enforce_non_thinking_ollama_response(json.load(sys.stdin), structured_output=False)' >/dev/null; then
        echo "[warm-ollama][error] Model violated Chromie's non-thinking output contract: $model" >&2
        echo "[warm-ollama][hint] Use an explicit non-thinking/instruct model tag for cognition." >&2
        exit 1
      fi
      echo "[warm-ollama] Model warmed successfully: $model context=$model_num_ctx"
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

if [[ "$REQUIRE_ALL_WARM_MODELS_RESIDENT" =~ ^(1|true|yes|on)$ ]] && [ "${#deduped_models[@]}" -gt 1 ]; then
  ps_body="$(curl -fsS --max-time 10 "${OLLAMA_URL}/api/ps" || true)"
  if [ -z "$ps_body" ]; then
    echo "[warm-ollama][error] Could not verify concurrent model residency via ${OLLAMA_URL}/api/ps." >&2
    exit 1
  fi
  if ! printf '%s' "$ps_body" | python3 -c '
import json
import sys

expected = sys.argv[1:]
payload = json.load(sys.stdin)
loaded = {
    str(item.get("model") or item.get("name") or "")
    for item in payload.get("models", [])
    if isinstance(item, dict)
}
missing = [model for model in expected if model not in loaded]
if missing:
    print(
        "missing=" + ",".join(missing) + " loaded=" + ",".join(sorted(loaded)),
        file=sys.stderr,
    )
    raise SystemExit(1)
' "${deduped_models[@]}"; then
    echo "[warm-ollama][error] Selected models did not remain loaded concurrently." >&2
    echo "[warm-ollama][hint] This profile requires all warmed models to remain resident; check VRAM with nvidia-smi and loaded runners with: curl ${OLLAMA_URL}/api/ps" >&2
    exit 1
  fi
  echo "[warm-ollama] Concurrent residency verified for all selected models."
fi

echo "[warm-ollama] All selected models warmed successfully."
