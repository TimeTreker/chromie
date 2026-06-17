from __future__ import annotations

import asyncio
import threading
import unittest

from asr.transcription import TranscriptionExecutor


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class _BlockingModel:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def transcribe(self, audio, **kwargs):
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        self.started.set()
        self.release.wait(timeout=2.0)

        def segments():
            try:
                yield _Segment(" hello ")
                yield _Segment("world")
            finally:
                with self._lock:
                    self.active -= 1

        return segments(), {"language": "en"}


class TranscriptionExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def _wait_for_event(
        self,
        event: threading.Event,
        *,
        timeout_s: float,
    ) -> bool:
        deadline = asyncio.get_running_loop().time() + timeout_s
        while not event.is_set():
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(0.01)
        return True

    async def test_inference_does_not_block_event_loop_and_is_bounded(self) -> None:
        model = _BlockingModel()
        executor = TranscriptionExecutor(max_concurrency=1)
        try:
            first = asyncio.create_task(executor.transcribe(model, [0.0]))
            started = await self._wait_for_event(model.started, timeout_s=1.0)
            self.assertTrue(started)

            # This timer still runs while the fake synchronous model is blocked.
            await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)

            second = asyncio.create_task(executor.transcribe(model, [0.0]))
            await asyncio.sleep(0.05)
            self.assertEqual(model.peak, 1)

            model.release.set()
            first_result, second_result = await asyncio.gather(first, second)
            self.assertEqual(first_result[0], "hello world")
            self.assertEqual(second_result[0], "hello world")
            self.assertEqual(model.peak, 1)
        finally:
            executor.close()


if __name__ == "__main__":
    unittest.main()
