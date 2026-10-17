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
TTSCandidateSettings = module.TTSCandidateSettings


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

    def test_candidate_settings_are_typed_and_name_the_key(self) -> None:
        settings = TTSCandidateSettings.from_env({})
        self.assertIsNone(settings.voice_root)
        self.assertEqual(settings.worker_startup_timeout_s, 1200.0)
        self.assertEqual(settings.transport_chunk_ms, 120)
        self.assertEqual(settings.request_timeout_s, 60.0)
        configured = TTSCandidateSettings.from_env(
            {"TTS_VOICE_ROOT": "/voices", "TTS_DEFAULT_SPEAKER": "chromie_en"}
        )
        self.assertEqual(configured.voice_root, Path("/voices"))
        self.assertEqual(configured.default_speaker, "chromie_en")
        for key, value in (
            ("TTS_WORKER_STARTUP_TIMEOUT_SEC", "soon"),
            ("TTS_CANDIDATE_REQUEST_TIMEOUT_SEC", "-1"),
            ("TTS_TRANSPORT_CHUNK_MS", "1.5"),
        ):
            with self.subTest(key=key), self.assertRaisesRegex(TTSConfigurationError, key):
                TTSCandidateSettings.from_env({key: value})
        with self.assertRaisesRegex(TTSConfigurationError, "COSYVOICE3_FP16"):
            module.required_boolean("COSYVOICE3_FP16", True, {"COSYVOICE3_FP16": "2"})
        self.assertEqual(
            module.required_text("QWEN3_TTS_DTYPE", "bfloat16", {"QWEN3_TTS_DTYPE": " "}),
            "bfloat16",
        )
        with self.assertRaisesRegex(TTSConfigurationError, "QWEN3_TTS_DTYPE is required"):
            module.required_text("QWEN3_TTS_DTYPE", "", {"QWEN3_TTS_DTYPE": " "})

    def test_tts_runtime_has_no_direct_environment_reads(self) -> None:
        for path in [*(ROOT / "tts").glob("*.py"), *(ROOT / "tts_candidates").rglob("*.py")]:
            if path.name == "settings.py":
                continue
            with self.subTest(path=path.name):
                self.assertNotIn("os.getenv", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
