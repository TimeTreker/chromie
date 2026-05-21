#!/usr/bin/env bash
set -euo pipefail
MODEL=${1:-${OLLAMA_MODEL:-gemma4:e2b}}
NUM_CTX=${OLLAMA_NUM_CTX:-2048}
NUM_PREDICT=${OLLAMA_NUM_PREDICT:-16}
KEEP_ALIVE=${OLLAMA_KEEP_ALIVE:-30m}

curl -s http://localhost:11434/api/generate \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"Say OK.\",\"stream\":false,\"think\":false,\"keep_alive\":\"$KEEP_ALIVE\",\"options\":{\"num_ctx\":$NUM_CTX,\"num_predict\":$NUM_PREDICT}}"
echo
