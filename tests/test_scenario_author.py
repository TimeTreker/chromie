from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts import scenario_author
from scripts.behavior_scenarios import load_scenario_file


class ScenarioAuthorTests(unittest.TestCase):
    def test_new_creates_scenarios_from_templates(self) -> None:
        cases = (
            {
                "suite": "router",
                "scenario_id": "draft_greeting",
                "text": "Hello there.",
                "extra_args": [
                    "--description",
                    "Draft greeting.",
                    "--tag",
                    "normal",
                ],
            },
            {
                "suite": "dialogue",
                "scenario_id": "draft_dialogue",
                "text": "Hi Chromie.",
                "extra_args": [],
            },
        )

        for case in cases:
            with self.subTest(suite=case["suite"]), tempfile.TemporaryDirectory() as temp_dir:
                code = scenario_author.main(
                    [
                        "new",
                        "--suite",
                        case["suite"],
                        "--id",
                        case["scenario_id"],
                        "--text",
                        case["text"],
                        "--scenario-root",
                        temp_dir,
                        *case["extra_args"],
                    ]
                )
                path = (
                    Path(temp_dir)
                    / case["suite"]
                    / f"{case['scenario_id']}.json"
                )
                scenario = load_scenario_file(path)

                self.assertEqual(code, 0)
                self.assertEqual(scenario.scenario_id, case["scenario_id"])
                self.assertEqual(scenario.suite, case["suite"])
                if case["suite"] == "router":
                    self.assertEqual(scenario.text, case["text"])
                    self.assertEqual(scenario.tags, ("normal",))
                else:
                    self.assertEqual(scenario.turns[0]["ask"], case["text"])

    def test_new_rejects_invalid_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code = scenario_author.main(
                [
                    "new",
                    "--suite",
                    "router",
                    "--id",
                    "Bad-ID",
                    "--scenario-root",
                    temp_dir,
                ]
            )

        self.assertEqual(code, 2)

    def test_validate_all_discovers_created_interaction_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scenario_author.main(
                [
                    "new",
                    "--suite",
                    "interaction",
                    "--id",
                    "draft_chat",
                    "--text",
                    "Hi Chromie.",
                    "--scenario-root",
                    str(root),
                ]
            )

            code = scenario_author.main(
                [
                    "validate-all",
                    "--suite",
                    "interaction",
                    "--scenario-root",
                    str(root),
                ]
            )

        self.assertEqual(code, 0)

    def test_edit_dry_run_prints_editor_command_for_existing_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            scenario_author.main(
                [
                    "new",
                    "--suite",
                    "router",
                    "--id",
                    "draft_edit",
                    "--text",
                    "Hello Chromie.",
                    "--scenario-root",
                    str(root),
                ]
            )

            output = StringIO()
            with redirect_stdout(output):
                code = scenario_author.main(
                    [
                        "edit",
                        "--suite",
                        "router",
                        "--id",
                        "draft_edit",
                        "--scenario-root",
                        str(root),
                        "--editor",
                        "true",
                        "--dry-run",
                    ]
                )

        self.assertEqual(code, 0)
        self.assertIn("draft_edit.json", output.getvalue())

    def test_validate_reports_bad_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")

            code = scenario_author.main(["validate", str(path)])

        self.assertEqual(code, 1)

    def test_prompt_mentions_suite_specific_expectations(self) -> None:
        cases = (
            {
                "suite": "router",
                "count": "3",
                "focus": "normal greetings and ambiguous commands",
                "expected": (
                    "Generate 3 candidate JSON scenario files",
                    "deterministic expectations",
                    "scenarios/router/<id>.json",
                ),
            },
            {
                "suite": "dialogue",
                "count": "2",
                "focus": "follow-up task context",
                "expected": (
                    "turns[]",
                    "history_contains",
                    "extracted_memory_contains",
                    "scenarios/dialogue/<id>.json",
                ),
            },
        )

        for case in cases:
            with self.subTest(suite=case["suite"]):
                output = StringIO()
                with redirect_stdout(output):
                    code = scenario_author.main(
                        [
                            "prompt",
                            "--suite",
                            case["suite"],
                            "--count",
                            case["count"],
                            "--focus",
                            case["focus"],
                        ]
                    )

                self.assertEqual(code, 0)
                text = output.getvalue()
                for expected in case["expected"]:
                    self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
