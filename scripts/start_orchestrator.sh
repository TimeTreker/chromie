#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

LOCK_FILE="/tmp/chromie-orchestrator.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[orchestrator][error] Another orchestrator process is already running." >&2
  echo "[orchestrator][error] Stop it first: pkill -f 'python.*orchestrator'" >&2
  exit 1
fi

echo "[orchestrator] Project root: $ROOT_DIR"
echo "[orchestrator] Preparing hardware/runtime environment..."

./scripts/build_runtime_env.sh

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

echo "[orchestrator] Hardware profile: ${CHROMIE_ACTIVE_PROFILE:-unknown}"
echo "[orchestrator] Agent model: ${AGENT_MODEL:-unset}"
echo "[orchestrator] Agent timeout: ${ORCH_AGENT_TIMEOUT_MS:-unset}ms"

CONDA_ENV_NAME="${CHROMIE_CONDA_ENV:-${CONDA_ENV_NAME:-Chromie}}"

# Prefer conda because this is the user's current host setup.
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base)"
elif [ -x "$HOME/miniconda3/bin/conda" ]; then
  CONDA_BASE="$HOME/miniconda3"
elif [ -x "$HOME/anaconda3/bin/conda" ]; then
  CONDA_BASE="$HOME/anaconda3"
else
  CONDA_BASE=""
fi

if [ -n "$CONDA_BASE" ]; then
  # shellcheck disable=SC1091
  source "$CONDA_BASE/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV_NAME"
  echo "[orchestrator] Using conda env: $CONDA_ENV_NAME"
elif [ -d "orchestrator/.venv" ]; then
  # shellcheck disable=SC1091
  source orchestrator/.venv/bin/activate
  echo "[orchestrator] Using venv: orchestrator/.venv"
else
  echo "[orchestrator][warn] No conda or orchestrator/.venv found; using current Python."
fi

echo "[orchestrator] Python: $(command -v python)"

if [ "${WARM_OLLAMA_BEFORE_ORCH:-1}" = "1" ]; then
  ./scripts/warm_ollama.sh "${AGENT_MODEL:-${OLLAMA_MODEL:-gemma4:e2b}}"
fi

echo "[orchestrator] Starting..."
python -m orchestrator.orchestrator
