#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/build_runtime_env.sh >/dev/null

set -a
# shellcheck disable=SC1091
source .env.runtime
set +a

cat <<EOF
Chromie hardware/runtime profile
================================
Profile:        ${CHROMIE_ACTIVE_PROFILE:-unknown}
CPU arch:       ${CHROMIE_CPU_ARCH:-unknown}
CPU model:      ${CHROMIE_CPU_MODEL:-unknown}
CPU cores:      ${CHROMIE_CPU_CORES:-unknown}
Memory:         ${CHROMIE_MEM_TOTAL_MIB:-unknown} MiB
Jetson:         ${CHROMIE_IS_JETSON:-0}
Jetson model:   ${CHROMIE_JETSON_MODEL:-}
GPU:            ${CHROMIE_NVIDIA_GPU_NAME:-unknown}
GPU compute:    ${CHROMIE_NVIDIA_COMPUTE_CAP:-unknown}
GPU memory:     ${CHROMIE_NVIDIA_MEMORY_TOTAL_MIB:-unknown} MiB
TTS CUDA arch:  ${TTS_CUDA_ARCH:-unset}

Key runtime config
------------------
ASR_BACKEND=${ASR_BACKEND:-unset}
ASR_MODE=${ASR_MODE:-unset}
ASR_MODEL=${ASR_MODEL:-unset}
ASR_COMPUTE_TYPE=${ASR_COMPUTE_TYPE:-unset}
ROUTER_USE_LLM=${ROUTER_USE_LLM:-unset}
AGENT_MODEL=${AGENT_MODEL:-unset}
AGENT_TIMEOUT_MS=${AGENT_TIMEOUT_MS:-unset}
ORCH_AGENT_TIMEOUT_MS=${ORCH_AGENT_TIMEOUT_MS:-unset}
OLLAMA_CONTEXT_LENGTH=${OLLAMA_CONTEXT_LENGTH:-unset}
TTS_MODEL_SIZE=${TTS_MODEL_SIZE:-unset}
TTS_CONTEXT_SIZE=${TTS_CONTEXT_SIZE:-unset}
TTS_N_BATCH=${TTS_N_BATCH:-unset}
TTS_THREADS=${TTS_THREADS:-unset}

Generated files
---------------
.env.runtime
${CHROMIE_SYSTEM_INFO_FILE:-.chromie/system_info.env}
EOF
