#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'USAGE'
Usage: ./scripts/compose.sh <docker compose args...>

Run Docker Compose with Chromie's generated runtime environment.

Examples:
  ./scripts/compose.sh ps
  ./scripts/compose.sh logs -f chromie-llm
  ./scripts/compose.sh exec chromie-agent python -m app.probe_capabilities --help
  ./scripts/compose.sh down
USAGE
}

if [ "$#" -eq 0 ] || [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ ! -f .env.runtime ]; then
  ./scripts/build_runtime_env.sh
fi

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

if [ -n "${CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE:-}" ]; then
  if [ ! -f "$CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE" ]; then
    echo "[compose][error] Service runtime override file not found: $CHROMIE_SERVICE_RUNTIME_OVERRIDE_FILE" >&2
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
      echo "[compose][error] Compose override file not found: $file" >&2
      exit 1
    fi
    COMPOSE_ARGS+=(-f "$file")
  done
fi

exec docker compose "${COMPOSE_ARGS[@]}" "$@"
