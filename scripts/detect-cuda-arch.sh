#!/usr/bin/env bash
set -euo pipefail

DEFAULT_ARCH="${DEFAULT_CUDA_ARCH:-89}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "${DEFAULT_ARCH}"
  exit 0
fi

# Recent NVIDIA drivers support compute_cap directly.
if caps="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader,nounits 2>/dev/null)"; then
  archs="$(
    echo "$caps" \
      | tr -d ' ' \
      | awk -F. 'NF >= 2 { print $1 $2 }' \
      | sort -u \
      | paste -sd ';' -
  )"

  if [ -n "$archs" ]; then
    echo "$archs"
    exit 0
  fi
fi

# Fallback for older nvidia-smi versions.
names="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || true)"

case "$names" in
  *"RTX 5090"*|*"RTX 5080"*|*"RTX 5070"*)
    echo "120"
    ;;
  *"RTX 4090"*|*"RTX 4080"*|*"RTX 4070"*|*"RTX 4060"*)
    echo "89"
    ;;
  *)
    echo "${DEFAULT_ARCH}"
    ;;
esac
