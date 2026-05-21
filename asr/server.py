import asyncio
import json
import logging
import os
import time

import numpy as np
import websockets
from faster_whisper import WhisperModel

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(threadName)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("chromie-asr")

HOST = os.getenv("ASR_HOST", "0.0.0.0")
PORT = int(os.getenv("ASR_PORT", "9001"))
MODEL_NAME = os.getenv("ASR_MODEL", "dropbox-dash/faster-whisper-large-v3-turbo")
DEVICE = os.getenv("ASR_DEVICE", "cuda")
COMPUTE_TYPE = os.getenv("ASR_COMPUTE_TYPE", "float16")
SAMPLE_RATE = int(os.getenv("ASR_SAMPLE_RATE", "16000"))
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE") or None
ASR_BEAM_SIZE = int(os.getenv("ASR_BEAM_SIZE", "1"))
ASR_VAD_FILTER = os.getenv("ASR_VAD_FILTER", "false").lower() in {"1", "true", "yes", "on"}
ASR_CONDITION_ON_PREVIOUS_TEXT = os.getenv("ASR_CONDITION_ON_PREVIOUS_TEXT", "false").lower() in {"1", "true", "yes", "on"}

logger.info(
    "ASR config: model=%s device=%s compute_type=%s language=%s beam_size=%s vad_filter=%s",
    MODEL_NAME,
    DEVICE,
    COMPUTE_TYPE,
    ASR_LANGUAGE or "auto",
    ASR_BEAM_SIZE,
    ASR_VAD_FILTER,
)
model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
logger.info("Model loaded successfully on %s", DEVICE)


def pcm16_to_float32(audio_bytes: bytes) -> np.ndarray:
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


async def handle_client(ws):
    async for message in ws:
        if isinstance(message, str):
            try:
                data = json.loads(message)
            except Exception:
                data = {}

            if data.get("type") in {"health", "ping"}:
                await ws.send(json.dumps({"type": "pong", "service": "asr"}))
            continue

        audio = pcm16_to_float32(message)
        duration = len(audio) / SAMPLE_RATE
        rms = float(np.sqrt(np.mean((audio * 32768.0) ** 2))) if len(audio) else 0.0

        logger.info("ASR received audio: %.2fs rms=%.1f bytes=%s", duration, rms, len(message))

        start = time.time()
        try:
            segments, info = model.transcribe(
                audio,
                language=ASR_LANGUAGE,
                beam_size=ASR_BEAM_SIZE,
                vad_filter=ASR_VAD_FILTER,
                condition_on_previous_text=ASR_CONDITION_ON_PREVIOUS_TEXT,
                temperature=0.0,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            elapsed = time.time() - start
            logger.info("ASR done in %.2fs text=%s", elapsed, text)
            await ws.send(json.dumps({"type": "final", "text": text, "duration": duration}))
        except Exception as exc:
            logger.error("ASR failed: %s", exc, exc_info=True)
            await ws.send(json.dumps({"type": "error", "message": str(exc)}))


async def main():
    logger.info("ASR server starting on ws://%s:%s", HOST, PORT)
    async with websockets.serve(handle_client, HOST, PORT, max_size=10**7, ping_interval=20, ping_timeout=20):
        logger.info("ASR server started on ws://%s:%s", HOST, PORT)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
