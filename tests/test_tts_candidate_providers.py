from __future__ import annotations

import asyncio
import importlib.util
import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from collections.abc import AsyncIterator
from multiprocessing.connection import Connection
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))
sys.path.insert(0, str(ROOT / "scripts"))

from candidate_provider import WorkerBackedCandidateProvider  # noqa: E402
from prepare_tts_reference import build_metadata  # noqa: E402
from provider import (  # noqa: E402
    TTSAudioChunk,
    TTSSynthesisCompleted,
    TTSSynthesisRequest,
    TTSModelArtifact,
    TTSProviderCapabilities,
)
from streaming_worker import StreamingProcessWorker  # noqa: E402


def stream_fixture_target(connection: Connection) -> None:
    connection.send({"type": "ready", "fixture": True})
    while True:
        payload = connection.recv()
        if payload.get("type") == "shutdown":
            connection.send({"type": "stopped"})
            return
        if payload.get("text") == "block":
            while True:
                time.sleep(1)
        if payload.get("text") == "slow-complete":
            time.sleep(0.08)
        if payload.get("text") == "audio-then-complete":
            connection.send(
                {"type": "audio", "pcm": b"\x01\x00" * 80, "sample_rate": 8000}
            )
            time.sleep(0.08)
            connection.send(
                {"type": "complete", "metrics": {"generate_seconds": 0.1}}
            )
            continue
        connection.send({"type": "audio", "pcm": b"\x01\x00" * 80, "sample_rate": 8000})
        connection.send({"type": "complete", "metrics": {"generate_seconds": 0.1}})


class FakeStreamingWorker:
    is_alive = True
    restart_count = 0
    cancel_drain_count = 0
    cancel_restart_count = 0
    cancellation_mode = "bounded_drain_then_restart_worker"
    ready_payload = {"fixture": True}

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def stream(self, _payload: dict[str, object]) -> AsyncIterator[dict[str, object]]:
        yield {"type": "audio", "pcm": b"\x01\x00" * 80, "sample_rate": 8000}
        yield {"type": "complete", "metrics": {"generate_seconds": 0.1}}


def fixture_capabilities() -> TTSProviderCapabilities:
    return TTSProviderCapabilities(
        provider_id="candidate-fixture",
        implementation="fixture",
        software_source="https://example.invalid/fixture",
        software_revision="0123456789abcdef",
        software_license_id="Apache-2.0",
        model_artifacts=(
            TTSModelArtifact(
                kind="weights",
                artifact_id="fixture/model",
                revision="fedcba9876543210",
                license_id="Apache-2.0",
            ),
        ),
        license_review_status="declared_unreviewed",
        languages=("zh", "en"),
        sample_rates=(8000,),
        max_concurrency=1,
        native_text_streaming=False,
        native_audio_streaming=True,
        request_cancellation=True,
        speaker_profiles=True,
        voice_cloning=True,
    )


