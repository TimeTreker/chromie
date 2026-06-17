from __future__ import annotations

import argparse
import unittest

from router.app.schema import RouteDecision
from scripts.interaction_text_mujoco_check import (
    _apply_soridormi_skill_timeout,
    parse_expected_arg,
    safe_idle_errors,
    validate_contract,
)
from shared.chromie_contracts.interaction import InteractionResponse


class InteractionTextMujocoCheckTests(unittest.TestCase):
    def test_parse_expected_arg_accepts_json_scalars(self) -> None:
        self.assertEqual(parse_expected_arg("0:vx_mps=0.2"), (0, "vx_mps", 0.2))
        self.assertEqual(parse_expected_arg("1:count=2"), (1, "count", 2))
        self.assertEqual(parse_expected_arg("2:label=left"), (2, "label", "left"))

    def test_parse_expected_arg_rejects_bad_shape(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_expected_arg("vx_mps=0.2")

    def test_validate_contract_checks_ordered_skills_and_args(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "robot_action",
                "intent": "compound_robot_action",
                "confidence": 0.99,
                "language": "en-US",
                "source": "catalog",
                "actions": [
                    {
                        "capability_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                    },
                    {
                        "capability_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                    },
                    {
                        "capability_id": "soridormi.turn_in_place",
                        "args": {"yaw_radps": -0.12},
                    },
                ],
            }
        )
        response = InteractionResponse.model_validate(
            {
                "skills": [
                    {
                        "skill_id": "soridormi.walk_velocity",
                        "args": {
                            "vx_mps": 0.2,
                            "vy_mps": 0.0,
                            "yaw_radps": 0.0,
                            "duration_s": 10.0,
                        },
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "soridormi.turn_in_place",
                        "args": {"yaw_radps": -0.12},
                        "timing": "sequential",
                    },
                ]
            }
        )

        errors = validate_contract(
            route=route,
            response=response,
            expected_skills=[
                "soridormi.walk_velocity",
                "soridormi.nod_yes",
                "soridormi.turn_in_place",
            ],
            expected_args=[
                (0, "vx_mps", 0.2),
                (0, "duration_s", 10.0),
                (1, "count", 2),
                (2, "yaw_radps", -0.12),
            ],
            arg_tolerance=1e-6,
        )

        self.assertEqual(errors, [])

    def test_validate_contract_reports_mismatch(self) -> None:
        route = RouteDecision.model_validate(
            {
                "route": "chat",
                "intent": "general_conversation",
                "confidence": 0.5,
                "language": "en-US",
                "source": "fallback",
            }
        )
        response = InteractionResponse()

        errors = validate_contract(
            route=route,
            response=response,
            expected_skills=["soridormi.walk_velocity"],
            expected_args=[(0, "vx_mps", 0.2)],
            arg_tolerance=1e-6,
        )

        self.assertGreaterEqual(len(errors), 3)
        self.assertTrue(any("route=" in item for item in errors))
        self.assertTrue(any("interaction skills mismatch" in item for item in errors))

    def test_safe_idle_errors_require_idle_non_emergency_status(self) -> None:
        self.assertEqual(
            safe_idle_errors(
                {
                    "active_task": None,
                    "emergency_stop": False,
                    "fallen": False,
                }
            ),
            [],
        )
        self.assertEqual(
            len(
                safe_idle_errors(
                    {
                        "active_task": {"plan_id": "x"},
                        "emergency_stop": True,
                        "fallen": True,
                    }
                )
            ),
            3,
        )

    def test_apply_soridormi_timeout_sets_request_timeouts(self) -> None:
        response = InteractionResponse.model_validate(
            {
                "skills": [
                    {
                        "skill_id": "soridormi.walk_velocity",
                        "args": {"vx_mps": 0.2, "duration_s": 10.0},
                        "timing": "sequential",
                    },
                    {
                        "skill_id": "chromie.unrelated",
                        "args": {},
                        "timing": "sequential",
                        "timeout_ms": 1000,
                    },
                ]
            }
        )

        updated = _apply_soridormi_skill_timeout(response, 120.0)

        self.assertEqual(updated.skills[0].timeout_ms, 120000)
        self.assertEqual(updated.skills[1].timeout_ms, 1000)


if __name__ == "__main__":
    unittest.main()
