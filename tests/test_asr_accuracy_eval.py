from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_asr_accuracy.py"
SPEC = importlib.util.spec_from_file_location("compare_asr_accuracy", SCRIPT)
assert SPEC is not None
compare_asr_accuracy = importlib.util.module_from_spec(SPEC)
sys.modules["compare_asr_accuracy"] = compare_asr_accuracy
assert SPEC.loader is not None
SPEC.loader.exec_module(compare_asr_accuracy)


class ASRAccuracyEvalTests(unittest.TestCase):
    def test_normalize_text_removes_case_punctuation_and_special_tokens(self) -> None:
        self.assertEqual(
            compare_asr_accuracy.normalize_text(
                "The <|SPECIAL_TOKEN_30|> Boy, SAID: Hello!"
            ),
            "the boy said hello",
        )

    def test_error_rates_handle_english_and_chinese(self) -> None:
        ref_words = compare_asr_accuracy.word_tokens("hello robot")
        hyp_words = compare_asr_accuracy.word_tokens("hello small robot")
        self.assertAlmostEqual(
            compare_asr_accuracy.error_rate(ref_words, hyp_words),
            0.5,
        )

        ref_chars = compare_asr_accuracy.char_tokens("开放时间。")
        hyp_chars = compare_asr_accuracy.char_tokens("开放时间")
        self.assertEqual(compare_asr_accuracy.edit_distance(ref_chars, hyp_chars), 0)

    def test_manifest_resolves_relative_audio_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio = root / "sample.wav"
            audio.write_bytes(b"not real wav")
            manifest = root / "samples.jsonl"
            manifest.write_text(
                json.dumps(
                    {
                        "id": "sample",
                        "audio": "sample.wav",
                        "text": "hello",
                        "language": "en",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            samples = compare_asr_accuracy.read_manifest(manifest)

        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].sample_id, "sample")
        self.assertEqual(samples[0].audio_path, audio.resolve())
        self.assertEqual(samples[0].text, "hello")
        self.assertEqual(samples[0].language, "en")


if __name__ == "__main__":
    unittest.main()
