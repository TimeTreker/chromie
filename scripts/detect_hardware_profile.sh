#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TMP_INFO="$(mktemp)"
trap 'rm -f "$TMP_INFO"' EXIT

./scripts/collect_system_info.sh > "$TMP_INFO"
# shellcheck disable=SC1090
source "$TMP_INFO"

jetson_model="${CHROMIE_JETSON_MODEL:-}"
gpu_name="${CHROMIE_NVIDIA_GPU_NAME:-}"
compute_cap="${CHROMIE_NVIDIA_COMPUTE_CAP:-}"
mem_mib="${CHROMIE_MEM_TOTAL_MIB:-0}"

# Prefer explicit Jetson model detection.
if [ "${CHROMIE_IS_JETSON:-0}" = "1" ]; then
  case "$jetson_model" in
    *"Orin Nano"*) echo "jetson_orin_nano_super"; exit 0 ;;
    *"AGX Orin"*) echo "jetson_agx_orin"; exit 0 ;;
    *"Thor"*) echo "jetson_thor"; exit 0 ;;
    *"Orin"*) echo "jetson_agx_orin"; exit 0 ;;
  esac
fi

# Desktop/discrete GPU detection by name.
case "$gpu_name" in
  *"RTX 5090"*) echo "rtx5090"; exit 0 ;;
  *"RTX 4090"*) echo "rtx4090"; exit 0 ;;
esac

# Fallback by compute capability when name is unavailable or vendor string differs.
case "$compute_cap" in
  12.0|12.*) echo "rtx5090"; exit 0 ;;
  8.9) echo "rtx4090"; exit 0 ;;
  8.7)
    # Orin-class but not identified through device-tree. Pick the smaller/safe Orin profile on low memory.
    if [ "${mem_mib:-0}" -le 20000 ]; then
      echo "jetson_orin_nano_super"
    else
      echo "jetson_agx_orin"
    fi
    exit 0
    ;;
esac

echo "default"
