from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from scripts.closed_loop_e2e import (
    AudioData,
    ClosedLoopCase,
    PipeWireMonitorCapture,
    _source_tree_digest,
    collect_debug_bundle,
    closed_loop_review_bundle,
    expected_term_result,
    parse_cases,
    primary_error,
    resample_pcm16,
    transcript_metrics,
    trim_silence,
    wait_for_agent_health,
    workflow_input_channel,
)


class ClosedLoopE2ETests(unittest.TestCase):
    def test_agent_readiness_retries_until_health_is_confirmed(self) -> None:
        class HealthResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return b'{"ok": true, "service": "chromie-agent"}'

        with patch(
            "scripts.closed_loop_e2e.urllib.request.urlopen",
            side_effect=[ConnectionResetError("warming"), HealthResponse()],
        ) as urlopen:
            with patch("scripts.closed_loop_e2e.time.sleep") as sleep:
                payload = wait_for_agent_health(
                    "http://127.0.0.1:8092",
                    timeout_s=5.0,
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1.0)

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

    def test_manifest_supports_multi_turn_workflow_cases(self) -> None:
        payload = {
            "workflow_cases": [
                {
                    "id": "memory",
                    "language": "en-US",
                    "turns": [
                        "Remember that my test color is blue.",
                        "What test color did I say?",
                    ],
                    "speaker_id": "chromie_en",
                    "oracle_policy": {
                        "mode": "hybrid",
                        "deterministic_sources": ["turn_completion"],
                        "semantic_dimensions": ["memory_recall"],
                    },
                }
            ]
        }
        case = parse_cases(payload, "workflow_cases")[0]
        self.assertEqual(
            case.user_turns(),
            (
                "Remember that my test color is blue.",
                "What test color did I say?",
            ),
        )
        self.assertEqual(case.text, "Remember that my test color is blue.")

    def test_daily_voice_manifest_references_canonical_scenarios(self) -> None:
        manifest_path = Path("benchmarks/manifests/daily_life_voice_e2e_v1.json")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        cases = parse_cases(
            payload,
            "workflow_cases",
            manifest_path=manifest_path,
        )
        self.assertEqual(len(cases), 16)
        self.assertEqual(
            {case.language.split("-", 1)[0] for case in cases},
            {"en", "zh"},
        )
        self.assertTrue(all(case.datasets == ("daily_conversation",) for case in cases))
        self.assertTrue(all(case.source_path.endswith(".json") for case in cases))
        self.assertTrue(all(case.primary_outcomes for case in cases))
        self.assertTrue(all(case.forbidden_behaviors for case in cases))
        self.assertTrue(any(len(case.user_turns()) > 1 for case in cases))

    def test_scenario_reference_rejects_semantic_overrides(self) -> None:
        payload = {
            "workflow_cases": [
                {
                    "scenario_path": (
                        "benchmarks/datasets/daily_conversation/scenarios/"
                        "family_home/washing_machine_status.json"
                    ),
                    "primary_outcomes": ["weaken the canonical expectation"],
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "semantic overrides"):
            parse_cases(payload, "workflow_cases")

    def test_primary_error_uses_cer_for_chinese_and_wer_for_english(self) -> None:
        self.assertEqual(primary_error("zh-CN", "你好", "你好")[0], "cer")
        self.assertEqual(primary_error("en-US", "hello there", "hello there")[0], "wer")

    def test_generated_voice_routes_as_a_final_asr_input(self) -> None:
        self.assertEqual(workflow_input_channel("tts-asr"), "voice")
        self.assertEqual(workflow_input_channel("text"), "text")

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

    def test_pipewire_monitor_resolves_default_sink_serial(self) -> None:
        inspected = """id 66, type PipeWire:Interface:Node
  * media.class = \"Audio/Sink\"
  * object.serial = \"95\"
"""
        with patch.object(PipeWireMonitorCapture, "available", return_value=True):
            with patch(
                "scripts.closed_loop_e2e.subprocess.check_output",
                return_value=inspected,
            ):
                self.assertEqual(PipeWireMonitorCapture.discover_target(), "95")

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
        self.assertGreaterEqual(len(payload["workflow_cases"]), 12)
        workflow_ids = {row["id"] for row in payload["workflow_cases"]}
        self.assertIn("en_session_memory_recall", workflow_ids)
        self.assertIn("zh_weather_followup", workflow_ids)
        self.assertIn("en_weather_correction", workflow_ids)
        self.assertIn("zh_long_ordered_playback", workflow_ids)
        self.assertTrue(
            any(len(row.get("turns", [])) > 1 for row in payload["workflow_cases"])
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
        normalized = bundle["scenarios"][0]["scenario"]
        self.assertEqual(normalized["inputs"]["turns"], ["How do you help?"])

    def test_daily_review_bundle_retains_canonical_behavior_boundaries(self) -> None:
        manifest_path = Path("benchmarks/manifests/daily_life_voice_e2e_v1.json")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        case = parse_cases(
            payload,
            "workflow_cases",
            manifest_path=manifest_path,
        )[0]
        bundle = closed_loop_review_bundle(
            [case],
            [
                {
                    "id": case.case_id,
                    "status": "review",
                    "mechanical_passed": True,
                    "semantic_review_required": True,
                    "workflow_input": "tts-asr",
                    "input_audio_passed": True,
                    "input_audio": [{"passed": True}],
                    "oracle_policy": {
                        "mode": case.oracle_mode,
                        "deterministic_sources": list(case.deterministic_sources),
                        "semantic_dimensions": list(case.semantic_dimensions),
                        "semantic_blocking": True,
                    },
                    "delivered_text": "I do not have evidence that Grandpa arrived.",
                    "delivered_speech_events": [{"text": "I do not know yet."}],
                    "captured_transcript": "I do not know yet.",
                    "metrics": {"cer": 0.0},
                    "audio_passed": True,
                    "artifacts": ["result.json"],
                    "error": None,
                }
            ],
        )
        normalized = bundle["scenarios"][0]["scenario"]
        self.assertEqual(normalized["datasets"], ["daily_conversation"])
        self.assertEqual(normalized["source"]["path"], case.source_path)
        self.assertEqual(
            normalized["expectations"]["forbidden_behaviors"],
            list(case.forbidden_behaviors),
        )

    def test_debug_bundle_is_collected_once_and_retained_in_run_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch("scripts.closed_loop_e2e.subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = (
                    "Debug bundle created:\n/tmp/chromie_debug_bundle.tar.gz\n"
                )
                run.return_value.stderr = ""
                result = collect_debug_bundle(output_dir)
            run.assert_called_once()
            self.assertTrue(result["succeeded"])
            self.assertEqual(
                result["archive"],
                "/tmp/chromie_debug_bundle.tar.gz",
            )
            self.assertTrue(Path(result["stdout"]).exists())

    def test_source_tree_digest_is_content_and_path_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (first / "module.py").write_text("value = 1\n", encoding="utf-8")
            (second / "contract.py").write_text("name = 'x'\n", encoding="utf-8")
            initial = _source_tree_digest(((first, "app"), (second, "contracts")))
            (first / "module.py").write_text("value = 2\n", encoding="utf-8")
            changed = _source_tree_digest(((first, "app"), (second, "contracts")))
            self.assertNotEqual(initial, changed)


if __name__ == "__main__":
    unittest.main()
