#!/usr/bin/env bash
set -euo pipefail

quote() {
  printf '%q' "$1"
}

emit() {
  local key="$1"
  local value="${2:-}"
  printf '%s=%s\n' "$key" "$(quote "$value")"
}

cpu_arch="$(uname -m 2>/dev/null || echo unknown)"
cpu_cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 0)"
mem_total_mib="$(awk '/MemTotal:/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)"
kernel="$(uname -sr 2>/dev/null || echo unknown)"

cpu_model=""
if [ -r /proc/cpuinfo ]; then
  cpu_model="$(awk -F': ' '/model name/ {print $2; exit} /Hardware/ {print $2; exit} /Processor/ {print $2; exit}' /proc/cpuinfo || true)"
fi
[ -n "$cpu_model" ] || cpu_model="unknown"

is_jetson="0"
jetson_model=""
if [ -r /proc/device-tree/model ]; then
  jetson_model="$(tr -d '\0' < /proc/device-tree/model || true)"
  case "$jetson_model" in
    *Jetson*|*NVIDIA*Orin*|*Thor*) is_jetson="1" ;;
  esac
fi

gpu_name=""
gpu_compute_cap=""
gpu_memory_total_mib=""
detected_cuda_arch=""

if command -v nvidia-smi >/dev/null 2>&1; then
  gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1 | sed 's/^ *//;s/ *$//' || true)"
  gpu_compute_cap="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -n1 | sed 's/^ *//;s/ *$//' || true)"
  gpu_memory_total_mib="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1 | sed 's/^ *//;s/ *$//' || true)"
fi

# Jetson usually does not provide a desktop-style nvidia-smi. Infer common CUDA arch from model.
if [ -z "$gpu_compute_cap" ] && [ -n "$jetson_model" ]; then
  case "$jetson_model" in
    *Orin*) gpu_compute_cap="8.7" ;;
    *Thor*) gpu_compute_cap="12.0" ;;
  esac
fi

if [ -n "$gpu_compute_cap" ]; then
  detected_cuda_arch="$(printf '%s' "$gpu_compute_cap" | awk -F. '{print $1 $2}')"
fi

emit CHROMIE_OS_KERNEL "$kernel"
emit CHROMIE_CPU_ARCH "$cpu_arch"
emit CHROMIE_CPU_MODEL "$cpu_model"
emit CHROMIE_CPU_CORES "$cpu_cores"
emit CHROMIE_MEM_TOTAL_MIB "$mem_total_mib"
emit CHROMIE_IS_JETSON "$is_jetson"
emit CHROMIE_JETSON_MODEL "$jetson_model"
emit CHROMIE_NVIDIA_GPU_NAME "$gpu_name"
emit CHROMIE_NVIDIA_COMPUTE_CAP "$gpu_compute_cap"
emit CHROMIE_NVIDIA_MEMORY_TOTAL_MIB "$gpu_memory_total_mib"
emit CHROMIE_DETECTED_CUDA_ARCH "$detected_cuda_arch"
