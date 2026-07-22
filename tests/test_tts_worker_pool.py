from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))


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


class TtsWorkerPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_selection_round_robins_configured_pool(self) -> None:
        sys.modules.pop("server", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "SPEAKER_DIR": temp_dir,
                "TTS_WORKER_COUNT": "3",
                "TTS_TOKENIZER_REPO": "fixture/tokenizer",
                "TTS_TOKENIZER_REVISION": "0123456789abcdef",
                "TTS_GGUF_REPO": "fixture/gguf",
                "TTS_GGUF_REVISION": "fedcba9876543210",
            }
            with stub_tts_dependencies(), mock.patch.dict(os.environ, env, clear=False):
                server = importlib.import_module("server")

        indexes = []
        for _ in range(5):
            index, _worker = await server.select_generation_worker()
            indexes.append(index)

        self.assertEqual(server.TTS_WORKER_COUNT, 3)
        self.assertEqual(indexes, [0, 1, 2, 0, 1])
        self.assertEqual(
            [item["index"] for item in server.generation_worker_status()],
            [0, 1, 2],
        )


if __name__ == "__main__":
    unittest.main()
