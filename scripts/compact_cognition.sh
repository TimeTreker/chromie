# shellcheck shell=bash
# Shared-GPU compact cognition for the maintained CosyVoice3 TTS default.
#
# Sourced by start_services.sh, start_orchestrator.sh and start_chromie.sh so
# the three launchers apply one rule: with the CosyVoice3 backend and
# TTS_COSYVOICE_COMPACT_COGNITION=1 (the .env.common default), every cognitive
# role runs TTS_COSYVOICE_OLLAMA_MODEL and Ollama keeps one resident model.
# Role context budgets stay as generated in .env.runtime.

# Every model key the compact plan replaces. start_services.sh records these
# (plus OLLAMA_MAX_LOADED_MODELS) for verify_runtime_profile.sh.
CHROMIE_COMPACT_COGNITION_MODEL_KEYS=(
  AGENT_USER_MEANING_INTERPRETER_MODEL
  AGENT_COGNITIVE_GATEWAY_ATTENTION_MODEL
  AGENT_MODEL
  AGENT_GOAL_ASSOCIATION_MODEL
  AGENT_COGNITIVE_ACTIVATION_MODEL
  AGENT_PLANNER_MODEL
  AGENT_DELIBERATIVE_MODEL
  OLLAMA_MODEL
)

# Usage: chromie_apply_compact_cognition <tts-backend>
# Exports the compact model plan and sets CHROMIE_COMPACT_COGNITION_MODEL when
# it applies; returns 1 and changes nothing otherwise.
chromie_apply_compact_cognition() {
  case "${1,,}" in
    cosyvoice|cosyvoice3) ;;
    *) return 1 ;;
  esac
  [ "${TTS_COSYVOICE_COMPACT_COGNITION:-1}" = "1" ] || return 1
  CHROMIE_COMPACT_COGNITION_MODEL="${TTS_COSYVOICE_OLLAMA_MODEL:-qwen3:4b}"
  local key
  for key in "${CHROMIE_COMPACT_COGNITION_MODEL_KEYS[@]}"; do
    export "$key=$CHROMIE_COMPACT_COGNITION_MODEL"
  done
  export OLLAMA_MAX_LOADED_MODELS=1
}
