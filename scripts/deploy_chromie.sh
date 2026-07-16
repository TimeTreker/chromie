#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BUILD_IMAGES=1
REBUILD_NO_CACHE=0
RUN_TESTS=1
PULL_EXTERNAL=1
START_AFTER=0
KEEP_SERVICES=0
START_ORCHESTRATOR=1
MCP_URL="${SORIDORMI_MCP_URL:-http://127.0.0.1:8000/mcp}"

usage() {
  cat <<'USAGE'
Usage: ./scripts/deploy_chromie.sh [options]

Prepare a fresh Chromie checkout for local simulator deployment. This script
does not own Soridormi; start Soridormi separately, then run Chromie with
scripts/start_chromie.sh or scripts/start_voice_mujoco.sh.

Options:
  --build                 Build Chromie-owned Docker images (default)
  --skip-build            Prepare env/tests only; do not build images
  --rebuild-no-cache      Rebuild Chromie images without Docker cache
  --skip-tests            Skip INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh
  --no-pull-external      Do not pull external images such as Ollama
  --start                 Start Chromie after deployment
  --mcp-url URL           Soridormi MCP URL for --start
                          default: http://127.0.0.1:8000/mcp
  --keep-services         With --start, leave Chromie containers running
  --no-orchestrator       With --start, skip host Orchestrator
  -h, --help              Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --build) BUILD_IMAGES=1; shift ;;
    --skip-build) BUILD_IMAGES=0; shift ;;
    --rebuild-no-cache) BUILD_IMAGES=1; REBUILD_NO_CACHE=1; shift ;;
    --skip-tests) RUN_TESTS=0; shift ;;
    --no-pull-external) PULL_EXTERNAL=0; shift ;;
    --start) START_AFTER=1; shift ;;
    --mcp-url) MCP_URL="${2:?--mcp-url requires a URL}"; shift 2 ;;
    --keep-services) KEEP_SERVICES=1; shift ;;
    --no-orchestrator) START_ORCHESTRATOR=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[deploy-chromie][error] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for cmd in docker git python3; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "[deploy-chromie][error] Required command not found: $cmd" >&2
    exit 1
  }
done

docker info >/dev/null 2>&1 || {
  echo "[deploy-chromie][error] Docker daemon is not reachable." >&2
  exit 1
}

for path in \
  .env.common \
  .env.local.example \
  docker-compose.yml \
  orchestrator/.env.local.example \
  requirements-test.txt \
  scripts/build_runtime_env.sh \
  scripts/generate_runtime_env.py \
  scripts/verify_runtime_profile.sh \
  scripts/list_runtime_ollama_models.sh \
  scripts/compose.sh \
  scripts/run_tests.sh \
  scripts/start_chromie.sh; do
  [ -e "$path" ] || {
    echo "[deploy-chromie][error] Missing repository file: $path" >&2
    exit 1
  }
done

if [ ! -f .env.local ]; then
  cp .env.local.example .env.local
  echo "[deploy-chromie] Created .env.local from .env.local.example."
fi

if [ ! -f orchestrator/.env.local ]; then
  cp orchestrator/.env.local.example orchestrator/.env.local
  echo "[deploy-chromie] Created orchestrator/.env.local from template."
fi

echo "[deploy-chromie] Building generated runtime environment..."
./scripts/build_runtime_env.sh

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

mkdir -p .chromie hf_cache "${OLLAMA_DATA_DIR:-ollama_data}" recordings

if [ -n "${CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE:-}" ]; then
  if [ ! -f "$CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE" ]; then
    echo "[deploy-chromie][error] Service runtime override file not found: $CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE"
  set +a
fi

COMPOSE_ARGS=(--env-file .env.runtime -f docker-compose.yml)
if [ -n "${CHROMIE_COMPOSE_OVERRIDE_FILES:-}" ]; then
  IFS=',' read -ra override_files <<< "${CHROMIE_COMPOSE_OVERRIDE_FILES}"
  for file in "${override_files[@]}"; do
    file="$(echo "$file" | xargs)"
    [ -n "$file" ] || continue
    if [ ! -f "$file" ]; then
      echo "[deploy-chromie][error] Compose override file not found: $file" >&2
      exit 1
    fi
    COMPOSE_ARGS+=(-f "$file")
  done
fi

if [ "$PULL_EXTERNAL" = "1" ]; then
  echo "[deploy-chromie] Pulling external runtime images..."
  docker compose "${COMPOSE_ARGS[@]}" pull chromie-llm
else
  echo "[deploy-chromie] Skipping external image pull."
fi

if [ "$BUILD_IMAGES" = "1" ]; then
  build_services=(chromie-asr chromie-tts chromie-router chromie-agent)
  if [ "$REBUILD_NO_CACHE" = "1" ]; then
    echo "[deploy-chromie] Building Chromie images with --no-cache..."
    docker compose "${COMPOSE_ARGS[@]}" build --no-cache "${build_services[@]}"
  else
    echo "[deploy-chromie] Building Chromie images with Docker cache..."
    docker compose "${COMPOSE_ARGS[@]}" build "${build_services[@]}"
  fi
else
  echo "[deploy-chromie] Skipping image build."
fi

if [ "$RUN_TESTS" = "1" ]; then
  echo "[deploy-chromie] Running full host validation with declared test dependencies..."
  INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh
else
  echo "[deploy-chromie] Skipping tests."
fi

cat <<EOF_DONE

======================================================================
Chromie deployment preparation complete
======================================================================
Runtime env: .env.runtime
Host overrides:
  .env.local
  orchestrator/.env.local

Start after Soridormi is running:
  ./scripts/start_chromie.sh --mcp-url ${MCP_URL}

Or run the paired stack from Chromie:
  ./scripts/start_voice_mujoco.sh --soridormi-repo ../soridormi
======================================================================
EOF_DONE

if [ "$START_AFTER" = "1" ]; then
  start_args=(--mcp-url "$MCP_URL")
  [ "$KEEP_SERVICES" = "1" ] && start_args+=(--keep-services)
  [ "$START_ORCHESTRATOR" = "0" ] && start_args+=(--no-orchestrator)
  exec ./scripts/start_chromie.sh "${start_args[@]}"
fi
