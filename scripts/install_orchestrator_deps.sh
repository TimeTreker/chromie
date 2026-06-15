#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REQ_FILE="${ORCH_REQUIREMENTS_FILE:-orchestrator/requirements.txt}"
STATE_DIR="${CHROMIE_STATE_DIR:-.chromie}"
HASH_FILE="$STATE_DIR/orchestrator_requirements.sha256"
AUTO_INSTALL="${ORCH_AUTO_INSTALL_DEPS:-1}"
FORCE_INSTALL="${ORCH_FORCE_INSTALL_DEPS:-0}"

case "${AUTO_INSTALL,,}" in
  0|false|no|off)
    echo "[deps] Skipping host orchestrator dependency install: ORCH_AUTO_INSTALL_DEPS=$AUTO_INSTALL"
    exit 0
    ;;
esac

if [ ! -f "$REQ_FILE" ]; then
  echo "[deps][error] Requirements file not found: $REQ_FILE" >&2
  exit 1
fi

mkdir -p "$STATE_DIR"

if command -v sha256sum >/dev/null 2>&1; then
  REQUIREMENTS_HASH="$(sha256sum "$REQ_FILE" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  REQUIREMENTS_HASH="$(shasum -a 256 "$REQ_FILE" | awk '{print $1}')"
else
  REQUIREMENTS_HASH="$(python - <<'PY'
from pathlib import Path
import hashlib
path = Path("orchestrator/requirements.txt")
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
)"
fi

PYTHON_ID="$(python -c 'import sys; print(f"{sys.executable}|{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
CURRENT_HASH="${REQUIREMENTS_HASH}|${PYTHON_ID}"

PREVIOUS_HASH=""
if [ -f "$HASH_FILE" ]; then
  PREVIOUS_HASH="$(cat "$HASH_FILE" || true)"
fi

if [ "$FORCE_INSTALL" != "1" ] && [ "$CURRENT_HASH" = "$PREVIOUS_HASH" ]; then
  echo "[deps] Host orchestrator dependencies are up to date."
  exit 0
fi

# A stale or missing hash file must not force a network operation when the
# active Python environment already satisfies the Orchestrator imports.
if [ "$FORCE_INSTALL" != "1" ] && python - <<'PYIMPORT' >/dev/null 2>&1
import aiohttp
import dotenv
import httpx
import mcp
import numpy
import pydantic
import scipy
import sounddevice
import webrtcvad
import websockets
PYIMPORT
then
  echo "$CURRENT_HASH" > "$HASH_FILE"
  echo "[deps] Host orchestrator dependencies are already importable."
  exit 0
fi

echo "[deps] Installing host orchestrator dependencies from $REQ_FILE"
echo "[deps] Python: $(command -v python)"
python -m pip install -U pip
python -m pip install -r "$REQ_FILE"

if [ "${ORCH_PIP_CHECK:-0}" = "1" ]; then
  python -m pip check
fi

echo "$CURRENT_HASH" > "$HASH_FILE"
echo "[deps] Host orchestrator dependencies installed."
