import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tts"))

# The resolver only needs snapshot_download at call time; provide a lightweight
# stand-in when the test environment does not install TTS dependencies.
try:
    import huggingface_hub  # noqa: F401
except ImportError:
    import types

    module = types.ModuleType("huggingface_hub")
    module.snapshot_download = lambda **kwargs: ""
    sys.modules["huggingface_hub"] = module

from model_sources import apply_model_sources, gguf_filename, resolve_model_sources


class TtsModelSourcesTests(unittest.TestCase):
    def test_quantization_maps_to_exact_release_filename(self) -> None:
        self.assertEqual(
            gguf_filename("0.6B", "Q4_K_M"),
            "OuteTTS-1.0-0.6B-Q4_K_M.gguf",
        )
        with self.assertRaises(RuntimeError):
            gguf_filename("1B", "Q4_K_M")

    def test_resolver_uses_revisions_and_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tokenizer = root / "tokenizer"
            gguf = root / "gguf"
            tokenizer.mkdir()
            gguf.mkdir()
            filename = "OuteTTS-1.0-0.6B-FP16.gguf"
            (gguf / filename).write_bytes(b"fixture")
            calls = []

            def downloader(**kwargs):
                calls.append(kwargs)
                return str(tokenizer if len(calls) == 1 else gguf)

            env = {
                "TTS_TOKENIZER_REPO": "example/tokenizer",
                "TTS_TOKENIZER_REVISION": "abc123",
                "TTS_GGUF_REPO": "example/gguf",
                "TTS_GGUF_REVISION": "def456",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                resolved = resolve_model_sources(
                    "0.6B", "FP16", downloader=downloader
                )

            self.assertEqual(calls[0]["revision"], "abc123")
            self.assertIn("*.json", calls[0]["allow_patterns"])
            self.assertEqual(calls[1]["revision"], "def456")
            self.assertEqual(calls[1]["allow_patterns"], [filename])
            self.assertEqual(Path(resolved.model_path), gguf / filename)

            config = type("Config", (), {})()
            self.assertIs(apply_model_sources(config, resolved), config)
            self.assertEqual(config.tokenizer_path, str(tokenizer.resolve()))
            self.assertEqual(config.model_path, str((gguf / filename).resolve()))

    def test_missing_revision_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TTS_TOKENIZER_REPO"):
                resolve_model_sources("0.6B", "FP16", downloader=lambda **_: "")


if __name__ == "__main__":
    unittest.main()
