#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -z "${CHROMIE_ACTIVE_PROFILE:-}" ]; then
  ./scripts/build_runtime_env.sh >/dev/null
  set -a
  # shellcheck disable=SC1091
  source .env.runtime
  set +a
fi

is_enabled() {
  case "${1:-0}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

models=()
append_model() {
  local model="${1:-}"
  [ -n "$model" ] || return 0
  local existing
  for existing in "${models[@]:-}"; do
    [ "$existing" != "$model" ] || return 0
  done
  models+=("$model")
}

if is_enabled "${ROUTER_USE_LLM:-0}"; then
  append_model "${ROUTER_MODEL:-}"
  if [ -n "${ROUTER_REVIEW_MODEL:-}" ] && {
    is_enabled "${ROUTER_POST_INTERRUPT_REVIEW_ENABLED:-0}" ||
      is_enabled "${ROUTER_SLOW_REVIEW_RECOVERY_ENABLED:-1}" ||
      is_enabled "${ROUTER_GENERIC_CHAT_REVIEW_ENABLED:-1}"
  }; then
    append_model "$ROUTER_REVIEW_MODEL"
  fi
fi

if is_enabled "${AGENT_USE_LLM:-1}"; then
  append_model "${AGENT_MODEL:-${OLLAMA_MODEL:-}}"
fi
if is_enabled "${AGENT_GOAL_ASSOCIATION_ENABLED:-1}"; then
  append_model "${AGENT_GOAL_ASSOCIATION_MODEL:-}"
fi
if is_enabled "${AGENT_FAST_PLANNER_ENABLED:-1}"; then
  append_model "${AGENT_FAST_PLANNER_MODEL:-}"
fi
if is_enabled "${AGENT_DEEP_PLANNER_ENABLED:-1}"; then
  append_model "${AGENT_DEEP_PLANNER_MODEL:-}"
fi
if is_enabled "${AGENT_RESPONSE_COMPOSER_ENABLED:-1}"; then
  append_model "${AGENT_RESPONSE_COMPOSER_MODEL:-}"
fi
if is_enabled "${AGENT_TOOL_RESULT_INTERPRETER_ENABLED:-1}"; then
  append_model "${AGENT_TOOL_RESULT_INTERPRETER_MODEL:-}"
fi
if is_enabled "${AGENT_TASK_CONTINUITY_ENABLED:-1}"; then
  append_model "${AGENT_TASK_CONTINUITY_MODEL:-}"
fi
if [ "${AGENT_SOCIAL_ATTENTION_MODE:-off}" != "off" ]; then
  append_model "${AGENT_SOCIAL_ATTENTION_MODEL:-}"
fi
if is_enabled "${AGENT_RESPONSE_REVIEW_ENABLED:-0}"; then
  append_model "${AGENT_RESPONSE_REVIEW_MODEL:-}"
fi

if [ "${#models[@]}" -eq 0 ]; then
  echo "[models][error] Active runtime selected no Ollama models." >&2
  exit 1
fi

printf '%s\n' "${models[@]}"
