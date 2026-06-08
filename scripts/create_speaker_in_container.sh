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

if [[ "${3:-}" == "--make-default" ]] || [[ "${3:-}" == "1" ]] || [[ "${3:-}" == "true" ]]; then
  MAKE_DEFAULT="1"
fi

# Ask the running chromie-tts websocket server to create the speaker profile.
# This uses the patched speaker creation built into tts/server.py and avoids
# torchaudio/torchcodec/FFmpeg/NPP.
docker compose --env-file .env.runtime exec -T \
  -e WAV_PATH="$WAV_PATH" \
  -e SPEAKER_ID="$SPEAKER_ID" \
  -e MAKE_DEFAULT="$MAKE_DEFAULT" \
  chromie-tts python - <<'PY'
import asyncio
import json
import os
import websockets

async def main():
    wav_path = os.environ["WAV_PATH"]
    speaker_id = os.environ["SPEAKER_ID"]
    make_default = os.environ.get("MAKE_DEFAULT") == "1"

    payload = {
        "type": "create_speaker",
        "request_id": f"create-{speaker_id}",
        "speaker_id": speaker_id,
        "wav_path": wav_path,
        "make_default": make_default,
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
