#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[orchestrator] Project root: $ROOT_DIR"

# Build and load the hardware-aware runtime environment before selecting conda/env/model settings.
if [ -x "./scripts/build_runtime_env.sh" ]; then
  echo "[orchestrator] Preparing hardware/runtime environment..."
  ./scripts/build_runtime_env.sh
fi

if [ -f ".env.runtime" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env.runtime
  set +a
fi

# Optional late-bound overrides are useful for supervised acceptance runs. They
# are sourced after .env.runtime so the runner can enable evidence capture and
# structured interaction without editing the operator's tracked/local config.
if [ -n "${ORCH_RUNTIME_OVERRIDE_FILE:-}" ]; then
  if [ ! -f "$ORCH_RUNTIME_OVERRIDE_FILE" ]; then
    echo "[orchestrator][error] Override file not found: $ORCH_RUNTIME_OVERRIDE_FILE" >&2
    exit 1
  fi
  echo "[orchestrator] Loading runtime overrides: $ORCH_RUNTIME_OVERRIDE_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ORCH_RUNTIME_OVERRIDE_FILE"
  set +a
fi

if [ "${CHROMIE_TTS_BACKEND:-cosyvoice3}" = "cosyvoice3" ] && [ "${TTS_COSYVOICE_COMPACT_COGNITION:-1}" = "1" ]; then
  COSYVOICE_BRAIN_MODEL="${TTS_COSYVOICE_OLLAMA_MODEL:-qwen3:4b}"
  export ROUTER_MODEL="$COSYVOICE_BRAIN_MODEL"
  export ROUTER_REVIEW_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_GOAL_ASSOCIATION_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_FAST_PLANNER_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_DEEP_PLANNER_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_RESPONSE_COMPOSER_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_TASK_CONTINUITY_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_SOCIAL_ATTENTION_MODEL="$COSYVOICE_BRAIN_MODEL"
  export AGENT_RESPONSE_REVIEW_MODEL="$COSYVOICE_BRAIN_MODEL"
  export OLLAMA_MODEL="$COSYVOICE_BRAIN_MODEL"
  export OLLAMA_MAX_LOADED_MODELS=1
  export TTS_URL="${TTS_URL:-ws://127.0.0.1:5000}"
  export TTS_SPEAKER_ID="${TTS_SPEAKER_ID:-default}"
  export ORCH_TTS_CONCURRENCY=1
  echo "[orchestrator] CosyVoice shared-GPU cognition: $COSYVOICE_BRAIN_MODEL"
fi


CONDA_ENV_NAME="${CONDA_ENV_NAME:-${CHROMIE_CONDA_ENV:-Chromie}}"
echo "[orchestrator] Using conda env: $CONDA_ENV_NAME"

# Make conda available in non-interactive shells.
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base)"
elif [ -x "$HOME/miniconda3/bin/conda" ]; then
  CONDA_BASE="$HOME/miniconda3"
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
  CONDA_BASE="$HOME/anaconda3"
else
  echo "[orchestrator][error] conda not found." >&2
  echo "[orchestrator][error] Please install conda or set PATH so 'conda' is available." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV_NAME"

echo "[orchestrator] Python: $(which python)"

# Install host Python dependencies only when orchestrator/requirements.txt changed.
if [ -x "./scripts/install_orchestrator_deps.sh" ]; then
  ./scripts/install_orchestrator_deps.sh
else
  echo "[orchestrator][warn] scripts/install_orchestrator_deps.sh not found; skipping dependency check."
fi

# Prevent duplicate microphone/VAD sessions from accidentally running two orchestrators.
LOCK_FILE="${ORCH_LOCK_FILE:-/tmp/chromie-orchestrator.lock}"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[orchestrator][error] Another orchestrator process is already running: $LOCK_FILE" >&2
  echo "[orchestrator][error] Stop the old process or remove the stale lock if you are sure it is not running." >&2
  exit 1
fi

if [ "${WARM_OLLAMA_BEFORE_ORCH:-1}" = "1" ]; then
  mapfile -t WARM_MODELS < <(./scripts/list_runtime_ollama_models.sh)
  echo "[orchestrator] Active profile models: ${WARM_MODELS[*]}"
  ./scripts/warm_ollama.sh "${WARM_MODELS[@]}"
fi
echo "[orchestrator] Starting..."
python -m orchestrator.orchestrator
