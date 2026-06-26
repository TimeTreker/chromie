from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.interaction_text_scenario_suite import (
    DEFAULT_CASES,
    TextScenarioCase,
    _case_namespace,
    load_case_file,
    merge_cases,
    select_cases,
    validate_scenario_result,
)


class InteractionTextScenarioSuiteTests(unittest.TestCase):
    def test_default_cases_include_user_examples_and_core_behaviors(self) -> None:
        cases = {case.case_id: case for case in DEFAULT_CASES}

        self.assertEqual(
            cases["false_belief_sun_shape"].text,
            "I think the sun is not a round sphere, do you think so?",
        )
        self.assertEqual(
            cases["compliment_self_image"].text,
            "You look beautiful, don't you?",
        )
        self.assertTrue(cases["false_belief_sun_shape"].expect_no_skills)
        self.assertTrue(cases["compliment_self_image"].expect_no_skills)
        self.assertIn("compound_walk_head_eye", cases)
        self.assertIn("deep_thought_memory_plan", cases)
        self.assertIn("emergency_stop", cases)

    def test_case_file_loads_routes_speech_and_args(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cases.json"
            path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "custom_blink",
                                "text": "blink twice",
                                "expected_route": "robot_action",
                                "expected_skills": ["soridormi.blink_eyes"],
                                "expected_args": ["0:count=2"],
                                "expected_speech_any": ["blink", "eyes"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            cases = load_case_file(path)

        self.assertEqual(cases[0].case_id, "custom_blink")
        self.assertEqual(cases[0].expected_routes, ("robot_action",))
        self.assertEqual(cases[0].expected_skills, ("soridormi.blink_eyes",))
        self.assertEqual(cases[0].expected_args, ((0, "count", 2),))
        self.assertEqual(cases[0].expected_speech_any, ("blink", "eyes"))

    def test_validate_scenario_result_checks_route_speech_and_forbidden_skills(self) -> None:
        case = TextScenarioCase(
            case_id="sun",
            text="sun",
            expected_routes=("chat",),
            expected_speech_all=("sun",),
            expected_speech_any=("sphere", "round"),
            forbidden_skills=("soridormi.walk_velocity",),
        )
        summary = {
            "route": {"route": "chat"},
            "interaction_response": {
                "speech": [{"text": "The Sun is very close to a round sphere."}],
                "skills": [
                    {
                        "skill_id": "soridormi.express_attention",
                        "metadata": {"source": "expressive_body_cue"},
                    }
                ],
            },
        }

        self.assertEqual(validate_scenario_result(case, summary), [])

        bad_summary = {
            "route": {"route": "robot_action"},
            "interaction_response": {
                "speech": [{"text": "Moving."}],
                "skills": [{"skill_id": "soridormi.walk_velocity"}],
            },
        }

        errors = validate_scenario_result(case, bad_summary)
        self.assertTrue(any("route=" in item for item in errors))
        self.assertTrue(any("speech missing required" in item for item in errors))
        self.assertTrue(any("forbidden skills" in item for item in errors))

    def test_validate_scenario_result_ignores_expressive_cues_only(self) -> None:
        case = TextScenarioCase(
            case_id="chat",
            text="hello",
            expected_routes=("chat",),
            expect_no_skills=True,
        )
        summary = {
            "route": {"route": "chat"},
            "interaction_response": {
                "speech": [{"text": "Hello."}],
                "skills": [
                    {
                        "skill_id": "soridormi.express_attention",
                        "metadata": {"source": "expressive_body_cue"},
                    },
                    {"skill_id": "soridormi.walk_velocity", "metadata": {}},
                ],
            },
        }

        errors = validate_scenario_result(case, summary)

        self.assertTrue(any("walk_velocity" in item for item in errors))
        self.assertFalse(any("express_attention" in item for item in errors))

    def test_select_and_merge_cases(self) -> None:
        base = (TextScenarioCase("a", "old"), TextScenarioCase("b", "bee"))
        replacement = TextScenarioCase("a", "new")

        merged = merge_cases(base, [replacement])
        selected = select_cases(merged, ["a"])

        self.assertEqual(len(merged), 2)
        self.assertEqual(selected, [replacement])
        with self.assertRaisesRegex(ValueError, "unknown scenario id"):
            select_cases(merged, ["missing"])

    def test_case_namespace_defaults_to_preview_headless_and_uses_single_route_assertion(self) -> None:
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
            arg_tolerance=1e-6,
            timeout_s=90.0,
            skill_timeout_s=120.0,
        )
        case = TextScenarioCase(
            "chat",
            "hello",
            expected_routes=("chat",),
            expect_no_skills=True,
            allow_expressive_cues=False,
            require_speech=True,
        )

        ns = _case_namespace(args, case, Path("/tmp/case"))

        self.assertTrue(ns.preview_only)
        self.assertFalse(ns.speaker)
        self.assertEqual(ns.expect_route, "chat")
        self.assertTrue(ns.expect_no_skills)
        self.assertTrue(ns.require_speech)


if __name__ == "__main__":
    unittest.main()
