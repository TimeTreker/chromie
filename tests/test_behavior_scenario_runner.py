from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import scenario_runner
from scripts.behavior_scenarios import (
    compare_reports,
    load_scenario_file,
    load_scenarios,
    run_scenarios_sync,
    write_report,
)


class BehaviorScenarioRunnerTests(unittest.TestCase):
    def test_loads_one_file_per_scenario_and_filters_by_suite_or_key(self) -> None:
        all_cases = load_scenarios()
        router_cases = load_scenarios(suites={"router"})
        adapter_cases = load_scenarios(suites={"adapter"})
        dialogue_cases = load_scenarios(suites={"dialogue"})
        selected = load_scenarios(only={"router/normal_greeting"})

        dialogue_keys = [case.key for case in dialogue_cases]

        self.assertEqual(len(all_cases), 353)
        self.assertEqual(len(adapter_cases), 4)
        self.assertEqual(len(router_cases), 17)
        self.assertEqual(len(dialogue_cases), 316)
        self.assertEqual(len(load_scenarios(suites={"interaction"})), 16)
        self.assertIn("dialogue/walk_then_followup_status", dialogue_keys)
        self.assertIn("dialogue/raw_joint_command_refusal", dialogue_keys)
        self.assertIn("dialogue/batch2_safety_117_walk_into_a_smoky_hallway", dialogue_keys)
        self.assertIn("dialogue/voice_log_20260630_planner_regression", dialogue_keys)
        self.assertIn("dialogue/daily_child_nearby_motion_hold", dialogue_keys)
        self.assertIn("dialogue/daily_power_cable_motion_hold", dialogue_keys)
        self.assertEqual([case.key for case in selected], ["router/normal_greeting"])
        for case in all_cases:
            self.assertEqual(case.path.stem, case.scenario_id)

    def test_scenario_file_rejects_multiple_or_mismatched_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "wrong_name.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "right_name",
                        "suite": "router",
                        "input": {"text": "hello"},
                        "expect": {"route": "chat"},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "file stem must match"):
                load_scenario_file(path)

    def test_report_compare_marks_improvements_and_regressions(self) -> None:
        baseline = {
            "cases": [
                {"key": "router/a", "ok": True},
                {"key": "router/b", "ok": False},
                {"key": "router/old", "ok": True},
            ]
        }
        current = {
            "cases": [
                {"key": "router/a", "ok": False},
                {"key": "router/b", "ok": True},
                {"key": "router/new", "ok": True},
            ]
        }

        comparison = compare_reports(current, baseline)

        self.assertEqual(comparison["regressions"], ["router/a"])
        self.assertEqual(comparison["improvements"], ["router/b"])
        self.assertEqual(comparison["new_cases"], ["router/new"])
        self.assertEqual(comparison["removed_cases"], ["router/old"])

    def test_cli_writes_json_report_for_selected_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code = scenario_runner.main(
                [
                    "--suite",
                    "router",
                    "--only",
                    "polite_stop",
                    "--report-dir",
                    temp_dir,
                ]
            )

            reports = list(Path(temp_dir).glob("*/summary.json"))

        self.assertEqual(code, 0)
        self.assertEqual(len(reports), 1)

    def test_dialogue_scenario_runs_turns_with_history_context(self) -> None:
        scenarios = load_scenarios(only={"dialogue/walk_then_followup_status"})

        report = run_scenarios_sync(scenarios)
        turns = report["cases"][0]["actual"]["turns"]

        self.assertTrue(report["ok"], report["cases"][0]["errors"])
        self.assertEqual(report["case_count"], 1)
        self.assertEqual([turn["id"] for turn in turns], ["walk_request", "followup_status"])
        self.assertIn("Walk forward slowly.", str(turns[1]["pre_context"]["history"]))
        self.assertIn("soridormi.walk_velocity", str(turns[1]["pre_context"]["session_memory"]))

    def test_dialogue_scenario_checks_extracted_memory_context(self) -> None:
        scenarios = load_scenarios(only={"dialogue/remember_tea_preference"})

        report = run_scenarios_sync(scenarios)
        turns = report["cases"][0]["actual"]["turns"]

        self.assertTrue(report["ok"], report["cases"][0]["errors"])
        self.assertIn(
            "Current task: Remember the user's tea preference",
            str(turns[1]["pre_context"]["session_memory"]["extracted_memory"]),
        )
        self.assertIn(
            "Remember the user's tea preference",
            turns[1]["pre_context"]["session_memory"]["memory_summary"],
        )

    def test_write_report_uses_timestamped_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_report({"ok": True, "cases": []}, report_dir=Path(temp_dir))

            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "summary.json")
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
