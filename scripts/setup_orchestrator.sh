#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH_DIR="$ROOT_DIR/orchestrator"

cd "$ORCH_DIR"

echo "[setup] Project root: $ROOT_DIR"
echo "[setup] Orchestrator dir: $ORCH_DIR"

if [[ ! -f ".env.local" ]]; then
  cp .env.local.example .env.local
  echo "[setup] Created orchestrator/.env.local from example. Edit ORCH_INPUT_DEVICE and ORCH_OUTPUT_DEVICE after running list_devices.py."
else
  echo "[setup] orchestrator/.env.local already exists; keeping it."
fi

if [[ "${SKIP_VENV:-0}" == "1" ]]; then
  echo "[setup] SKIP_VENV=1, installing requirements into the current Python environment."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
else
  if [[ ! -d ".venv" ]]; then
    echo "[setup] Creating local venv at orchestrator/.venv"
    python3 -m venv .venv
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

echo
echo "[setup] Listing audio devices:"
python list_devices.py

cd "$ROOT_DIR"

echo
echo "[setup] Done. Next steps:"
echo "  1. Edit $ORCH_DIR/.env.local and set ORCH_INPUT_DEVICE / ORCH_OUTPUT_DEVICE."
echo "  2. Start Docker services: ./scripts/start_services.sh"
echo "  3. Activate orchestrator/.venv if this script created it."
echo "  4. Run orchestrator: python -m orchestrator.orchestrator"
