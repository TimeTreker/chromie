from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from scripts.closed_loop_e2e import (
    AudioData,
    ClosedLoopCase,
    closed_loop_review_bundle,
    expected_term_result,
    parse_cases,
    primary_error,
    resample_pcm16,
    transcript_metrics,
    trim_silence,
)


class ClosedLoopE2ETests(unittest.TestCase):
    def test_manifest_supports_chinese_and_english_cases(self) -> None:
        payload = {
            "transport_cases": [
                {
                    "id": "zh",
                    "language": "zh-CN",
                    "text": "你好",
                    "speaker_id": "chromie_zh",
                },
                {
                    "id": "en",
                    "language": "en-US",
                    "text": "Hello",
                    "speaker_id": "chromie_en",
                },
            ]
        }
        cases = parse_cases(payload, "transport_cases")
        self.assertEqual([case.case_id for case in cases], ["zh", "en"])
        self.assertEqual(cases[0].speaker_id, "chromie_zh")
        self.assertEqual(cases[1].speaker_id, "chromie_en")

    def test_primary_error_uses_cer_for_chinese_and_wer_for_english(self) -> None:
        self.assertEqual(primary_error("zh-CN", "你好", "你好")[0], "cer")
        self.assertEqual(primary_error("en-US", "hello there", "hello there")[0], "wer")

    def test_transcript_metrics_ignore_case_and_punctuation(self) -> None:
        metrics = transcript_metrics(
            "en-US",
            "Hello, Chromie!",
            "hello chromie",
        )
        self.assertEqual(metrics["error_rate"], 0.0)
        zh_metrics = transcript_metrics("zh-CN", "你好，Chromie！", "你好 chromie")
        self.assertEqual(zh_metrics["error_rate"], 0.0)

    def test_expected_terms_are_semantic_output_checks_not_asr_rules(self) -> None:
        case = ClosedLoopCase(
            case_id="family",
            language="en-US",
            text="question",
            speaker_id="chromie_en",
            max_error_rate=0.4,
            expected_any=("help", "organize"),
            expected_all=("family",),
        )
        self.assertTrue(
            expected_term_result(case, "I help my family organize things.")["passed"]
        )
        self.assertFalse(expected_term_result(case, "I like the weather.")["passed"])

    def test_hybrid_workflow_does_not_use_phrase_matching_as_semantic_truth(self) -> None:
        case = ClosedLoopCase(
            case_id="family",
            language="en-US",
            text="question",
            speaker_id="chromie_en",
            max_error_rate=0.4,
            expected_any=("help",),
            oracle_mode="hybrid",
            deterministic_sources=("audio_transport",),
            primary_outcomes=("Answer how Chromie helps her family",),
            semantic_dimensions=("intent_understanding",),
        )
        result = expected_term_result(case, "Any natural answer is reviewed later.")
        self.assertTrue(result["passed"])
        self.assertFalse(result["applied"])

    def test_resample_pcm16_changes_sample_count(self) -> None:
        source_rate = 24000
        samples = np.arange(source_rate, dtype=np.int16)
        pcm = resample_pcm16(AudioData(samples.tobytes(), source_rate), 16000)
        self.assertEqual(len(pcm) // 2, 16000)

    def test_trim_silence_retains_active_audio_with_padding(self) -> None:
        rate = 16000
        silence = np.zeros(rate, dtype=np.int16)
        tone = np.full(rate // 2, 2000, dtype=np.int16)
        audio = AudioData(np.concatenate([silence, tone, silence]).tobytes(), rate)
        trimmed = trim_silence(audio)
        self.assertGreater(len(trimmed.pcm16), len(tone.tobytes()))
        self.assertLess(len(trimmed.pcm16), len(audio.pcm16))

    def test_default_manifest_exists_and_is_bilingual(self) -> None:
        path = Path("benchmarks/manifests/closed_loop_e2e_v1.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        languages = {
            row["language"].split("-", 1)[0]
            for key in ("transport_cases", "workflow_cases")
            for row in payload[key]
        }
        self.assertEqual(languages, {"zh", "en"})
        self.assertTrue(
            all(
                row["oracle_policy"]["mode"] == "deterministic"
                for row in payload["transport_cases"]
            )
        )
        self.assertTrue(
            all(
                row["oracle_policy"]["mode"] == "hybrid"
                for row in payload["workflow_cases"]
            )
        )
        self.assertTrue(
            all("expected_any" not in row for row in payload["workflow_cases"])
        )

    def test_closed_loop_review_bundle_uses_external_semantic_review(self) -> None:
        case = ClosedLoopCase(
            case_id="family",
            language="en-US",
            text="How do you help?",
            speaker_id="chromie_en",
            max_error_rate=0.4,
            oracle_mode="hybrid",
            deterministic_sources=("audio_transport",),
            primary_outcomes=("Answer how Chromie helps her family",),
            semantic_dimensions=("intent_understanding", "naturalness"),
            review_rubric={"dimensions": ["intent_understanding", "naturalness"]},
        )
        bundle = closed_loop_review_bundle(
            [case],
            [
                {
                    "id": "family",
                    "status": "review",
                    "mechanical_passed": True,
                    "semantic_review_required": True,
                    "oracle_policy": {
                        "mode": "hybrid",
                        "deterministic_sources": ["audio_transport"],
                        "semantic_dimensions": ["intent_understanding", "naturalness"],
                        "semantic_blocking": True,
                    },
                    "delivered_text": "I help my family remember and organize things.",
                    "delivered_speech_events": [{"text": "I help my family."}],
                    "captured_transcript": "I help my family.",
                    "metrics": {"wer": 0.0},
                    "audio_passed": True,
                    "artifacts": ["result.json"],
                    "error": None,
                }
            ],
        )
        self.assertEqual(bundle["scenarios"][0]["review_reason"], "semantic_adjudication")
        self.assertEqual(
            bundle["scenarios"][0]["review_request"]["semantic_dimensions"],
            ["intent_understanding", "naturalness"],
        )


if __name__ == "__main__":
    unittest.main()
