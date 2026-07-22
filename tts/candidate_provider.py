"""Shared provider adapter for isolated candidate-model processes."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from provider import (
    TTSAudioChunk,
    TTSSynthesisCompleted,
    TTSSynthesisRequest,
    TTSProvider,
    TTSProviderCapabilities,
    TTSStreamEvent,
)
from streaming_worker import StreamingProcessWorker


class WorkerBackedCandidateProvider(TTSProvider):
    def __init__(
        self,
        *,
        capabilities: TTSProviderCapabilities,
        worker: StreamingProcessWorker,
        speakers: list[str] | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._worker = worker
        self._speakers = speakers or ["default"]

    @property
    def capabilities(self) -> TTSProviderCapabilities:
        return self._capabilities

    async def start(self) -> None:
        await self._worker.start()

    async def stop(self) -> None:
        await self._worker.stop()

    async def health(self) -> dict[str, Any]:
        return {
            "ready": self._worker.is_alive,
            "worker_process_alive": self._worker.is_alive,
            "worker_restart_count": self._worker.restart_count,
            "cancellation_mode": "terminate_and_restart_worker",
            "worker": dict(self._worker.ready_payload),
        }

    async def list_speakers(self) -> list[str]:
        return list(self._speakers)

    async def synthesize_stream(
        self,
        request: TTSSynthesisRequest,
    ) -> AsyncIterator[TTSStreamEvent]:
        started = time.perf_counter()
        audio_bytes = 0
        sample_rate: int | None = None
        async for event in self._worker.stream(
            {
                "type": "synthesize",
                "request_id": request.request_id,
                "text": request.text,
                "speaker_id": request.speaker_id,
                "language_hint": request.language_hint,
                "metadata": dict(request.metadata),
            }
        ):
            event_type = event.get("type")
            if event_type == "audio":
                pcm = event.get("pcm")
                if not isinstance(pcm, bytes) or not pcm:
                    raise RuntimeError("candidate worker emitted an empty audio event")
                event_rate = int(event.get("sample_rate") or 0)
                if event_rate not in self._capabilities.sample_rates:
                    raise RuntimeError(
                        "candidate worker emitted an undeclared sample rate: "
                        f"{event_rate}"
                    )
                if sample_rate is not None and event_rate != sample_rate:
                    raise RuntimeError("candidate worker changed sample rate mid-stream")
                sample_rate = event_rate
                audio_bytes += len(pcm)
                yield TTSAudioChunk(pcm=pcm, sample_rate=event_rate)
            elif event_type == "error":
                raise RuntimeError(str(event.get("message") or "candidate synthesis failed"))
            elif event_type == "complete":
                if audio_bytes <= 0 or sample_rate is None:
                    raise RuntimeError("candidate worker completed without audio")
                metrics = event.get("metrics")
                if not isinstance(metrics, dict):
                    metrics = {}
                total_seconds = time.perf_counter() - started
                audio_seconds = audio_bytes / (sample_rate * 2)
                metrics = {
                    **metrics,
                    "audio_seconds": audio_seconds,
                    "total_seconds": total_seconds,
                    "realtime_factor": (
                        total_seconds / audio_seconds if audio_seconds > 0 else None
                    ),
                }
                metadata = event.get("provider_metadata")
                yield TTSSynthesisCompleted(
                    metrics=metrics,
                    provider_metadata=metadata if isinstance(metadata, dict) else {},
                )
                return
            else:
                raise RuntimeError(f"unsupported candidate worker event: {event_type!r}")
