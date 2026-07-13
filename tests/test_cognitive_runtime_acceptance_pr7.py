from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.cognitive_runtime_acceptance import (
    _events_report,
    _level_a_report,
    build_bundle,
)


class CognitiveRuntimeAcceptanceTests(unittest.TestCase):
    def test_level_a_scenarios_pass(self):
        report = _level_a_report()
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["case_count"], 4)

    def test_events_summary_keeps_evidence_class_separate(self):
        report = _events_report(
            [
                {
                    "mode": "apply",
                    "status": "applied",
                    "lane": "robot_action",
                    "timings_ms": {"total": 123.4},
                    "interaction": {"skill_ids": ["soridormi.blink_eyes"]},
                }
            ]
        )
        self.assertEqual(report["evidence_class"], "live_text_operational")
        self.assertEqual(report["status_counts"]["applied"], 1)
        self.assertEqual(report["applied_skill_ids"], ["soridormi.blink_eyes"])

    def test_bundle_never_declares_release_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            events.write_text(
                json.dumps(
                    {
                        "mode": "apply",
                        "status": "applied",
                        "lane": "chat",
                        "timings_ms": {"total": 10},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            summary = Path(tmp) / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "evidence_dir": tmp,
                        "cognitive_runtime": {"status": "applied"},
                        "execution": {"status": "completed"},
                        "status_after": {
                            "active_task": None,
                            "emergency_stop": False,
                            "fallen": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            bundle = build_bundle(events_path=events, text_mujoco_summary=summary)
            self.assertTrue(bundle["status_vocabulary"]["target_validated"])
            self.assertFalse(bundle["status_vocabulary"]["release_ready"])


if __name__ == "__main__":
    unittest.main()
