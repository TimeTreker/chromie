#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_ID="${TTS_AB_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
OUTPUT_DIR="${TTS_AB_OUTPUT_DIR:-.chromie/evidence/tts-provider-ab/$RUN_ID}"
WAIT_TIMEOUT="${TTS_CANDIDATE_WAIT_TIMEOUT_SEC:-1800}"
KEEP_CANDIDATES="${TTS_AB_KEEP_CANDIDATES:-0}"
TTS_VOICE_ROOT="${TTS_VOICE_ROOT:-assets/tts/voices}"
TTS_VOICE_ROOT="$(python3 - "$ROOT_DIR" "$TTS_VOICE_ROOT" <<'PY_TTS_VOICE_ROOT'
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
voice_root = Path(sys.argv[2]).expanduser()
if not voice_root.is_absolute():
    voice_root = root / voice_root
print(voice_root.resolve())
PY_TTS_VOICE_ROOT
)"
export TTS_VOICE_ROOT

restore_default() {
  if [ "$KEEP_CANDIDATES" != "1" ]; then
    ./scripts/compose.sh --profile tts-evaluation stop \
      chromie-tts-oute chromie-tts-qwen3 || true
    ./scripts/compose.sh up -d --no-build chromie-tts chromie-llm || true
  fi
}
trap restore_default EXIT

python3 - "$TTS_VOICE_ROOT" <<'PY_TTS_CATALOG'
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd() / "tts"))
from voice_catalog import validate_voice_catalog
catalog = validate_voice_catalog(Path(sys.argv[1]))
print(
    f"[tts-ab] voice catalog revision={catalog.revision} "
    f"default={catalog.default_speaker_id} speakers={','.join(catalog.speaker_ids())}"
)
PY_TTS_CATALOG

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

echo "[tts-ab] Building and starting CosyVoice3 and Qwen3-TTS with chromie_mixed..."
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
