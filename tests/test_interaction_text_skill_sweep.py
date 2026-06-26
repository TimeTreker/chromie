from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.interaction_text_skill_sweep import (
    DEFAULT_CASES,
    TextSkillCase,
    _case_namespace,
    load_case_file,
    merge_cases,
    select_cases,
    uncovered_live_skills,
)


class InteractionTextSkillSweepTests(unittest.TestCase):
    def test_default_cases_cover_core_deterministic_text_skills(self) -> None:
        covered = {skill for case in DEFAULT_CASES for skill in case.expected_skills}

        self.assertIn("soridormi.walk_velocity", covered)
        self.assertIn("soridormi.curve_walk", covered)
        self.assertIn("soridormi.turn_in_place", covered)
        self.assertIn("soridormi.nod_yes", covered)
        self.assertIn("soridormi.shake_no", covered)
        self.assertIn("soridormi.blink_eyes", covered)

    def test_case_file_loads_expected_args(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cases.json"
            path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "custom_walk",
                                "text": "walk slowly",
                                "expected_skills": ["soridormi.walk_velocity"],
                                "expected_args": ["0:vx_mps=0.1"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            cases = load_case_file(path)

        self.assertEqual(cases[0].case_id, "custom_walk")
        self.assertEqual(cases[0].expected_args, ((0, "vx_mps", 0.1),))

    def test_select_cases_accepts_case_id_or_skill_id(self) -> None:
        cases = [
            TextSkillCase("walk", "walk", ("soridormi.walk_velocity",)),
            TextSkillCase("nod", "nod", ("soridormi.nod_yes",)),
        ]

        by_case = select_cases(cases, ["nod"])
        by_skill = select_cases(cases, ["soridormi.walk_velocity"])

        self.assertEqual([case.case_id for case in by_case], ["nod"])
        self.assertEqual([case.case_id for case in by_skill], ["walk"])

    def test_uncovered_live_skills_reports_missing_text_cases(self) -> None:
        cases = [
            TextSkillCase("walk", "walk", ("soridormi.walk_velocity",)),
        ]

        missing = uncovered_live_skills(
            cases,
            {"soridormi.walk_velocity", "soridormi.nod_yes"},
        )

        self.assertEqual(missing, ["soridormi.nod_yes"])

    def test_case_namespace_defaults_to_preview_and_headless(self) -> None:
        args = Namespace(
            router_url="http://router",
            agent_url="http://agent",
            soridormi_mcp_url="http://mcp",
            manifest=Path("capabilities/soridormi.json"),
            language="en-US",
            speaker=False,
            execute=False,
            allow_non_sim=False,
            auto_confirm_sim=True,
            require_speech=False,
            arg_tolerance=1e-6,
            timeout_s=90.0,
            skill_timeout_s=120.0,
        )
        case = TextSkillCase(
            "walk",
            "walk",
            ("soridormi.walk_velocity",),
            ((0, "vx_mps", 0.1),),
        )

        ns = _case_namespace(args, case, Path("/tmp/case"))

        self.assertTrue(ns.preview_only)
        self.assertFalse(ns.speaker)
        self.assertEqual(ns.expect_skill, ["soridormi.walk_velocity"])
        self.assertEqual(ns.expect_arg, [(0, "vx_mps", 0.1)])

    def test_merge_cases_replaces_default_by_id(self) -> None:
        base = (TextSkillCase("walk", "old", ("soridormi.walk_velocity",)),)
        replacement = TextSkillCase("walk", "new", ("soridormi.walk_velocity",))

        merged = merge_cases(base, [replacement])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].text, "new")


if __name__ == "__main__":
    unittest.main()
