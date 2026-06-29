from __future__ import annotations

import asyncio
import threading
import tempfile
import unittest
from pathlib import Path

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
        model_name: str = "example/faster-whisper-model",
        model_revision: str | None = "abc123",
        device: str = "cpu",
        **overrides,
    ) -> ASRBackendConfig:
        values = dict(
            backend=backend,
            mode=mode,
            model_name=model_name,
            model_revision=model_revision,
            device=device,
            compute_type="int8",
        )
        values.update(overrides)
        return ASRBackendConfig(**values)

    def test_backend_name_accepts_existing_faster_whisper_spellings(self) -> None:
        self.assertEqual(canonical_backend_name("faster-whisper"), "faster_whisper")
        self.assertEqual(canonical_backend_name(" faster_whisper "), "faster_whisper")
        self.assertEqual(canonical_backend_name(""), "sherpa_onnx")
        self.assertEqual(canonical_backend_name("sherpa-onnx"), "sherpa_onnx")

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

    def test_sherpa_backend_uses_injected_recognizer_factory(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeResult:
            text = (
                '{"lang": "<|en|>", "text": '
                '"<|en|> hello<|SPECIAL_TOKEN_30|> sherpa <|END|> . ", '
                '"timestamps": [0.1]}'
            )

        class FakeStream:
            result = None

            def accept_waveform(self, sample_rate, audio):
                calls.append({"sample_rate": sample_rate, "audio": audio})

        class FakeRecognizer:
            def create_stream(self):
                return FakeStream()

            def decode_stream(self, stream):
                stream.result = FakeResult()

        class FakeRecognizerFactory:
            @staticmethod
            def from_sense_voice(**kwargs):
                calls.append({"kwargs": kwargs})
                return FakeRecognizer()

        with tempfile.TemporaryDirectory() as temp:
            model_dir = Path(temp)
            (model_dir / "model.int8.onnx").write_text("model", encoding="utf-8")
            (model_dir / "tokens.txt").write_text("tokens", encoding="utf-8")

            backend = create_final_asr_backend(
                self._config(
                    backend="sherpa-onnx",
                    model_name=str(model_dir),
                    model_revision="sense-voice-revision",
                    device="cuda",
                    sample_rate=16000,
                    sherpa_num_threads=2,
                    sherpa_language="auto",
                    sherpa_use_itn=True,
                ),
                sherpa_onnx_factory=FakeRecognizerFactory,
            )

            text, info = backend.transcribe_final([0.0])

        self.assertEqual(text, "hello sherpa.")
        self.assertEqual(info["backend"], "sherpa_onnx")
        self.assertEqual(info["provider"], "cuda")
        self.assertEqual(calls[0]["kwargs"]["model"], str(model_dir / "model.int8.onnx"))
        self.assertEqual(calls[0]["kwargs"]["tokens"], str(model_dir / "tokens.txt"))
        self.assertEqual(calls[0]["kwargs"]["provider"], "cuda")
        self.assertEqual(calls[0]["kwargs"]["language"], "auto")
        self.assertEqual(calls[0]["kwargs"]["use_itn"], True)
        self.assertEqual(calls[1], {"sample_rate": 16000, "audio": [0.0]})

    def test_sherpa_backend_fails_closed_when_model_files_are_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires local SenseVoice model files"):
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
