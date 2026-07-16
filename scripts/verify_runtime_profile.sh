#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env.runtime ]; then
  echo "[profile-check][error] .env.runtime is missing." >&2
  exit 1
fi
if [ ! -f .chromie/runtime_profile.json ]; then
  echo "[profile-check][error] .chromie/runtime_profile.json is missing." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

read_manifest_field() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path('.chromie/runtime_profile.json').read_text())
print(payload[sys.argv[1]])
PY
}

manifest_profile="$(read_manifest_field active_profile)"
manifest_fingerprint="$(read_manifest_field fingerprint)"
if [ "$manifest_profile" != "${CHROMIE_ACTIVE_PROFILE:-}" ]; then
  echo "[profile-check][error] Manifest profile '$manifest_profile' does not match .env.runtime '${CHROMIE_ACTIVE_PROFILE:-}'" >&2
  exit 1
fi
if [ "$manifest_fingerprint" != "${CHROMIE_RUNTIME_ENV_FINGERPRINT:-}" ]; then
  echo "[profile-check][error] Manifest fingerprint does not match .env.runtime." >&2
  exit 1
fi

services=(chromie-asr chromie-llm chromie-tts chromie-router chromie-agent)
declare -A service_env
for service in "${services[@]}"; do
  container_id="$(docker compose --env-file .env.runtime -f docker-compose.yml ps -q "$service")"
  if [ -z "$container_id" ]; then
    echo "[profile-check][error] $service is not running." >&2
    exit 1
  fi
  service_env["$service"]="$(docker inspect "$container_id" --format '{{range .Config.Env}}{{println .}}{{end}}')"
done

value_from_dump() {
  local dump="$1" name="$2"
  printf '%s\n' "$dump" | awk -F= -v key="$name" '$1 == key {sub(/^[^=]*=/, ""); print; exit}'
}

failures=0
check_value() {
  local service="$1" name="$2" expected actual
  expected="${!name-}"
  actual="$(value_from_dump "${service_env[$service]}" "$name")"
  if [ "$actual" != "$expected" ]; then
    echo "[profile-check][error] $service $name mismatch: runtime='$expected' container='$actual'" >&2
    failures=$((failures + 1))
  fi
}

for service in "${services[@]}"; do
  check_value "$service" CHROMIE_ACTIVE_PROFILE
  check_value "$service" CHROMIE_RUNTIME_ENV_FINGERPRINT
done

for name in \
  AGENT_MODEL \
  AGENT_GOAL_ASSOCIATION_MODEL \
  AGENT_FAST_PLANNER_MODEL \
  AGENT_DEEP_PLANNER_MODEL \
  AGENT_RESPONSE_COMPOSER_MODEL \
  AGENT_TASK_CONTINUITY_MODEL \
  AGENT_SOCIAL_ATTENTION_MODEL \
  AGENT_RESPONSE_REVIEW_MODEL; do
  check_value chromie-agent "$name"
done
for name in ROUTER_MODEL ROUTER_REVIEW_MODEL; do
  check_value chromie-router "$name"
done
check_value chromie-tts TTS_CUDA_ARCH

tts_container_id="$(docker compose --env-file .env.runtime -f docker-compose.yml ps -q chromie-tts)"
tts_image_id="$(docker inspect "$tts_container_id" --format '{{.Image}}')"
built_cuda_arch="$(docker image inspect "$tts_image_id" --format '{{index .Config.Labels "org.chromie.tts-cuda-arch"}}')"
built_profile="$(docker image inspect "$tts_image_id" --format '{{index .Config.Labels "org.chromie.hardware-profile"}}')"
if [ "$built_cuda_arch" != "${TTS_CUDA_ARCH:-}" ]; then
  echo "[profile-check][error] chromie-tts image CUDA arch '$built_cuda_arch' does not match detected profile arch '${TTS_CUDA_ARCH:-}'." >&2
  echo "[profile-check][hint] Rebuild with: BUILD=1 ./scripts/start_services.sh" >&2
  failures=$((failures + 1))
fi
if [ -z "$built_profile" ] || [ "$built_profile" = "unknown" ]; then
  echo "[profile-check][error] chromie-tts image lacks an automatic-profile build label." >&2
  echo "[profile-check][hint] Rebuild with: BUILD=1 ./scripts/start_services.sh" >&2
  failures=$((failures + 1))
fi

if [ "$failures" -ne 0 ]; then
  echo "[profile-check][error] Runtime containers or images do not match the auto-detected hardware profile." >&2
  exit 1
fi

echo "[profile-check] Auto-detected profile: ${CHROMIE_ACTIVE_PROFILE}"
echo "[profile-check] Runtime fingerprint: ${CHROMIE_RUNTIME_ENV_FINGERPRINT}"
echo "[profile-check] TTS image: built_profile=${built_profile} cuda_arch=${built_cuda_arch}"
echo "[profile-check] Active Ollama models: $(./scripts/list_runtime_ollama_models.sh | paste -sd, -)"
echo "[profile-check] All container environments match .env.runtime."