def load_provider_impl(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TtsCandidateProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_backed_provider_maps_audio_and_comparable_metrics(self) -> None:
        provider = WorkerBackedCandidateProvider(
            capabilities=fixture_capabilities(),
            worker=FakeStreamingWorker(),  # type: ignore[arg-type]
        )
        events = [
            event
            async for event in provider.synthesize_stream(
                TTSSynthesisRequest(request_id="fixture-1", text="你好")
            )
        ]
        self.assertIsInstance(events[0], TTSAudioChunk)
        self.assertIsInstance(events[1], TTSSynthesisCompleted)
        completed = events[1]
        assert isinstance(completed, TTSSynthesisCompleted)
        self.assertEqual(completed.metrics["audio_seconds"], 0.01)
        self.assertGreater(float(completed.metrics["total_seconds"]), 0.0)

        health = await provider.health()
        self.assertEqual(
            health["cancellation_mode"],
            "bounded_drain_then_restart_worker",
        )
        self.assertEqual(health["worker_cancel_drain_count"], 0)
        self.assertEqual(health["worker_cancel_restart_count"], 0)

    async def test_streaming_worker_restarts_after_native_cancellation(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-worker",
            startup_timeout_s=5.0,
        )
        await worker.start()

        async def consume_blocking() -> None:
            async for _event in worker.stream({"type": "synthesize", "text": "block"}):
                pass

        task = asyncio.create_task(consume_blocking())
        await asyncio.sleep(0.05)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(worker.restart_count, 1)
        events = [
            event
            async for event in worker.stream({"type": "synthesize", "text": "recover"})
        ]
        self.assertEqual([event["type"] for event in events], ["audio", "complete"])
        await worker.stop()

    async def test_streaming_worker_drains_nearly_complete_cancel_without_reload(
        self,
    ) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-drain-worker",
            startup_timeout_s=5.0,
            cancel_drain_timeout_s=0.5,
        )
        await worker.start()

        async def consume_slow() -> None:
            async for _event in worker.stream(
                {"type": "synthesize", "text": "slow-complete"}
            ):
                pass

        try:
            task = asyncio.create_task(consume_slow())
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            self.assertTrue(worker.is_alive)
            self.assertEqual(worker.restart_count, 0)
            self.assertEqual(worker.cancel_restart_count, 0)
            self.assertEqual(worker.cancel_drain_count, 1)
            self.assertEqual(
                worker.cancellation_mode,
                "bounded_drain_then_restart_worker",
            )
            events = [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "recover"}
                )
            ]
            self.assertEqual(
                [event["type"] for event in events],
                ["audio", "complete"],
            )
        finally:
            await worker.stop()

    async def test_streaming_worker_drain_timeout_restarts_fail_closed(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-drain-timeout-worker",
            startup_timeout_s=5.0,
            cancel_drain_timeout_s=0.05,
        )
        await worker.start()

        async def consume_blocking() -> None:
            async for _event in worker.stream(
                {"type": "synthesize", "text": "block"}
            ):
                pass

        try:
            task = asyncio.create_task(consume_blocking())
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

            self.assertTrue(worker.is_alive)
            self.assertEqual(worker.cancel_drain_count, 0)
            self.assertEqual(worker.restart_count, 1)
            self.assertEqual(worker.cancel_restart_count, 1)
            events = [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "recover"}
                )
            ]
            self.assertEqual(
                [event["type"] for event in events],
                ["audio", "complete"],
            )
        finally:
            await worker.stop()

    async def test_streaming_worker_generator_close_drains_terminal_event(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-generator-close-worker",
            startup_timeout_s=5.0,
            cancel_drain_timeout_s=0.5,
        )
        await worker.start()
        stream = worker.stream(
            {"type": "synthesize", "text": "audio-then-complete"}
        )
        try:
            first = await stream.__anext__()
            self.assertEqual(first["type"], "audio")
            await stream.aclose()

            self.assertTrue(worker.is_alive)
            self.assertEqual(worker.cancel_drain_count, 1)
            self.assertEqual(worker.restart_count, 0)
            events = [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "recover"}
                )
            ]
            self.assertEqual(
                [event["type"] for event in events],
                ["audio", "complete"],
            )
        finally:
            await worker.stop()

    def test_candidate_locks_match_provider_constants_and_compose_profile(self) -> None:
        lock = json.loads(
            (ROOT / "tts_candidates" / "model-lock.json").read_text(encoding="utf-8")
        )
        cosy = load_provider_impl(
            "tts_candidates/cosyvoice/provider_impl.py", "cosy_provider_fixture"
        )
        qwen = load_provider_impl(
            "tts_candidates/qwen3/provider_impl.py", "qwen_provider_fixture"
        )
        self.assertEqual(
            lock["candidates"][cosy.PROVIDER_ID]["model"]["revision"],
            cosy.DEFAULT_MODEL_REVISION,
        )
        self.assertEqual(
            lock["candidates"][qwen.PROVIDER_ID]["runtime"]["revision"],
            qwen.DEFAULT_SOFTWARE_REVISION,
        )
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('profiles: ["tts-evaluation"]', compose)
        self.assertIn('"5001:5000"', compose)
        self.assertIn('"5002:5000"', compose)
        self.assertIn("TTS_AB_REFERENCE_DIR", compose)
        self.assertIn("./hf_cache/modelscope:/root/.cache/modelscope", compose)
        self.assertIn("TTS_CANDIDATE_CANCEL_DRAIN_TIMEOUT_SEC", compose)
        self.assertIn("Qwen/Qwen3-TTS-12Hz-0.6B-Base", compose)
        cosy_dockerfile = (ROOT / "tts_candidates" / "cosyvoice" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("onnxruntime-gpu==1.18.1", cosy_dockerfile)
        self.assertNotIn("onnxruntime-gpu==1.18.0", cosy_dockerfile)

    def test_candidate_reference_metadata_preserves_authorized_license(self) -> None:
        for relative, name in (
            ("tts_candidates/cosyvoice/provider_impl.py", "cosy_reference_fixture"),
            ("tts_candidates/qwen3/provider_impl.py", "qwen_reference_fixture"),
        ):
            with self.subTest(provider=name), tempfile.TemporaryDirectory() as temp_dir:
                wav_path = Path(temp_dir) / "reference.wav"
                metadata_path = Path(temp_dir) / "reference.json"
                wav_path.write_bytes(b"RIFF" + b"\x00" * 128)
                audio_sha = hashlib.sha256(wav_path.read_bytes()).hexdigest()
                metadata_path.write_text(
                    json.dumps(
                        {
                            "text": "你好，Hello.",
                            "audio_sha256": audio_sha,
                            "license_id": "User-authorized-AI-generated-voice-reference",
                        }
                    ),
                    encoding="utf-8",
                )
                module = load_provider_impl(relative, name)
                with patch.dict(
                    os.environ,
                    {
                        "TTS_REFERENCE_WAV": str(wav_path),
                        "TTS_REFERENCE_METADATA": str(metadata_path),
                    },
                ):
                    _wav, text, observed_sha, license_id = module.reference_metadata()
                self.assertEqual(text, "你好，Hello.")
                self.assertEqual(observed_sha, audio_sha)
                self.assertEqual(
                    license_id, "User-authorized-AI-generated-voice-reference"
                )

                metadata_path.write_text(
                    json.dumps({"text": "你好，Hello.", "audio_sha256": audio_sha}),
                    encoding="utf-8",
                )
                with patch.dict(
                    os.environ,
                    {
                        "TTS_REFERENCE_WAV": str(wav_path),
                        "TTS_REFERENCE_METADATA": str(metadata_path),
                    },
                ), self.assertRaisesRegex(RuntimeError, "metadata or SHA-256"):
                    module.reference_metadata()

    def test_reference_metadata_binds_whole_wav_and_source_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            wav_path = Path(temp_dir) / "reference.wav"
            wav_path.write_bytes(b"RIFF" + b"\x00" * 128)
            metadata = build_metadata(
                text="你好，Chromie。",
                wav_path=wav_path,
                health={"provider": fixture_capabilities().as_dict()},
                result={
                    "audio_bytes": 128,
                    "audio_sha256": "0" * 64,
                    "observed_audio_seconds": 1.0,
                },
            )
        self.assertEqual(len(metadata["audio_sha256"]), 64)
        self.assertEqual(metadata["source_provider"]["provider_id"], "candidate-fixture")
        self.assertFalse(metadata["production_voice_approved"])


if __name__ == "__main__":
    unittest.main()
