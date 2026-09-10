from __future__ import annotations

import asyncio
import importlib.util
import hashlib
import json
import multiprocessing
from functools import partial
import os
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import AsyncIterator
from multiprocessing.connection import Connection
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


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


def stream_fixture_target(connection: Connection, *, cancellation_event=None) -> None:
    connection.send({"type": "ready", "fixture": True})
    while True:
        payload = connection.recv()
        if payload.get("type") == "shutdown":
            connection.send({"type": "stopped"})
            return
        if payload.get("text") in {"cooperative-cancel", "cooperative-after-audio"}:
            if payload["text"] == "cooperative-after-audio":
                connection.send({"type": "audio", "pcm": b"old", "sample_rate": 8000})
            while not cancellation_event.is_set():
                time.sleep(0.005)
            # Cleanup must keep the event set and own the request lock until its
            # terminal event; a queued successor must not clear it early.
            time.sleep(0.04)
            if not cancellation_event.is_set():
                connection.send({"type": "error", "message": "next request raced cleanup"})
                continue
            connection.send({"type": "complete"})
            continue
        if payload.get("text") == "check-cleared" and cancellation_event.is_set():
            connection.send({"type": "error", "message": "stale cancellation"})
            continue
        if payload.get("text") in {"block", "silent"}:
            while True:
                time.sleep(1)
        if payload.get("text") == "worker-error":
            connection.send({"type": "error", "message": "fixture failure"})
            continue
        if payload.get("text") == "duplicate-ready":
            connection.send({"type": "ready", "fixture": "delayed"})
        if payload.get("text") == "audio-then-stall":
            connection.send(
                {"type": "audio", "pcm": b"\x01\x00" * 80, "sample_rate": 8000}
            )
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
    failure_restart_count = 0
    cancellation_mode = "bounded_drain_then_restart_worker"
    worker_warmed = True
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
    async def test_cooperative_cancel_preserves_worker_and_serializes_cleanup(self) -> None:
        signal = multiprocessing.get_context("spawn").Event()
        worker = StreamingProcessWorker(
            partial(stream_fixture_target, cancellation_event=signal),
            name="cooperative-test", startup_timeout_s=5,
            cancellation_event=signal, cancel_drain_timeout_s=0.5,
        )
        await worker.start()
        initial_pid = worker._process.pid
        try:
            for early in (False, True):
                with self.subTest(early=early):
                    text = "cooperative-cancel" if early else "cooperative-after-audio"
                    stream = worker.stream({"type": "synthesize", "text": text})
                    if early:
                        task = asyncio.create_task(anext(stream))
                        await asyncio.sleep(0.02)
                        task.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                    else:
                        self.assertEqual((await anext(stream))["pcm"], b"old")
                        cleanup = asyncio.create_task(stream.aclose())
                        await asyncio.sleep(0)
                    current = [event async for event in worker.stream({
                        "type": "synthesize", "text": "check-cleared",
                    })]
                    if not early:
                        await cleanup
                    self.assertEqual(
                        [event["pcm"] for event in current if event["type"] == "audio"],
                        [b"\x01\x00" * 80],
                    )
                    self.assertEqual(worker._process.pid, initial_pid)
            self.assertEqual(worker.cancel_drain_count, 2)
            self.assertEqual(worker.restart_count, 0)
            self.assertEqual(
                worker.cancellation_mode, "signal_then_bounded_drain_then_restart_worker"
            )
        finally:
            await worker.stop()

    async def test_cooperative_cancel_timeout_keeps_restart_fallback(self) -> None:
        signal = multiprocessing.get_context("spawn").Event()
        worker = StreamingProcessWorker(
            partial(stream_fixture_target, cancellation_event=signal),
            name="cooperative-fallback-test", startup_timeout_s=5,
            cancellation_event=signal, cancel_drain_timeout_s=0.05,
        )
        await worker.start()
        initial_pid = worker._process.pid
        try:
            async def consume():
                return [event async for event in worker.stream({"text": "block"})]
            task = asyncio.create_task(consume())
            await asyncio.sleep(0.02)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertNotEqual(worker._process.pid, initial_pid)
            self.assertEqual(worker.cancel_restart_count, 1)
            events = [event async for event in worker.stream({"text": "check-cleared"})]
            self.assertEqual(events[-1]["type"], "complete")
        finally:
            await worker.stop()

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
        self.assertEqual(completed.metrics["queue_wait_seconds"], 0.0)

        health = await provider.health()
        self.assertEqual(
            health["cancellation_mode"],
            "bounded_drain_then_restart_worker",
        )
        self.assertEqual(health["worker_cancel_drain_count"], 0)
        self.assertEqual(health["worker_cancel_restart_count"], 0)
        self.assertEqual(health["worker_failure_restart_count"], 0)

    async def test_streaming_worker_invalidates_after_worker_error(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-error-worker",
            startup_timeout_s=5.0,
        )
        await worker.start()
        try:
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                async for _event in worker.stream(
                    {"type": "synthesize", "text": "worker-error"}
                ):
                    pass
            self.assertFalse(worker.is_alive)
            self.assertEqual(worker.failure_restart_count, 1)

            events = [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "recover"}
                )
            ]
            self.assertEqual([event["type"] for event in events], ["audio", "complete"])
        finally:
            await worker.stop()

    async def test_streaming_worker_discards_delayed_startup_control_event(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-delayed-ready-worker",
            startup_timeout_s=5.0,
        )
        await worker.start()
        try:
            events = [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "duplicate-ready"}
                )
            ]
            self.assertEqual(
                [event["type"] for event in events],
                ["audio", "complete"],
            )
        finally:
            await worker.stop()

    async def test_streaming_worker_first_audio_timeout_invalidates_worker(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-first-audio-timeout-worker",
            startup_timeout_s=5.0,
            first_audio_timeout_s=0.05,
            request_timeout_s=1.0,
        )
        await worker.start()
        try:
            with self.assertRaisesRegex(TimeoutError, "produced no audio"):
                async for _event in worker.stream(
                    {"type": "synthesize", "text": "silent"}
                ):
                    pass
            self.assertFalse(worker.is_alive)
            self.assertEqual(worker.failure_restart_count, 1)
        finally:
            await worker.stop()

    async def test_streaming_worker_uses_cold_timeout_until_first_completion(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-cold-watchdog-worker",
            startup_timeout_s=5.0,
            first_audio_timeout_s=0.02,
            request_timeout_s=0.04,
            cold_first_audio_timeout_s=0.2,
            cold_request_timeout_s=0.3,
        )
        await worker.start()
        try:
            events = [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "slow-complete"}
                )
            ]
            self.assertEqual([event["type"] for event in events], ["audio", "complete"])
            self.assertTrue(worker.worker_warmed)

            with self.assertRaisesRegex(TimeoutError, "did not complete"):
                async for _event in worker.stream(
                    {"type": "synthesize", "text": "audio-then-stall"}
                ):
                    pass
            self.assertFalse(worker.is_alive)
        finally:
            await worker.stop()

    async def test_streaming_worker_reports_wait_for_singleton_owner(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-queue-evidence-worker",
            startup_timeout_s=5.0,
        )
        await worker.start()

        async def consume_slow() -> list[dict[str, object]]:
            return [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "slow-complete"}
                )
            ]

        try:
            first = asyncio.create_task(consume_slow())
            await asyncio.sleep(0.01)
            second = [
                event
                async for event in worker.stream(
                    {"type": "synthesize", "text": "recover"}
                )
            ]
            await first
            self.assertGreater(
                float(second[-1]["worker_queue_wait_seconds"]),
                0.05,
            )
        finally:
            await worker.stop()

    async def test_streaming_worker_total_timeout_catches_post_audio_stall(self) -> None:
        worker = StreamingProcessWorker(
            stream_fixture_target,
            name="candidate-test-request-timeout-worker",
            startup_timeout_s=5.0,
            first_audio_timeout_s=1.0,
            request_timeout_s=0.05,
        )
        await worker.start()
        try:
            with self.assertRaisesRegex(TimeoutError, "did not complete"):
                async for _event in worker.stream(
                    {"type": "synthesize", "text": "audio-then-stall"}
                ):
                    pass
            self.assertFalse(worker.is_alive)
            self.assertEqual(worker.failure_restart_count, 1)
        finally:
            await worker.stop()

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
        self.assertEqual(lock["default_provider"], cosy.PROVIDER_ID)
        self.assertIn("chromie-tts:", compose)
        self.assertIn("dockerfile: tts_candidates/cosyvoice/Dockerfile", compose)
        self.assertIn('"127.0.0.1:5000:5000"', compose)
        self.assertIn("chromie-tts-oute:", compose)
        self.assertIn('profiles: ["tts-evaluation"]', compose)
        self.assertIn('"127.0.0.1:5001:5000"', compose)
        self.assertIn('"127.0.0.1:5002:5000"', compose)
        self.assertIn("TTS_VOICE_ROOT", compose)
        self.assertIn("assets/tts/voices", compose)
        self.assertGreaterEqual(compose.count("type: bind"), 2)
        self.assertIn("target: /voices", compose)
        self.assertIn("target: /evaluation", compose)
        self.assertIn("./hf_cache/modelscope:/root/.cache/modelscope", compose)
        self.assertIn("TTS_CANDIDATE_CANCEL_DRAIN_TIMEOUT_SEC", compose)
        self.assertIn("Qwen/Qwen3-TTS-12Hz-0.6B-Base", compose)
        cosy_dockerfile = (ROOT / "tts_candidates" / "cosyvoice" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("onnxruntime-gpu==1.18.1", cosy_dockerfile)
        self.assertNotIn("onnxruntime-gpu==1.18.0", cosy_dockerfile)

        qwen_dockerfile = (ROOT / "tts_candidates" / "qwen3" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        legacy_dockerfile = (ROOT / "tts" / "Dockerfile").read_text(encoding="utf-8")
        for dockerfile in (cosy_dockerfile, qwen_dockerfile, legacy_dockerfile):
            self.assertIn("settings.py", dockerfile)


    def test_cosyvoice_catalog_exposes_and_routes_builtin_speakers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            speaker_ids = ("chromie_zh", "chromie_en", "chromie_mixed")
            manifest = {
                "schema_version": 1,
                "default_speaker_id": "chromie_mixed",
                "speakers": list(speaker_ids),
                "language_routes": {
                    "zh": "chromie_zh",
                    "en": "chromie_en",
                    "mixed": "chromie_mixed",
                },
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            for index, speaker_id in enumerate(speaker_ids, start=1):
                profile = root / speaker_id
                profile.mkdir()
                wav_path = profile / "reference.wav"
                wav_path.write_bytes(
                    b"RIFF" + (64).to_bytes(4, "little") + b"WAVE" + bytes([index]) * 64
                )
                audio_sha = hashlib.sha256(wav_path.read_bytes()).hexdigest()
                (profile / "reference.json").write_text(
                    json.dumps(
                        {
                            "speaker_id": speaker_id,
                            "text": f"reference {speaker_id}",
                            "audio_sha256": audio_sha,
                            "license_id": "project-ai-generated-voice",
                            "languages": ["zh" if speaker_id == "chromie_zh" else "en"],
                        }
                    ),
                    encoding="utf-8",
                )
            cosy = load_provider_impl(
                "tts_candidates/cosyvoice/provider_impl.py",
                "cosy_catalog_fixture",
            )
            with patch.dict(os.environ, {"TTS_VOICE_ROOT": str(root)}, clear=False):
                voices = cosy.runtime_voices()
            self.assertEqual(voices.default_speaker_id, "chromie_mixed")
            self.assertEqual(
                voices.resolve(
                    speaker_id="default", language_hint="zh-CN", text="你好"
                ).speaker_id,
                "chromie_zh",
            )
            self.assertEqual(
                voices.resolve(
                    speaker_id="chromie_en", language_hint="zh", text="你好"
                ).speaker_id,
                "chromie_en",
            )

    def test_cosyvoice_cancel_closes_tokens_and_skips_only_cancelled_acoustics(self) -> None:
        cosy = load_provider_impl(
            "tts_candidates/cosyvoice/provider_impl.py", "cosy_cancel_fixture"
        )
        signal = threading.Event()
        entered, closed = [], []
        def tokens(**kwargs):
            entered.append(kwargs)
            try:
                yield from (1, 2, 3)
            finally:
                closed.append(True)
        waveform, empty = object(), object()
        acoustic = Mock(return_value=waveform)
        native = SimpleNamespace(
            llm=SimpleNamespace(inference=tokens, inference_bistream=tokens),
            token2wav=acoustic,
        )
        torch = SimpleNamespace(zeros=Mock(return_value=empty))
        cosy._enable_native_cancellation(native, signal, torch)
        for name in ("inference", "inference_bistream"):
            with self.subTest(name=name):
                signal.clear()
                stream = getattr(native.llm, name)(text="original")
                self.assertEqual(next(stream), 1)
                self.assertIs(native.token2wav(token="original"), waveform)
                signal.set()
                self.assertEqual(list(stream), [])
                self.assertEqual(len(entered), len(closed))
                before = acoustic.call_count
                self.assertIs(native.token2wav(token="cancelled"), empty)
                self.assertEqual(acoustic.call_count, before)
                self.assertEqual(list(getattr(native.llm, name)(text="cancelled")), [])
                signal.clear()
                self.assertEqual(list(getattr(native.llm, name)(text="next")), [1, 2, 3])
                self.assertIs(native.token2wav(token="next"), waveform)
                self.assertEqual(len(entered), len(closed))

    def test_cosyvoice_worker_prepares_then_reuses_selected_voice_conditioning(self) -> None:
        cosy = load_provider_impl(
            "tts_candidates/cosyvoice/provider_impl.py", "cosy_cached_voice_fixture"
        )
        requests = [
            ("你好。", "default", "chromie_zh"),
            ("Hello.", "default", "chromie_en"),
            ("你好，Chromie.", "default", "chromie_mixed"),
            ("再次问好。", "default", "chromie_zh"),
            ("你好。", "chromie_en", "chromie_en"),
        ]
        environment = {
            "TTS_VOICE_ROOT": str(ROOT / "assets/tts/voices"),
            "TTS_DEFAULT_SPEAKER": "chromie_mixed",
            "COSYVOICE3_PROMPT_PREFIX": "You are a helpful assistant.",
        }
        with patch.dict(os.environ, environment):
            voices = cosy.runtime_voices()
            # A replacement worker must prepare its own cache before readiness.
            for generation in range(2):
                with self.subTest(generation=generation):
                    prepared = {}
                    events = []
                    initial_hops = []
                    native_model = SimpleNamespace(token_hop_len=25)

                    def prepare(prompt, wav, speaker):
                        prepared[speaker] = (prompt, wav)
                        events.append(("prepare", speaker))
                        return True

                    def infer(text, prompt, wav, *, zero_shot_spk_id, stream):
                        self.assertTrue(stream)
                        self.assertEqual(prepared[zero_shot_spk_id], (prompt, wav))
                        initial_hops.append(native_model.token_hop_len)
                        native_model.token_hop_len = 100
                        events.append(("infer", text, zero_shot_spk_id))
                        yield {"tts_speech": object()}
                        self.assertEqual(native_model.token_hop_len, 100)

                    model = SimpleNamespace(
                        model=native_model,
                        sample_rate=24000,
                        add_zero_shot_spk=prepare,
                        inference_zero_shot=infer,
                    )
                    connection = Mock()
                    connection.recv.side_effect = [
                        {"type": "synthesize", "text": text, "speaker_id": speaker}
                        for text, speaker, _expected in requests
                    ] + [{"type": "shutdown"}]
                    connection.send.side_effect = lambda item: events.append(
                        ("send", item)
                    )
                    modules = {
                        "torch": SimpleNamespace(OutOfMemoryError=MemoryError),
                        "cosyvoice.cli.cosyvoice": SimpleNamespace(
                            AutoModel=lambda **_kwargs: model
                        ),
                        "huggingface_hub": SimpleNamespace(
                            snapshot_download=lambda **_kwargs: "/fixture-model"
                        ),
                    }
                    with (
                        patch.dict(sys.modules, modules),
                        patch.object(threading, "excepthook"),
                        patch.object(cosy, "tensor_pcm16", return_value=b"\x01\x00"),
                    ):
                        cosy.worker_target(connection)

                    self.assertEqual(set(prepared), set(voices.profiles))
                    self.assertEqual(initial_hops, [25] * len(requests))
                    profile_count = len(voices.profiles)
                    self.assertEqual(events[profile_count][0], "send")
                    self.assertEqual(events[profile_count][1]["type"], "ready")
                    self.assertEqual(
                        sum(e[0] == "prepare" for e in events), profile_count
                    )
                    self.assertEqual(
                        [e[1:] for e in events if e[0] == "infer"],
                        [(text, expected) for text, _speaker, expected in requests],
                    )
                    completed = [
                        e[1]["provider_metadata"] for e in events
                        if e[0] == "send" and e[1]["type"] == "complete"
                    ]
                    self.assertEqual(len(completed), len(requests))
                    for metadata, (_text, _speaker, expected) in zip(completed, requests):
                        self.assertEqual(metadata["speaker_id"], expected)
                        self.assertEqual(
                            metadata["reference_sha256"],
                            voices.profiles[expected].audio_sha256,
                        )
                    for speaker, (prompt, wav) in prepared.items():
                        profile = voices.profiles[speaker]
                        self.assertEqual(
                            prompt,
                            environment["COSYVOICE3_PROMPT_PREFIX"]
                            + "<|endofprompt|>" + profile.text,
                        )
                        self.assertEqual(wav, str(profile.wav_path))

    def test_cosyvoice_reference_preparation_failure_prevents_readiness(self) -> None:
        cosy = load_provider_impl(
            "tts_candidates/cosyvoice/provider_impl.py", "cosy_cache_failure_fixture"
        )
        for failure in (False, RuntimeError("reference preparation failed")):
            with self.subTest(failure=failure):
                prepare = Mock(return_value=failure)
                if isinstance(failure, Exception):
                    prepare.side_effect = failure
                modules = {
                    "torch": SimpleNamespace(OutOfMemoryError=MemoryError),
                    "cosyvoice.cli.cosyvoice": SimpleNamespace(
                        AutoModel=lambda **_kwargs: SimpleNamespace(
                            model=SimpleNamespace(token_hop_len=25),
                            sample_rate=24000, add_zero_shot_spk=prepare
                        )
                    ),
                    "huggingface_hub": SimpleNamespace(
                        snapshot_download=lambda **_kwargs: "/fixture-model"
                    ),
                }
                connection = Mock()
                with (
                    patch.dict(os.environ, {"TTS_VOICE_ROOT": str(ROOT / "assets/tts/voices")}),
                    patch.dict(sys.modules, modules),
                    patch.object(threading, "excepthook"),
                ):
                    cosy.worker_target(connection)
                connection.recv.assert_not_called()
                connection.send.assert_called_once()
                result = connection.send.call_args.args[0]
                self.assertEqual(result["type"], "error")
                self.assertIn("CosyVoice startup failed", result["message"])

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
