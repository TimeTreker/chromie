import asyncio
import json
import logging
import os
import time

import numpy as np
import websockets

try:
    from .backends import ASRBackendConfig, create_final_asr_backend
    from .transcription import TranscriptionExecutor
except ImportError:
    from backends import ASRBackendConfig, create_final_asr_backend
    from transcription import TranscriptionExecutor

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(threadName)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("chromie-asr")

HOST = os.getenv("ASR_HOST", "0.0.0.0")
PORT = int(os.getenv("ASR_PORT", "9001"))
DEFAULT_SENSEVOICE_MODEL_ID = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
DEFAULT_SENSEVOICE_MODEL_REVISION = f"asr-models/{DEFAULT_SENSEVOICE_MODEL_ID}"
DEFAULT_SENSEVOICE_MODEL_PATH = (
    "/root/.cache/huggingface/sherpa-onnx/"
    f"{DEFAULT_SENSEVOICE_MODEL_ID}"
)

SHERPA_ONNX_MODEL_TYPE = os.getenv("SHERPA_ONNX_MODEL_TYPE", "sense_voice")
SHERPA_ONNX_PROVIDER = os.getenv("SHERPA_ONNX_PROVIDER") or None
SHERPA_ONNX_MODEL_FILE = os.getenv("SHERPA_ONNX_MODEL_FILE") or None
SHERPA_ONNX_TOKENS_FILE = os.getenv("SHERPA_ONNX_TOKENS_FILE") or None
ASR_MODE = os.getenv("ASR_MODE", "final")
MODEL_NAME = os.getenv("ASR_MODEL", DEFAULT_SENSEVOICE_MODEL_PATH)
MODEL_REVISION = os.getenv("ASR_MODEL_REVISION") or DEFAULT_SENSEVOICE_MODEL_REVISION
DEVICE = os.getenv("ASR_DEVICE", "cuda")
SAMPLE_RATE = int(os.getenv("ASR_SAMPLE_RATE", "16000"))
ASR_LANGUAGE = os.getenv("ASR_LANGUAGE") or None
SHERPA_ONNX_NUM_THREADS = max(1, int(os.getenv("SHERPA_ONNX_NUM_THREADS", "2")))
SHERPA_ONNX_LANGUAGE = os.getenv("SHERPA_ONNX_LANGUAGE") or ASR_LANGUAGE or "auto"
SHERPA_ONNX_USE_ITN = os.getenv("SHERPA_ONNX_USE_ITN", "true").lower() in {"1", "true", "yes", "on"}
ASR_MAX_CONCURRENT_TRANSCRIPTIONS = max(
    1,
    int(os.getenv("ASR_MAX_CONCURRENT_TRANSCRIPTIONS", "1")),
)
ASR_STARTUP_WARMUP_ENABLED = os.getenv("ASR_STARTUP_WARMUP_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
ASR_STARTUP_WARMUP_AUDIO_SECONDS = max(0.01, float(os.getenv("ASR_STARTUP_WARMUP_AUDIO_SECONDS", "1.0")))

logger.info(
    (
        "ASR config: backend=sherpa_onnx mode=%s model=%s revision=%s device=%s "
        "language=%s"
    ),
    ASR_MODE,
    MODEL_NAME,
    MODEL_REVISION or "unpinned",
    DEVICE,
    ASR_LANGUAGE or "auto",
)
asr_backend = create_final_asr_backend(
    ASRBackendConfig(
        mode=ASR_MODE,
        model_name=MODEL_NAME,
        model_revision=MODEL_REVISION,
        device=DEVICE,
        sample_rate=SAMPLE_RATE,
        sherpa_model_type=SHERPA_ONNX_MODEL_TYPE,
        sherpa_provider=SHERPA_ONNX_PROVIDER,
        sherpa_num_threads=SHERPA_ONNX_NUM_THREADS,
        sherpa_language=SHERPA_ONNX_LANGUAGE,
        sherpa_use_itn=SHERPA_ONNX_USE_ITN,
        sherpa_debug=os.getenv("SHERPA_ONNX_DEBUG", "false").lower() in {"1", "true", "yes", "on"},
        sherpa_model_file=SHERPA_ONNX_MODEL_FILE,
        sherpa_tokens_file=SHERPA_ONNX_TOKENS_FILE,
    )
)
logger.info(
    "ASR backend loaded successfully: backend=%s model=%s device=%s",
    asr_backend.name,
    asr_backend.model_name,
    DEVICE,
)
transcription_executor = TranscriptionExecutor(ASR_MAX_CONCURRENT_TRANSCRIPTIONS)


def warm_up_backend() -> None:
    if not ASR_STARTUP_WARMUP_ENABLED:
        logger.info("ASR startup warm-up disabled")
        return

    sample_count = max(1, int(SAMPLE_RATE * ASR_STARTUP_WARMUP_AUDIO_SECONDS))
    audio = np.zeros(sample_count, dtype=np.float32)
    logger.info(
        "ASR startup warm-up starting: audio=%.2fs samples=%s",
        sample_count / SAMPLE_RATE,
        sample_count,
    )
    start = time.time()
    text, _info = asr_backend.transcribe_final(audio)
    elapsed = time.time() - start
    logger.info(
        "ASR startup warm-up finished in %.2fs text_chars=%s",
        elapsed,
        len(text),
    )


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
                await ws.send(
                    json.dumps(
                        {
                            "type": "pong",
                            "service": "asr",
                            "max_concurrent_transcriptions": ASR_MAX_CONCURRENT_TRANSCRIPTIONS,
                            "backend": asr_backend.name,
                            "mode": ASR_MODE,
                            "model": asr_backend.model_name,
                            "model_revision": asr_backend.model_revision,
                        }
                    )
                )
            continue

        audio = pcm16_to_float32(message)
        duration = len(audio) / SAMPLE_RATE
        rms = float(np.sqrt(np.mean((audio * 32768.0) ** 2))) if len(audio) else 0.0

        logger.info("ASR received audio: %.2fs rms=%.1f bytes=%s", duration, rms, len(message))

        start = time.time()
        try:
            text, info = await transcription_executor.transcribe(
                asr_backend,
                audio,
            )
            elapsed = time.time() - start
            logger.info("ASR done in %.2fs text=%s", elapsed, text)
            await ws.send(json.dumps({"type": "final", "text": text, "duration": duration}))
        except Exception as exc:
            logger.error("ASR failed: %s", exc, exc_info=True)
            await ws.send(json.dumps({"type": "error", "message": str(exc)}))


async def main():
    warm_up_backend()
    logger.info("ASR server starting on ws://%s:%s", HOST, PORT)
    try:
        async with websockets.serve(handle_client, HOST, PORT, max_size=10**7, ping_interval=20, ping_timeout=20):
            logger.info("ASR server started on ws://%s:%s", HOST, PORT)
            await asyncio.Future()
    finally:
        transcription_executor.close()


if __name__ == "__main__":
    asyncio.run(main())
