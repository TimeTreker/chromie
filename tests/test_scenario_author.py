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
    def test_new_creates_router_scenario_from_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code = scenario_author.main(
                [
                    "new",
                    "--suite",
                    "router",
                    "--id",
                    "draft_greeting",
                    "--text",
                    "Hello there.",
                    "--description",
                    "Draft greeting.",
                    "--tag",
                    "normal",
                    "--scenario-root",
                    temp_dir,
                ]
            )
            path = Path(temp_dir) / "router" / "draft_greeting.json"
            scenario = load_scenario_file(path)

        self.assertEqual(code, 0)
        self.assertEqual(scenario.scenario_id, "draft_greeting")
        self.assertEqual(scenario.text, "Hello there.")
        self.assertEqual(scenario.tags, ("normal",))

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

    def test_prompt_mentions_deterministic_expectations_and_suite(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            code = scenario_author.main(
                [
                    "prompt",
                    "--suite",
                    "router",
                    "--count",
                    "3",
                    "--focus",
                    "normal greetings and ambiguous commands",
                ]
            )

        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn("Generate 3 candidate JSON scenario files", text)
        self.assertIn("deterministic expectations", text)
        self.assertIn("scenarios/router/<id>.json", text)


if __name__ == "__main__":
    unittest.main()
