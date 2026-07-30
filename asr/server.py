import asyncio
import json
import logging
import time

import numpy as np
import websockets

try:
    from .backends import create_final_asr_backend
    from .transcription import TranscriptionExecutor
    from .settings import ASRServiceSettings
except ImportError:
    from backends import create_final_asr_backend
    from transcription import TranscriptionExecutor
    from settings import ASRServiceSettings

settings = ASRServiceSettings.from_env()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(threadName)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("chromie-asr")


logger.info(
    (
        "ASR config: backend=sherpa_onnx mode=%s model=%s revision=%s device=%s "
        "language=%s"
    ),
    settings.mode,
    settings.model_name,
    settings.model_revision or "unpinned",
    settings.device,
    settings.language or "auto",
)
asr_backend = create_final_asr_backend(settings.backend_config())
logger.info(
    "ASR backend loaded successfully: backend=%s model=%s device=%s",
    asr_backend.name,
    asr_backend.model_name,
    settings.device,
)
transcription_executor = TranscriptionExecutor(settings.max_concurrent_transcriptions)


def warm_up_backend() -> None:
    if not settings.startup_warmup_enabled:
        logger.info("ASR startup warm-up disabled")
        return

    sample_count = max(
        1,
        int(settings.sample_rate * settings.startup_warmup_audio_seconds),
    )
    audio = np.zeros(sample_count, dtype=np.float32)
    logger.info(
        "ASR startup warm-up starting: audio=%.2fs samples=%s",
        sample_count / settings.sample_rate,
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
            except json.JSONDecodeError as exc:
                logger.debug("Ignoring malformed ASR control message: %s", exc)
                data = {}

            if data.get("type") in {"health", "ping"}:
                await ws.send(
                    json.dumps(
                        {
                            "type": "pong",
                            "service": "asr",
                            "max_concurrent_transcriptions": settings.max_concurrent_transcriptions,
                            "backend": asr_backend.name,
                            "mode": settings.mode,
                            "model": asr_backend.model_name,
                            "model_revision": asr_backend.model_revision,
                            "settings": settings.safe_diagnostics(),
                        }
                    )
                )
            continue

        audio = pcm16_to_float32(message)
        duration = len(audio) / settings.sample_rate
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
    logger.info("ASR server starting on ws://%s:%s", settings.host, settings.port)
    try:
        async with websockets.serve(
            handle_client,
            settings.host,
            settings.port,
            max_size=10**7,
            ping_interval=20,
            ping_timeout=20,
        ):
            logger.info("ASR server started on ws://%s:%s", settings.host, settings.port)
            await asyncio.Future()
    finally:
        transcription_executor.close()


if __name__ == "__main__":
    asyncio.run(main())
