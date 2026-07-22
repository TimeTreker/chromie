"""OuteTTS adapter for the framework-neutral :mod:`provider` contract."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from performance import (
    TtsPerformanceSample,
    nonnegative_remainder,
    summarize_samples,
)
from provider import (
    TTSAudioChunk,
    TTSSynthesisCompleted,
    TTSSynthesisRequest,
    TTSModelArtifact,
    TTSProvider,
    TTSProviderCapabilities,
    TTSStreamEvent,
)


@dataclass(frozen=True)
class OuteTTSProviderConfig:
    tokenizer_id: str
    tokenizer_revision: str
    gguf_id: str
    gguf_revision: str
    sample_rate: int
    chunk_ms: int
    max_concurrency: int
    generation_retries: int
    max_length: int
    context_size: int
    quantization: str
    audio_codec_device: str
    metrics_window: int
    speaker_dir: Path


class OuteTTSProvider(TTSProvider):
    """Adapt restartable OuteTTS workers to the common provider contract."""

    def __init__(
        self,
        *,
        config: OuteTTSProviderConfig,
        workers: Sequence[Any],
        select_worker: Callable[[], Awaitable[tuple[int, Any]]],
        worker_status: Callable[[], list[dict[str, object]]],
        list_speaker_ids: Callable[[], list[str]],
        validate_speaker_path: Callable[[Path], Path],
    ) -> None:
        self._config = config
        self._workers = tuple(workers)
        self._select_worker = select_worker
        self._worker_status = worker_status
        self._list_speaker_ids = list_speaker_ids
        self._validate_speaker_path = validate_speaker_path
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._recent_samples: deque[TtsPerformanceSample] = deque(
            maxlen=config.metrics_window
        )
        self._capabilities = TTSProviderCapabilities(
            provider_id="oute",
            implementation="OuteTTS/llama.cpp",
            software_license_id="Apache-2.0",
            model_artifacts=(
                TTSModelArtifact(
                    kind="tokenizer_config",
                    artifact_id=config.tokenizer_id,
                    revision=config.tokenizer_revision,
                    license_id="Apache-2.0",
                ),
                TTSModelArtifact(
                    kind="gguf_weights",
                    artifact_id=config.gguf_id,
                    revision=config.gguf_revision,
                    license_id="Apache-2.0",
                ),
            ),
            license_review_status="declared_unreviewed",
            languages=("zh", "en"),
            sample_rates=(config.sample_rate,),
            max_concurrency=config.max_concurrency,
            native_text_streaming=False,
            native_audio_streaming=False,
            request_cancellation=True,
            speaker_profiles=True,
            voice_cloning=True,
        )

    @property
    def capabilities(self) -> TTSProviderCapabilities:
        return self._capabilities

    async def start(self) -> None:
        await asyncio.gather(*(worker.start() for worker in self._workers))

    async def stop(self) -> None:
        await asyncio.gather(
            *(worker.stop() for worker in self._workers),
            return_exceptions=True,
        )

    async def health(self) -> dict[str, Any]:
        workers = self._worker_status()
        return {
            "worker_count": len(self._workers),
            "max_concurrent_synthesis": self._config.max_concurrency,
            "worker_process_alive": all(bool(item.get("alive")) for item in workers),
            "worker_restart_count": sum(
                int(item.get("restart_count") or 0) for item in workers
            ),
            "workers": workers,
            "cancellation_mode": "terminate_and_restart_worker",
            "recent_performance": summarize_samples(self._recent_samples),
        }

    async def list_speakers(self) -> list[str]:
        return self._list_speaker_ids()

    async def create_speaker(
        self,
        *,
        speaker_id: str,
        wav_path: str,
        make_default: bool,
    ) -> dict[str, Any]:
        resolved = self._validate_speaker_path(Path(wav_path))
        response = await self._workers[0].request(
            {
                "type": "create_speaker",
                "speaker_id": speaker_id,
                "wav_path": str(resolved),
                "make_default": make_default,
            }
        )
        if response.get("type") == "error":
            raise RuntimeError(str(response.get("message") or "speaker creation failed"))
        if response.get("type") != "speaker_created":
            raise RuntimeError(
                f"Unexpected generation-worker response: {response.get('type')!r}"
            )
        return dict(response)

    async def _generate(self, request: TTSSynthesisRequest) -> tuple[bytes, dict[str, Any]]:
        request_received = time.perf_counter()
        async with self._semaphore:
            queue_wait_seconds = time.perf_counter() - request_received
            total_started = time.perf_counter()
            last_error: Exception | None = None

            for attempt in range(1, self._config.generation_retries + 1):
                try:
                    worker_index, worker = await self._select_worker()
                    worker_started = time.perf_counter()
                    response = await worker.request(
                        {
                            "type": "generate",
                            "text": request.text,
                            "speaker_id": request.speaker_id,
                        }
                    )
                    worker_roundtrip_seconds = time.perf_counter() - worker_started
                    if response.get("type") == "error":
                        raise RuntimeError(
                            str(response.get("message") or "generation failed")
                        )
                    if response.get("type") != "generated":
                        raise RuntimeError(
                            "Unexpected generation-worker response: "
                            f"{response.get('type')!r}"
                        )

                    pcm = response.get("pcm") or b""
                    timings = response.get("timings")
                    if not isinstance(timings, dict):
                        timings = {}
                    generate_seconds = float(timings.get("generate_seconds") or 0.0)
                    model_generate_seconds = float(
                        timings.get("model_generate_seconds") or 0.0
                    )
                    codec_decode_seconds = float(
                        timings.get("codec_decode_seconds") or 0.0
                    )
                    pcm_conversion_seconds = float(
                        timings.get("pcm_conversion_seconds") or 0.0
                    )
                    pipeline_overhead_seconds = float(
                        timings.get("pipeline_overhead_seconds") or 0.0
                    )
                    model_prompt_tokens = int(timings.get("model_prompt_tokens") or 0)
                    model_generated_tokens = int(
                        timings.get("model_generated_tokens") or 0
                    )
                    generation_max_length = int(
                        timings.get("generation_max_length") or 0
                    )
                    generation_headroom_tokens = int(
                        timings.get("generation_headroom_tokens") or 0
                    )
                    generation_limit_reached = bool(
                        timings.get("generation_limit_reached", False)
                    )
                    if generation_limit_reached:
                        raise RuntimeError(
                            "OuteTTS reached its generation max_length before the audio "
                            "end token; refusing to play a truncated sentence. "
                            f"prompt_tokens={model_prompt_tokens}, "
                            f"generated_tokens={model_generated_tokens}, "
                            f"max_length={generation_max_length}, "
                            f"text_chars={len(request.text)}. Increase "
                            "TTS_CONTEXT_SIZE/TTS_MAX_LENGTH or shorten the host TTS chunk."
                        )
                    if not pcm:
                        raise RuntimeError(
                            "OuteTTS generated empty audio. "
                            f"effective_max_length={self._config.max_length}, "
                            f"text_chars={len(request.text)}. Do not set TTS_MAX_LENGTH "
                            "too low; use TTS_MAX_TEXT_CHARS to shorten spoken text."
                        )

                    audio_seconds = len(pcm) / (self._config.sample_rate * 2)
                    total_seconds = time.perf_counter() - total_started
                    sample = TtsPerformanceSample(
                        audio_seconds=audio_seconds,
                        generate_seconds=generate_seconds,
                        model_generate_seconds=model_generate_seconds,
                        codec_decode_seconds=codec_decode_seconds,
                        pcm_conversion_seconds=pcm_conversion_seconds,
                        worker_roundtrip_seconds=worker_roundtrip_seconds,
                        queue_wait_seconds=queue_wait_seconds,
                        total_seconds=total_seconds,
                    )
                    self._recent_samples.append(sample)
                    metrics = {
                        **sample.as_dict(),
                        "pipeline_overhead_seconds": pipeline_overhead_seconds,
                        "ipc_overhead_seconds": nonnegative_remainder(
                            worker_roundtrip_seconds,
                            generate_seconds,
                            pcm_conversion_seconds,
                        ),
                        "audio_codec_device": self._config.audio_codec_device,
                        "quantization": self._config.quantization,
                        "context_size": self._config.context_size,
                        "max_length": self._config.max_length,
                        "model_prompt_tokens": model_prompt_tokens,
                        "model_generated_tokens": model_generated_tokens,
                        "generation_max_length": generation_max_length,
                        "generation_headroom_tokens": generation_headroom_tokens,
                        "generation_limit_reached": generation_limit_reached,
                        "worker_index": worker_index,
                        "attempt": attempt,
                    }
                    return bytes(pcm), metrics
                except Exception as exc:
                    last_error = exc
                    if attempt < self._config.generation_retries:
                        await asyncio.sleep(0.05)

            raise RuntimeError(
                f"TTS generated no audio after retries: {last_error}"
            ) from last_error

    async def synthesize_stream(
        self,
        request: TTSSynthesisRequest,
    ) -> AsyncIterator[TTSStreamEvent]:
        pcm, metrics = await self._generate(request)
        chunk_bytes = int(
            self._config.sample_rate * self._config.chunk_ms / 1000
        ) * 2
        for offset in range(0, len(pcm), chunk_bytes):
            yield TTSAudioChunk(
                pcm=pcm[offset : offset + chunk_bytes],
                sample_rate=self._config.sample_rate,
            )
            await asyncio.sleep(0)
        yield TTSSynthesisCompleted(
            metrics=metrics,
            provider_metadata={"native_audio_streaming": False},
        )
