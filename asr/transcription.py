from __future__ import annotations

import asyncio
import concurrent.futures
import functools
from typing import Any


def _transcribe_sync(model: Any, audio: Any, kwargs: dict[str, Any]) -> tuple[str, Any]:
    """Run the complete faster-whisper call, including generator consumption."""
    segments, info = model.transcribe(audio, **kwargs)
    text = " ".join(segment.text.strip() for segment in segments).strip()
    return text, info


class TranscriptionExecutor:
    """Bounded executor that keeps blocking ASR inference off the event loop."""

    def __init__(
        self,
        max_concurrency: int = 1,
        *,
        executor: concurrent.futures.Executor | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._owns_executor = executor is None
        self._executor = executor or concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="chromie-asr-transcribe",
        )

    async def transcribe(self, model: Any, audio: Any, **kwargs: Any) -> tuple[str, Any]:
        async with self._semaphore:
            loop = asyncio.get_running_loop()
            call = functools.partial(_transcribe_sync, model, audio, kwargs)
            return await loop.run_in_executor(self._executor, call)

    def close(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
