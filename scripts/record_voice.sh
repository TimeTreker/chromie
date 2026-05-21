#!/usr/bin/env bash
set -euo pipefail
mkdir -p tts/speakers
OUT=${1:-tts/speakers/chromie_voice.wav}
DURATION=${2:-14}
DEVICE=${3:-default}
arecord -D "$DEVICE" -f S16_LE -r 48000 -c 1 -d "$DURATION" "$OUT"
echo "Saved: $OUT"
