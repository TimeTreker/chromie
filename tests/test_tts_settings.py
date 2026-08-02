from __future__ import annotations

import importlib.util
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "tts" / "settings.py"
spec = importlib.util.spec_from_file_location("chromie_tts_settings", SETTINGS_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load TTS settings")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
TTSConfigurationError = module.TTSConfigurationError
TTSServiceSettings = module.TTSServiceSettings


class TTSServiceSettingsTests(unittest.TestCase):
    def test_defaults_are_typed_and_immutable(self) -> None:
        settings = TTSServiceSettings.from_env({})
        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 5000)
        self.assertEqual(settings.context_size, 4096)
        self.assertTrue(settings.reset_llama_state)
        with self.assertRaises(Exception):
            settings.port = 6000

    def test_invalid_values_name_the_environment_key(self) -> None:
        with self.assertRaisesRegex(TTSConfigurationError, "TTS_PORT"):
            TTSServiceSettings.from_env({"TTS_PORT": "invalid"})
        with self.assertRaisesRegex(
            TTSConfigurationError, "TTS_SPEAKER_TRANSCRIPT_MIN_SIMILARITY"
        ):
            TTSServiceSettings.from_env(
                {"TTS_SPEAKER_TRANSCRIPT_MIN_SIMILARITY": "1.2"}
            )
        with self.assertRaisesRegex(TTSConfigurationError, "TTS_RESET_LLAMA_STATE"):
            TTSServiceSettings.from_env({"TTS_RESET_LLAMA_STATE": "maybe"})

    def test_model_source_contract_fails_closed(self) -> None:
        settings = TTSServiceSettings.from_env({})
        with self.assertRaisesRegex(TTSConfigurationError, "TTS_TOKENIZER_REPO"):
            settings.required_model_sources()
        complete = TTSServiceSettings.from_env(
            {
                "TTS_TOKENIZER_REPO": "example/tokenizer",
                "TTS_TOKENIZER_REVISION": "abc",
                "TTS_GGUF_REPO": "example/gguf",
                "TTS_GGUF_REVISION": "def",
            }
        )
        self.assertEqual(
            complete.required_model_sources(),
            ("example/tokenizer", "abc", "example/gguf", "def"),
        )

    def test_tts_runtime_has_no_direct_environment_reads(self) -> None:
        for path in (ROOT / "tts").glob("*.py"):
            if path.name == "settings.py":
                continue
            with self.subTest(path=path.name):
                self.assertNotIn("os.getenv", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
