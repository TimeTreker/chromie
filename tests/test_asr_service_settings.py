from __future__ import annotations

import unittest

from asr.settings import (
    ASRServiceSettings,
    DEFAULT_SENSEVOICE_MODEL_PATH,
    DEFAULT_SENSEVOICE_MODEL_REVISION,
)


class ASRServiceSettingsTests(unittest.TestCase):
    def test_defaults_are_typed_and_stable(self) -> None:
        settings = ASRServiceSettings.from_env({})

        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 9001)
        self.assertEqual(settings.mode, "final")
        self.assertEqual(settings.model_name, DEFAULT_SENSEVOICE_MODEL_PATH)
        self.assertEqual(settings.model_revision, DEFAULT_SENSEVOICE_MODEL_REVISION)
        self.assertEqual(settings.sample_rate, 16000)
        self.assertTrue(settings.sherpa_use_itn)
        self.assertTrue(settings.startup_warmup_enabled)

    def test_profile_values_are_parsed_once_from_snapshot(self) -> None:
        environ = {
            "ASR_DEVICE": "cpu",
            "ASR_PORT": "9101",
            "ASR_SAMPLE_RATE": "48000",
            "ASR_STARTUP_WARMUP_ENABLED": "false",
            "ASR_STARTUP_WARMUP_AUDIO_SECONDS": "0.5",
            "SHERPA_ONNX_NUM_THREADS": "6",
        }

        settings = ASRServiceSettings.from_env(environ)
        environ["ASR_DEVICE"] = "cuda"
        environ["ASR_PORT"] = "9999"

        self.assertEqual(settings.device, "cpu")
        self.assertEqual(settings.port, 9101)
        self.assertEqual(settings.sample_rate, 48000)
        self.assertFalse(settings.startup_warmup_enabled)
        self.assertEqual(settings.startup_warmup_audio_seconds, 0.5)
        self.assertEqual(settings.sherpa_num_threads, 6)

    def test_language_precedence_preserves_explicit_sherpa_value(self) -> None:
        settings = ASRServiceSettings.from_env(
            {
                "ASR_LANGUAGE": "zh",
                "SHERPA_ONNX_LANGUAGE": "en",
            }
        )
        inherited = ASRServiceSettings.from_env({"ASR_LANGUAGE": "zh"})

        self.assertEqual(settings.language, "zh")
        self.assertEqual(settings.sherpa_language, "en")
        self.assertEqual(inherited.sherpa_language, "zh")

    def test_invalid_boolean_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "ASR_STARTUP_WARMUP_ENABLED"):
            ASRServiceSettings.from_env(
                {"ASR_STARTUP_WARMUP_ENABLED": "sometimes"}
            )

    def test_invalid_numeric_range_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, "ASR_PORT"):
            ASRServiceSettings.from_env({"ASR_PORT": "70000"})
        with self.assertRaisesRegex(ValueError, "ASR_SAMPLE_RATE"):
            ASRServiceSettings.from_env({"ASR_SAMPLE_RATE": "not-a-number"})

    def test_backend_config_is_derived_without_new_environment_reads(self) -> None:
        settings = ASRServiceSettings.from_env(
            {
                "ASR_MODEL": "/models/sensevoice",
                "ASR_MODEL_REVISION": "revision-1",
                "ASR_DEVICE": "cpu",
                "SHERPA_ONNX_PROVIDER": "cpu",
                "SHERPA_ONNX_DEBUG": "true",
            }
        )

        backend = settings.backend_config()

        self.assertEqual(backend.model_name, "/models/sensevoice")
        self.assertEqual(backend.model_revision, "revision-1")
        self.assertEqual(backend.device, "cpu")
        self.assertEqual(backend.sherpa_provider, "cpu")
        self.assertTrue(backend.sherpa_debug)

    def test_safe_diagnostics_omit_override_file_paths(self) -> None:
        settings = ASRServiceSettings.from_env(
            {
                "SHERPA_ONNX_MODEL_FILE": "/private/alice/model.onnx",
                "SHERPA_ONNX_TOKENS_FILE": "/private/alice/tokens.txt",
            }
        )

        diagnostics = settings.safe_diagnostics()

        self.assertNotIn("sherpa_model_file", diagnostics)
        self.assertNotIn("sherpa_tokens_file", diagnostics)
        self.assertEqual(diagnostics["port"], 9001)


if __name__ == "__main__":
    unittest.main()
