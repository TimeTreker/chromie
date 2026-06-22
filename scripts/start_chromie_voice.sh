#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[chromie][warn] scripts/start_chromie_voice.sh is deprecated; use scripts/start_chromie.sh." >&2
exec "$ROOT_DIR/scripts/start_chromie.sh" "$@"
