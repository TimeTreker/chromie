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
        goal_interpretation_cases = load_scenarios(suites={"goal_interpretation"})
        cognitive_core_dialogue_cases = load_scenarios(suites={"cognitive_core_dialogue"})
        cognitive_turn_loop_cases = load_scenarios(
            suites={"cognitive_turn_loop"}
        )
        selected = load_scenarios(only={"goal_interpretation/goal_interpretation_normal_greeting"})

        self.assertEqual(len(all_cases), 52)
        self.assertEqual(len(goal_interpretation_cases), 28)
        self.assertEqual(len(cognitive_core_dialogue_cases), 3)
        cognitive_cases = load_scenarios(suites={"cognitive_runtime"})
        self.assertEqual(len(cognitive_cases), 15)
        self.assertEqual(len(cognitive_turn_loop_cases), 6)
        self.assertIn(
            "cognitive_turn_loop/active_stop_cancel_retains_outcome",
            [case.key for case in cognitive_turn_loop_cases],
        )
        self.assertIn(
            "cognitive_runtime/chat_turn_cannot_replay_completed_motion",
            [case.key for case in cognitive_cases],
        )
        self.assertIn(
            "cognitive_runtime/qualified_vocal_provider_exact_recitation",
            [case.key for case in cognitive_cases],
        )
        self.assertIn(
            "cognitive_runtime/qualified_media_walk_parallel",
            [case.key for case in cognitive_cases],
        )
        self.assertIn(
            "goal_interpretation/weather_check",
            [case.key for case in goal_interpretation_cases],
        )
        self.assertEqual([case.key for case in selected], ["goal_interpretation/goal_interpretation_normal_greeting"])
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
                        "suite": "goal_interpretation",
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
                {"key": "goal_interpretation/a", "ok": True},
                {"key": "goal_interpretation/b", "ok": False},
                {"key": "goal_interpretation/old", "ok": True},
            ]
        }
        current = {
            "cases": [
                {"key": "goal_interpretation/a", "ok": False},
                {"key": "goal_interpretation/b", "ok": True},
                {"key": "goal_interpretation/new", "ok": True},
            ]
        }

        comparison = compare_reports(current, baseline)

        self.assertEqual(comparison["regressions"], ["goal_interpretation/a"])
        self.assertEqual(comparison["improvements"], ["goal_interpretation/b"])
        self.assertEqual(comparison["new_cases"], ["goal_interpretation/new"])
        self.assertEqual(comparison["removed_cases"], ["goal_interpretation/old"])

    def test_cli_writes_json_report_for_selected_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code = scenario_runner.main(
                [
                    "--suite",
                    "goal_interpretation",
                    "--only",
                    "weather_check",
                    "--report-dir",
                    temp_dir,
                ]
            )

            reports = list(Path(temp_dir).glob("*/summary.json"))

        self.assertEqual(code, 0)
        self.assertEqual(len(reports), 1)

    def test_cognitive_core_dialogue_replays_weather_then_repeated_walk(self) -> None:
        scenarios = load_scenarios(
            only={"cognitive_core_dialogue/weather_then_repeated_walk_stays_grounded"}
        )

        report = run_scenarios_sync(scenarios)
        turns = report["cases"][0]["actual"]["turns"]

        self.assertTrue(report["ok"], report["cases"][0]["errors"])
        self.assertEqual(
            turns[1]["llm_stages"],
            ["goal_interpretation"],
        )
        self.assertEqual(
            turns[2]["interpretation"]["responsibilities"][0]["bindings"],
            {"direction": "forward", "duration_s": 15, "pace": "quickly"},
        )
        self.assertIn(
            "What is the weather in Beijing today?",
            str(turns[1]["pre_context"]["history"]),
        )

    def test_goal_interpretation_scenario_preserves_direct_weather_question(self) -> None:
        scenarios = load_scenarios(
            only={"goal_interpretation/inactive_direct_weather_question_false_addressedness"}
        )

        report = run_scenarios_sync(scenarios)
        actual = report["cases"][0]["actual"]

        self.assertTrue(report["ok"], report["cases"][0]["errors"])
        self.assertEqual(actual["responsibilities"][0]["bindings"]["location"], "北京")
        self.assertEqual(
            actual["llm_stages"],
            ["goal_interpretation"],
        )

    def test_cognitive_turn_loop_retains_outcomes_and_suppresses_unsafe_speech(
        self,
    ) -> None:
        scenarios = load_scenarios(suites={"cognitive_turn_loop"})

        report = run_scenarios_sync(scenarios)
        cases = {case["id"]: case for case in report["cases"]}

        self.assertTrue(report["ok"], report["cases"])
        self.assertEqual(report["case_count"], 6)
        self.assertEqual(report["passed"], 6)
        self.assertEqual(
            cases["admitted_mixed_completed_not_run_final"]["actual"][
                "evidence_statuses"
            ],
            ["completed", "not_run"],
        )
        self.assertEqual(
            cases["schema_unavailable_output_not_spoken"]["actual"][
                "observation_statuses"
            ],
            ["schema_unavailable"],
        )
        self.assertTrue(
            cases["newer_turn_suppresses_stale_final"]["actual"][
                "final_response_absent"
            ]
        )
        self.assertEqual(
            cases["active_stop_cancel_retains_outcome"]["actual"][
                "provider_cancelled_step_ids"
            ],
            ["active-first"],
        )

    def test_write_report_uses_timestamped_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_report({"ok": True, "cases": []}, report_dir=Path(temp_dir))

            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "summary.json")
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
