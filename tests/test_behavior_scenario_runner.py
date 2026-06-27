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
    write_report,
)


class BehaviorScenarioRunnerTests(unittest.TestCase):
    def test_loads_one_file_per_scenario_and_filters_by_suite_or_key(self) -> None:
        all_cases = load_scenarios()
        router_cases = load_scenarios(suites={"router"})
        selected = load_scenarios(only={"router/normal_greeting"})

        self.assertEqual(len(all_cases), 15)
        self.assertEqual(len(router_cases), 8)
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

    def test_write_report_uses_timestamped_summary_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_report({"ok": True, "cases": []}, report_dir=Path(temp_dir))

            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(path.name, "summary.json")
        self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
