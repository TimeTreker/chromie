from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from collections.abc import AsyncIterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))

from oute_provider import OuteTTSProvider, OuteTTSProviderConfig  # noqa: E402
from provider import (  # noqa: E402
    TTSAudioChunk,
    TTSSynthesisCompleted,
    TTSSynthesisRequest,
    TTSProvider,
    TTSProviderCapabilities,
    TTSProviderRegistry,
    TTSModelArtifact,
    TTSStreamEvent,
)


def capabilities(provider_id: str = "fixture") -> TTSProviderCapabilities:
    return TTSProviderCapabilities(
        provider_id=provider_id,
        implementation="fixture runtime",
        software_license_id="Apache-2.0",
        model_artifacts=(
            TTSModelArtifact(
                kind="weights",
                artifact_id="fixture/model",
                revision="0123456789abcdef",
                license_id="Apache-2.0",
            ),
        ),
        license_review_status="declared_unreviewed",
        languages=("zh", "en"),
        sample_rates=(16000,),
        max_concurrency=1,
        native_text_streaming=True,
        native_audio_streaming=True,
        request_cancellation=True,
        speaker_profiles=False,
        voice_cloning=False,
    )


class FixtureProvider(TTSProvider):
    def __init__(self, provider_id: str = "fixture") -> None:
        self._capabilities = capabilities(provider_id)

    @property
    def capabilities(self) -> TTSProviderCapabilities:
        return self._capabilities

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def synthesize_stream(
        self,
        request: TTSSynthesisRequest,
    ) -> AsyncIterator[TTSStreamEvent]:
        yield TTSAudioChunk(pcm=b"\x00\x00", sample_rate=16000)
        yield TTSSynthesisCompleted(metrics={"request_id": request.request_id})

    async def health(self) -> dict[str, object]:
        return {"ready": True}

    async def list_speakers(self) -> list[str]:
        return ["default"]


class FakeWorker:
    def __init__(self, *, response: dict[str, object] | None = None) -> None:
        self.response = response or {
            "type": "generated",
            "pcm": b"\x01\x00" * 320,
            "timings": {
                "generate_seconds": 0.2,
                "model_generate_seconds": 0.1,
                "codec_decode_seconds": 0.05,
                "pcm_conversion_seconds": 0.01,
                "pipeline_overhead_seconds": 0.04,
                "generation_limit_reached": False,
            },
        }
        self.is_alive = False
        self.restart_count = 0
        self.ready_payload: dict[str, object] = {}
        self.requests: list[dict[str, object]] = []

    async def start(self) -> None:
        self.is_alive = True

    async def stop(self) -> None:
        self.is_alive = False

    async def request(self, payload: dict[str, object]) -> dict[str, object]:
        self.requests.append(payload)
        return dict(self.response)


def oute_provider(worker: FakeWorker, root: Path) -> OuteTTSProvider:
    async def select_worker() -> tuple[int, FakeWorker]:
        return 0, worker

    def worker_status() -> list[dict[str, object]]:
        return [
            {
                "index": 0,
                "alive": worker.is_alive,
                "restart_count": worker.restart_count,
            }
        ]

    return OuteTTSProvider(
        config=OuteTTSProviderConfig(
            tokenizer_id="OuteAI/OuteTTS-1.0-0.6B",
            tokenizer_revision="e7bcd87b0ca47fd8c46317c8f745a5e4e19c7b5c",
            gguf_id="OuteAI/OuteTTS-1.0-0.6B-GGUF",
            gguf_revision="d85d0f1e5242c3fb04c95f55bd99ec3ebd4c2d16",
            sample_rate=8000,
            chunk_ms=20,
            max_concurrency=1,
            generation_retries=1,
            max_length=2048,
            context_size=2048,
            quantization="FP16",
            audio_codec_device="cpu",
            metrics_window=4,
            speaker_dir=root,
        ),
        workers=[worker],
        select_worker=select_worker,
        worker_status=worker_status,
        list_speaker_ids=lambda: ["default"],
        validate_speaker_path=lambda path: path,
    )


class TTSProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_is_explicit_and_fails_closed(self) -> None:
        registry = TTSProviderRegistry()
        registry.register("fixture", FixtureProvider)
        self.assertEqual(registry.provider_ids(), ("fixture",))
        self.assertEqual(registry.create("fixture").capabilities.provider_id, "fixture")
        with self.assertRaisesRegex(RuntimeError, "Unknown TTS_PROVIDER"):
            registry.create("missing")
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register("fixture", FixtureProvider)

        mismatched = TTSProviderRegistry()
        mismatched.register("declared", lambda: FixtureProvider("different"))
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            mismatched.create("declared")

    async def test_contract_serializes_streaming_and_provenance_truthfully(self) -> None:
        payload = capabilities().as_dict()
        self.assertEqual(payload["contract_version"], 1)
        self.assertEqual(payload["languages"], ["zh", "en"])
        self.assertEqual(payload["software_license_id"], "Apache-2.0")
        self.assertEqual(payload["model_artifacts"][0]["kind"], "weights")
        self.assertTrue(payload["native_audio_streaming"])
        with self.assertRaisesRegex(ValueError, "immutable commit"):
            TTSModelArtifact(
                kind="weights",
                artifact_id="fixture/model",
                revision="",
                license_id="Apache-2.0",
            )
        with self.assertRaisesRegex(ValueError, "immutable commit"):
            TTSModelArtifact(
                kind="weights",
                artifact_id="fixture/model",
                revision="main",
                license_id="Apache-2.0",
            )

    async def test_oute_adapter_yields_transport_chunks_and_common_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            worker = FakeWorker()
            provider = oute_provider(worker, Path(temp_dir))
            await provider.start()
            events = [
                event
                async for event in provider.synthesize_stream(
                    TTSSynthesisRequest(
                        request_id="req-1",
                        text="你好。",
                        speaker_id="default",
                    )
                )
            ]

            chunks = [event for event in events if isinstance(event, TTSAudioChunk)]
            completed = [
                event for event in events if isinstance(event, TTSSynthesisCompleted)
            ]
            self.assertEqual(len(chunks), 2)
            self.assertEqual(sum(len(item.pcm) for item in chunks), 640)
            self.assertEqual(len(completed), 1)
            self.assertEqual(completed[0].metrics["worker_index"], 0)
            self.assertEqual(completed[0].metrics["quantization"], "FP16")
            self.assertFalse(provider.capabilities.native_audio_streaming)
            self.assertTrue(provider.capabilities.request_cancellation)
            health = await provider.health()
            self.assertEqual(health["recent_performance"]["count"], 1)
            await provider.stop()

    async def test_cancelling_stream_propagates_to_native_worker_request(self) -> None:
        cancelled = asyncio.Event()

        class BlockingWorker(FakeWorker):
            async def request(self, payload: dict[str, object]) -> dict[str, object]:
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()

        with tempfile.TemporaryDirectory() as temp_dir:
            provider = oute_provider(BlockingWorker(), Path(temp_dir))

            async def consume() -> None:
                async for _event in provider.synthesize_stream(
                    TTSSynthesisRequest(request_id="cancel-me", text="Long speech")
                ):
                    pass

            task = asyncio.create_task(consume())
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(cancelled.is_set())


if __name__ == "__main__":
    unittest.main()
