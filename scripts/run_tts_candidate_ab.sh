#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="${TTS_AB_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
REFERENCE_DIR="${TTS_AB_REFERENCE_DIR:-.chromie/evidence/tts-provider-ab/reference}"
OUTPUT_DIR="${TTS_AB_OUTPUT_DIR:-.chromie/evidence/tts-provider-ab/$RUN_ID}"
WAIT_TIMEOUT="${TTS_CANDIDATE_WAIT_TIMEOUT_SEC:-1800}"
KEEP_CANDIDATES="${TTS_AB_KEEP_CANDIDATES:-0}"

export TTS_REFERENCE_DIR="$REFERENCE_DIR"

restore_default() {
  if [ "$KEEP_CANDIDATES" != "1" ]; then
    ./scripts/compose.sh --profile tts-evaluation stop \
      chromie-tts-oute chromie-tts-qwen3 || true
    ./scripts/compose.sh up -d --no-build chromie-tts chromie-llm || true
  fi
}
trap restore_default EXIT

if [ "${TTS_AB_SKIP_REFERENCE_GENERATION:-0}" = "1" ]; then
  echo "[tts-ab] Using the existing authorized reference voice..."
  python scripts/tts_reference.py validate --reference-dir "$REFERENCE_DIR"
else
  echo "[tts-ab] Starting the OuteTTS fallback to generate an evaluation-only reference..."
  reference_up=(--profile tts-evaluation up -d --wait --wait-timeout "$WAIT_TIMEOUT")
  if [ "${TTS_AB_SKIP_REFERENCE_BUILD:-0}" = "1" ]; then
    reference_up+=(--no-build)
  else
    reference_up+=(--build)
  fi
  reference_up+=(chromie-tts-oute)
  ./scripts/compose.sh "${reference_up[@]}"

  echo "[tts-ab] Generating the shared evaluation reference voice..."
  python scripts/prepare_tts_reference.py \
    --url ws://127.0.0.1:5001 \
    --output-dir "$REFERENCE_DIR"
fi

python scripts/tts_reference.py validate --reference-dir "$REFERENCE_DIR"

echo "[tts-ab] Releasing OuteTTS and Ollama GPU memory for the isolated comparison..."
./scripts/compose.sh --profile tts-evaluation stop chromie-tts-oute
./scripts/compose.sh stop chromie-llm chromie-tts || true

compose_up=(--profile tts-evaluation up -d --wait --wait-timeout "$WAIT_TIMEOUT")
if [ "${TTS_AB_SKIP_BUILD:-0}" != "1" ]; then
  compose_up+=(--build)
else
  compose_up+=(--no-build)
fi
compose_up+=(chromie-tts chromie-tts-qwen3)

echo "[tts-ab] Building and starting CosyVoice3 and Qwen3-TTS..."
./scripts/compose.sh "${compose_up[@]}"

echo "[tts-ab] Running the identical committed A/B matrix..."
python scripts/tts_provider_ab.py \
  --provider cosyvoice3=ws://127.0.0.1:5000 \
  --provider qwen3_tts=ws://127.0.0.1:5002 \
  --warmup "${TTS_AB_WARMUP:-1}" \
  --timeout "${TTS_AB_CASE_TIMEOUT_SEC:-300}" \
  --output-dir "$OUTPUT_DIR"

echo "[tts-ab] Objective result: $OUTPUT_DIR/result.json"
echo "[tts-ab] Listening review required: $OUTPUT_DIR/listening-review.json"
