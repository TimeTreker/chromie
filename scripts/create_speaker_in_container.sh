#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env.runtime ]; then
  ./scripts/build_runtime_env.sh
fi

WAV_PATH="${1:-/app/speakers/chromie_voice.wav}"
SPEAKER_ID="${2:-chromie_voice}"
MAKE_DEFAULT="0"
TRANSCRIPT_PATH="${4:-${WAV_PATH%.*}.txt}"

if [[ "${3:-}" == "--make-default" ]] || [[ "${3:-}" == "1" ]] || [[ "${3:-}" == "true" ]]; then
  MAKE_DEFAULT="1"
fi

# This helper is specific to the optional OuteTTS fallback. CosyVoice uses
# scripts/tts_reference.py to install its authorized reference voice.
# This uses the exact-transcript validation and pinned Whisper alignment path
# built into tts/server.py. The runtime image supplies FFmpeg for decoding.
docker compose --env-file .env.runtime -f docker-compose.yml --profile tts-evaluation exec -T \
  -e WAV_PATH="$WAV_PATH" \
  -e SPEAKER_ID="$SPEAKER_ID" \
  -e MAKE_DEFAULT="$MAKE_DEFAULT" \
  -e TRANSCRIPT_PATH="$TRANSCRIPT_PATH" \
  chromie-tts-oute python - <<'PY'
import asyncio
import json
import os
from pathlib import Path
import websockets

async def main():
    wav_path = os.environ["WAV_PATH"]
    speaker_id = os.environ["SPEAKER_ID"]
    make_default = os.environ.get("MAKE_DEFAULT") == "1"
    transcript_path = Path(os.environ["TRANSCRIPT_PATH"])
    if not transcript_path.is_file():
        raise SystemExit(f"Missing exact transcript sidecar: {transcript_path}")
    transcript = transcript_path.read_text(encoding="utf-8").strip()
    if not transcript:
        raise SystemExit(f"Empty exact transcript sidecar: {transcript_path}")

    payload = {
        "type": "create_speaker",
        "request_id": f"create-{speaker_id}",
        "speaker_id": speaker_id,
        "wav_path": wav_path,
        "make_default": make_default,
        "transcript": transcript,
    }

    async with websockets.connect("ws://localhost:5000", max_size=10**7) as ws:
        await ws.send(json.dumps(payload))
        while True:
            msg = await ws.recv()
            print(msg)
            data = json.loads(msg)
            if data.get("type") in {"speaker_created", "error"}:
                if data.get("type") == "error":
                    raise SystemExit(1)
                return

asyncio.run(main())
PY
