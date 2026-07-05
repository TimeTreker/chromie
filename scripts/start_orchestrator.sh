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
  WARM_MODELS=("${AGENT_MODEL:-gemma4:e2b}")
  if [[ "${AGENT_RESPONSE_REVIEW_ENABLED:-0}" =~ ^(1|true|yes|on)$ ]]; then
    WARM_MODELS+=("${AGENT_RESPONSE_REVIEW_MODEL:-gemma4:e2b}")
  fi
  if [[ "${ROUTER_USE_LLM:-0}" =~ ^(1|true|yes|on)$ ]]; then
    WARM_MODELS=("${ROUTER_MODEL:-qwen3:0.6b}" "${WARM_MODELS[@]}")
    if [ -n "${ROUTER_REVIEW_MODEL:-}" ] && {
      [[ "${ROUTER_POST_INTERRUPT_REVIEW_ENABLED:-0}" =~ ^(1|true|yes|on)$ ]] ||
        [[ "${ROUTER_SLOW_REVIEW_RECOVERY_ENABLED:-1}" =~ ^(1|true|yes|on)$ ]]
    }; then
      WARM_MODELS+=("${ROUTER_REVIEW_MODEL}")
    fi
  fi
  ./scripts/warm_ollama.sh "${WARM_MODELS[@]}"
fi

echo "[orchestrator] Starting..."
python -m orchestrator.orchestrator
