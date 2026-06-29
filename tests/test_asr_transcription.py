from __future__ import annotations

import asyncio
import threading
import unittest

from asr.backends import ASRBackendConfig, canonical_backend_name, create_final_asr_backend
from asr.transcription import TranscriptionExecutor


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class _BlockingBackend:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def transcribe_final(self, audio, **kwargs):
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        self.started.set()
        self.release.wait(timeout=2.0)

        with self._lock:
            self.active -= 1
        return "hello world", {"language": "en"}


class ASRBackendTests(unittest.TestCase):
    def _config(
        self,
        *,
        backend: str = "faster_whisper",
        mode: str = "final",
    ) -> ASRBackendConfig:
        return ASRBackendConfig(
            backend=backend,
            mode=mode,
            model_name="example/faster-whisper-model",
            model_revision="abc123",
            device="cpu",
            compute_type="int8",
        )

    def test_backend_name_accepts_existing_faster_whisper_spellings(self) -> None:
        self.assertEqual(canonical_backend_name("faster-whisper"), "faster_whisper")
        self.assertEqual(canonical_backend_name(" faster_whisper "), "faster_whisper")
        self.assertEqual(canonical_backend_name(""), "faster_whisper")

    def test_faster_whisper_backend_uses_injected_model_factory(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeModel:
            def transcribe(self, audio, **kwargs):
                calls.append({"audio": audio, "kwargs": kwargs})
                return [_Segment(" hello "), _Segment("world")], {"language": "en"}

        def factory(*args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            return FakeModel()

        backend = create_final_asr_backend(
            self._config(),
            faster_whisper_factory=factory,
        )

        text, info = backend.transcribe_final([0.0], language="en", beam_size=1)

        self.assertEqual(text, "hello world")
        self.assertEqual(info, {"language": "en"})
        self.assertEqual(
            calls[0],
            {
                "args": ("example/faster-whisper-model",),
                "kwargs": {
                    "device": "cpu",
                    "compute_type": "int8",
                    "revision": "abc123",
                },
            },
        )
        self.assertEqual(calls[1]["kwargs"], {"language": "en", "beam_size": 1})

    def test_planned_sherpa_backend_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "planned but not implemented"):
            create_final_asr_backend(self._config(backend="sherpa-onnx"))

    def test_streaming_mode_fails_closed_until_protocol_is_added(self) -> None:
        with self.assertRaisesRegex(ValueError, "ASR_MODE='streaming'"):
            create_final_asr_backend(self._config(mode="streaming"))


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
        backend = _BlockingBackend()
        executor = TranscriptionExecutor(max_concurrency=1)
        try:
            first = asyncio.create_task(executor.transcribe(backend, [0.0]))
            started = await self._wait_for_event(backend.started, timeout_s=1.0)
            self.assertTrue(started)

            # This timer still runs while the fake synchronous model is blocked.
            await asyncio.wait_for(asyncio.sleep(0), timeout=0.1)

            second = asyncio.create_task(executor.transcribe(backend, [0.0]))
            await asyncio.sleep(0.05)
            self.assertEqual(backend.peak, 1)

            backend.release.set()
            first_result, second_result = await asyncio.gather(first, second)
            self.assertEqual(first_result[0], "hello world")
            self.assertEqual(second_result[0], "hello world")
            self.assertEqual(backend.peak, 1)
        finally:
            executor.close()


if __name__ == "__main__":
    unittest.main()
