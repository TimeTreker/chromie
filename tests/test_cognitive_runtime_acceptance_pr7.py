from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.cognitive_runtime_acceptance import (
    _events_report,
    _level_a_report,
    build_bundle,
    main,
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

    def test_bundle_requires_matching_run_provenance_for_target_validation(self):
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
                        "provenance": {
                            "chromie": {
                                "revision": "chromie-accepted",
                                "dirty": False,
                            },
                            "soridormi": {
                                "upstream_revision": "soridormi-accepted",
                                "checkout_revision": "soridormi-accepted",
                                "checkout_dirty": False,
                                "source_binding": "endpoint_reported_revision",
                                "endpoint_revision": "soridormi-accepted",
                            },
                            "semantic_runtime": {
                                "path": "goal_driven_cognitive_runtime",
                                "configured_cognitive_runtime_mode": "apply",
                                "cognitive_runtime_selected_for_route": True,
                            },
                        },
                        "cognitive_runtime": {"status": "applied"},
                        "execution": {
                            "status": "completed",
                            "results": [
                                {
                                    "skill_id": "soridormi.nod_yes",
                                    "status": "completed",
                                    "output": {"mode": "sim", "completed": True},
                                }
                            ],
                        },
                        "status_before": {
                            "mode": "sim",
                            "backend": "runtime",
                            "safe_idle": True,
                            "active_task": None,
                            "emergency_stop": False,
                            "fallen": False,
                        },
                        "status_after": {
                            "mode": "sim",
                            "backend": "runtime",
                            "safe_idle": True,
                            "active_task": None,
                            "emergency_stop": False,
                            "fallen": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            bundle = build_bundle(
                events_path=events,
                text_mujoco_summary=summary,
                expected_chromie_revision="chromie-accepted",
                expected_soridormi_revision="soridormi-accepted",
            )
            self.assertTrue(bundle["status_vocabulary"]["target_validated"])
            self.assertFalse(bundle["status_vocabulary"]["release_ready"])
            self.assertNotIn("chromie_revision", bundle)
            self.assertEqual(
                bundle["simulator"]["run_provenance"]["chromie_revision"],
                "chromie-accepted",
            )

            unsafe_payload = json.loads(summary.read_text(encoding="utf-8"))
            unsafe_payload["status_before"]["safe_idle"] = False
            unsafe_payload["status_before"]["active_task"] = {"plan_id": "stuck"}
            summary.write_text(json.dumps(unsafe_payload), encoding="utf-8")
            unsafe_bundle = build_bundle(
                events_path=events,
                text_mujoco_summary=summary,
                expected_chromie_revision="chromie-accepted",
                expected_soridormi_revision="soridormi-accepted",
            )
            self.assertFalse(
                unsafe_bundle["status_vocabulary"]["target_validated"],
                "an unsafe pre-run state must not be accepted as target evidence",
            )

    def test_retained_legacy_summary_is_not_relabelled_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "evidence_dir": tmp,
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
            bundle = build_bundle(
                events_path=None,
                text_mujoco_summary=summary,
                expected_chromie_revision="current-chromie",
                expected_soridormi_revision="current-soridormi",
            )
            self.assertFalse(bundle["status_vocabulary"]["target_validated"])
            self.assertIsNone(bundle["simulator"]["cognitive_status"])
            self.assertFalse(bundle["simulator"]["provenance_matches"])
            provenance_errors = "\n".join(
                bundle["simulator"]["provenance_errors"]
            )
            self.assertIn("declared paired Soridormi checkout", provenance_errors)
            self.assertIn("clean declared paired Soridormi checkout", provenance_errors)
            self.assertIn("safe-idle pre-run state", provenance_errors)
            self.assertIn("safe-idle post-run state", provenance_errors)

    def test_applied_run_with_stale_revision_is_not_target_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "provenance": {
                            "chromie": {
                                "revision": "old-chromie",
                                "dirty": False,
                            },
                            "soridormi": {
                                "upstream_revision": "current-soridormi",
                                "checkout_revision": "current-soridormi",
                                "checkout_dirty": False,
                                "source_binding": "endpoint_reported_revision",
                                "endpoint_revision": "current-soridormi",
                            },
                            "semantic_runtime": {
                                "path": "goal_driven_cognitive_runtime",
                                "configured_cognitive_runtime_mode": "apply",
                                "cognitive_runtime_selected_for_route": True,
                            },
                        },
                        "cognitive_runtime": {"status": "applied"},
                        "execution": {
                            "status": "completed",
                            "results": [
                                {
                                    "skill_id": "soridormi.nod_yes",
                                    "status": "completed",
                                    "output": {"mode": "sim", "completed": True},
                                }
                            ],
                        },
                        "status_before": {
                            "mode": "sim",
                            "backend": "runtime",
                            "safe_idle": True,
                            "active_task": None,
                            "emergency_stop": False,
                            "fallen": False,
                        },
                        "status_after": {
                            "mode": "sim",
                            "backend": "runtime",
                            "safe_idle": True,
                            "active_task": None,
                            "emergency_stop": False,
                            "fallen": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            bundle = build_bundle(
                events_path=None,
                text_mujoco_summary=summary,
                expected_chromie_revision="current-chromie",
                expected_soridormi_revision="current-soridormi",
            )
            self.assertFalse(bundle["status_vocabulary"]["target_validated"])
            self.assertIn(
                "does not match",
                bundle["simulator"]["provenance_errors"][0],
            )

    def test_bundle_cli_does_not_require_the_global_events_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.json"
            summary.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "provenance": {
                            "chromie": {"revision": "chromie", "dirty": False},
                            "soridormi": {
                                "upstream_revision": "soridormi",
                                "checkout_revision": "soridormi",
                                "checkout_dirty": False,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--mode",
                        "bundle",
                        "--text-mujoco-summary",
                        str(summary),
                        "--expected-chromie-revision",
                        "chromie",
                        "--expected-soridormi-revision",
                        "soridormi",
                    ]
                )
            self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
