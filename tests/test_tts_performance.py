from __future__ import annotations

import importlib
import os
import sys
import tempfile
import time
import types
import unittest
from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))

from performance import (  # noqa: E402
    TtsPerformanceSample,
    nonnegative_remainder,
    resolve_audio_codec_device,
    summarize_samples,
)


@contextmanager
def stub_tts_dependencies():
    outetts = types.ModuleType("outetts")
    outetts.Backend = types.SimpleNamespace(LLAMACPP="llamacpp")
    outetts.GenerationConfig = lambda **kwargs: kwargs
    outetts.GenerationType = types.SimpleNamespace(CHUNKED="chunked")
    outetts.Interface = object
    outetts.LlamaCppQuantization = types.SimpleNamespace(
        FP16="FP16",
        Q8_0="Q8_0",
        Q6_K="Q6_K",
        Q5_K_M="Q5_K_M",
        Q4_K_M="Q4_K_M",
    )
    outetts.Models = types.SimpleNamespace(
        VERSION_1_0_SIZE_0_6B="0.6B",
        VERSION_1_0_SIZE_1B="1B",
    )
    outetts.SamplerConfig = lambda **kwargs: kwargs

    class ModelConfig:
        @classmethod
        def auto_config(cls, **_kwargs):
            return types.SimpleNamespace()

    outetts.ModelConfig = ModelConfig

    scipy = types.ModuleType("scipy")
    scipy.signal = types.ModuleType("signal")  # type: ignore[attr-defined]
    scipy.signal.resample_poly = lambda wav, *_args, **_kwargs: wav  # type: ignore[attr-defined]

    websockets = types.ModuleType("websockets")
    websockets.exceptions = types.SimpleNamespace(ConnectionClosed=Exception)
    websockets.serve = lambda *_args, **_kwargs: None

    soundfile = types.ModuleType("soundfile")
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(  # type: ignore[attr-defined]
        is_available=lambda: False,
        synchronize=lambda: None,
    )
    huggingface_hub = types.ModuleType("huggingface_hub")
    huggingface_hub.snapshot_download = lambda **_kwargs: ""

    modules = {
        "huggingface_hub": huggingface_hub,
        "outetts": outetts,
        "scipy": scipy,
        "scipy.signal": scipy.signal,
        "soundfile": soundfile,
        "torch": torch,
        "websockets": websockets,
    }
    with mock.patch.dict(sys.modules, modules):
        yield


