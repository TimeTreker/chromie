#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONDA_ENV_NAME="${CONDA_ENV_NAME:-Chromie}"

echo "[orchestrator] Project root: $ROOT_DIR"
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
echo "[orchestrator] Starting..."

if [ "${WARM_OLLAMA_BEFORE_ORCH:-1}" = "1" ]; then
  ./scripts/warm_ollama.sh "${AGENT_MODEL:-gemma4:26b}"
fi

python -m orchestrator.orchestrator