class TtsPerformanceContractTests(unittest.TestCase):
    def test_audio_codec_device_resolution_is_explicit(self) -> None:
        self.assertEqual(
            resolve_audio_codec_device("auto", cuda_available=True),
            "cuda",
        )
        self.assertEqual(
            resolve_audio_codec_device("auto", cuda_available=False),
            "cpu",
        )
        self.assertEqual(
            resolve_audio_codec_device("cpu", cuda_available=True),
            "cpu",
        )
        with self.assertRaises(RuntimeError):
            resolve_audio_codec_device("cuda", cuda_available=False)
        with self.assertRaises(ValueError):
            resolve_audio_codec_device("metal", cuda_available=True)

    def test_performance_summary_reports_median_realtime_factor(self) -> None:
        samples = [
            TtsPerformanceSample(
                audio_seconds=2.0,
                generate_seconds=1.0,
                model_generate_seconds=0.8,
                codec_decode_seconds=0.15,
                pcm_conversion_seconds=0.01,
                worker_roundtrip_seconds=1.05,
                queue_wait_seconds=0.0,
                total_seconds=1.1,
            ),
            TtsPerformanceSample(
                audio_seconds=2.0,
                generate_seconds=2.0,
                model_generate_seconds=1.7,
                codec_decode_seconds=0.2,
                pcm_conversion_seconds=0.01,
                worker_roundtrip_seconds=2.05,
                queue_wait_seconds=0.2,
                total_seconds=2.3,
            ),
        ]

        summary = summarize_samples(samples)

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["median_realtime_factor"], 0.75)
        self.assertEqual(summary["median_model_realtime_factor"], 0.625)
        self.assertEqual(nonnegative_remainder(1.0, 0.8, 0.3), 0.0)

    def test_generation_timing_hook_reports_token_limit_exhaustion(self) -> None:
        sys.modules.pop("server", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "SPEAKER_DIR": temp_dir,
                "TTS_AUDIO_CODEC_DEVICE": "cpu",
                "TTS_DETAILED_TIMING": "0",
                "TTS_TOKENIZER_REPO": "fixture/tokenizer",
                "TTS_TOKENIZER_REVISION": "0123456789abcdef",
                "TTS_GGUF_REPO": "fixture/gguf",
                "TTS_GGUF_REVISION": "fedcba9876543210",
            }
            with stub_tts_dependencies(), mock.patch.dict(os.environ, env, clear=False):
                server = importlib.import_module("server")

        class FakeModel:
            def generate(self, input_ids, config):
                return [8, 9, 10]

        fake = types.SimpleNamespace(model=FakeModel(), audio_codec=types.SimpleNamespace())
        server.install_generation_timing_hooks(fake)
        server._active_timing_metrics = {
            "model_generate_seconds": 0.0,
            "codec_decode_seconds": 0.0,
            "generation_limit_reached": False,
        }
        try:
            output = fake.model.generate(
                [1, 2],
                types.SimpleNamespace(max_length=5),
            )
            self.assertEqual(output, [8, 9, 10])
            self.assertEqual(server._active_timing_metrics["model_prompt_tokens"], 2)
            self.assertEqual(server._active_timing_metrics["model_generated_tokens"], 3)
            self.assertEqual(server._active_timing_metrics["generation_headroom_tokens"], 0)
            self.assertTrue(server._active_timing_metrics["generation_limit_reached"])
        finally:
            server._active_timing_metrics = None

    def test_generate_tts_sync_reports_pipeline_overhead(self) -> None:
        sys.modules.pop("server", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "SPEAKER_DIR": temp_dir,
                "TTS_AUDIO_CODEC_DEVICE": "cpu",
                "TTS_DETAILED_TIMING": "0",
                "TTS_TOKENIZER_REPO": "fixture/tokenizer",
                "TTS_TOKENIZER_REVISION": "0123456789abcdef",
                "TTS_GGUF_REPO": "fixture/gguf",
                "TTS_GGUF_REVISION": "fedcba9876543210",
            }
            with stub_tts_dependencies(), mock.patch.dict(os.environ, env, clear=False):
                server = importlib.import_module("server")

        server.interface = types.SimpleNamespace(generate=lambda *, config: config)
        output, metrics = server.generate_tts_sync("fixture")

        self.assertEqual(output, "fixture")
        self.assertGreaterEqual(metrics["pipeline_overhead_seconds"], 0.0)

    def test_speaker_creation_validates_exact_transcript_with_aligner(self) -> None:
        sys.modules.pop("server", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wav_path = root / "chromie_zh.wav"
            wav_path.write_bytes(b"RIFF" + b"\x00" * 128)
            env = {
                "SPEAKER_DIR": temp_dir,
                "TTS_AUDIO_CODEC_DEVICE": "cpu",
                "TTS_DETAILED_TIMING": "0",
                "TTS_TOKENIZER_REPO": "fixture/tokenizer",
                "TTS_TOKENIZER_REVISION": "0123456789abcdef",
                "TTS_GGUF_REPO": "fixture/gguf",
                "TTS_GGUF_REVISION": "fedcba9876543210",
            }
            with stub_tts_dependencies(), mock.patch.dict(os.environ, env, clear=False):
                server = importlib.import_module("server")

            calls = []

            class FakeInterface:
                def create_speaker(self, path, *, whisper_model, whisper_device):
                    calls.append((path, whisper_model, whisper_device))
                    return {"fixture": True, "text": "你好，我是 Chromie。"}

            server.interface = FakeInterface()
            server.patch_torch_1d_audio_slice = nullcontext
            server.save_speaker_json = lambda *_args, **_kwargs: None
            server.create_speaker_profile_from_wav(
                "chromie_zh",
                wav_path,
                transcript=" 你好，我是 Chromie。 ",
            )

            self.assertEqual(calls, [(str(wav_path), "turbo", "cpu")])
            self.assertEqual(
                wav_path.with_suffix(".txt").read_text(encoding="utf-8"),
                "你好，我是 Chromie。\n",
            )
            self.assertEqual(
                server.speaker_transcript_similarity(
                    "Hello, I’m Chromie!",
                    "hello im chromie",
                ),
                1.0,
            )

    def test_server_timing_hooks_measure_model_and_codec_without_replacing_output(self) -> None:
        sys.modules.pop("server", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "SPEAKER_DIR": temp_dir,
                "TTS_AUDIO_CODEC_DEVICE": "cpu",
                "TTS_DETAILED_TIMING": "0",
                "TTS_TOKENIZER_REPO": "fixture/tokenizer",
                "TTS_TOKENIZER_REVISION": "0123456789abcdef",
                "TTS_GGUF_REPO": "fixture/gguf",
                "TTS_GGUF_REVISION": "fedcba9876543210",
            }
            with stub_tts_dependencies(), mock.patch.dict(os.environ, env, clear=False):
                server = importlib.import_module("server")

        class FakeModel:
            device = "cuda:0"

            def generate(self, value):
                time.sleep(0.001)
                return value + 1

            def parameters(self):
                return iter([types.SimpleNamespace(device="cuda:0")])

        class FakeCodec:
            device = "cpu"

            def __init__(self):
                self.model = FakeModel()

            def decode(self, value):
                time.sleep(0.001)
                return value * 2

        fake = types.SimpleNamespace(model=FakeModel(), audio_codec=FakeCodec())
        server.install_generation_timing_hooks(fake)
        metrics = {"model_generate_seconds": 0.0, "codec_decode_seconds": 0.0}
        server._active_timing_metrics = metrics
        try:
            self.assertEqual(fake.model.generate(2), 3)
            self.assertEqual(fake.audio_codec.decode(3), 6)
        finally:
            server._active_timing_metrics = None

        self.assertGreater(metrics["model_generate_seconds"], 0.0)
        self.assertGreater(metrics["codec_decode_seconds"], 0.0)
        description = server.describe_audio_codec(fake)
        self.assertEqual(description["reported"], "cpu")
        self.assertEqual(description["effective"], "cuda:0")
        server.TTS_AUDIO_CODEC_DEVICE = "cuda"
        server.TTS_AUDIO_CODEC_DEVICE_REQUESTED = "auto"
        server.validate_audio_codec_device(description)
        server.TTS_AUDIO_CODEC_DEVICE = "cpu"
        server.TTS_AUDIO_CODEC_DEVICE_REQUESTED = "cpu"
        with self.assertRaises(RuntimeError):
            server.validate_audio_codec_device(description)


if __name__ == "__main__":
    unittest.main()
