from __future__ import annotations

import unittest

from scripts.router_regression import (
    candidate_capabilities,
    evaluate_case,
    selected_capabilities,
)


class RouterRegressionEvaluatorTests(unittest.TestCase):
    def test_extracts_single_capability_from_intent(self) -> None:
        response = {"intent": "capability:soridormi.walk_velocity", "actions": []}
        self.assertEqual(selected_capabilities(response), ["soridormi.walk_velocity"])

    def test_actions_define_compound_execution_order(self) -> None:
        response = {
            "intent": "compound_robot_action",
            "actions": [
                {"capability_id": "soridormi.walk_velocity"},
                {"skill_id": "soridormi.turn_in_place"},
                {"intent": "capability:soridormi.nod_yes"},
            ],
        }
        self.assertEqual(
            selected_capabilities(response),
            [
                "soridormi.walk_velocity",
                "soridormi.turn_in_place",
                "soridormi.nod_yes",
            ],
        )

    def test_candidate_ids_are_not_treated_as_selections(self) -> None:
        response = {
            "intent": "general_conversation",
            "candidate_capabilities": [
                {"capability_id": "soridormi.walk_velocity"},
                {"capability_id": "soridormi.nod_yes"},
            ],
        }
        self.assertEqual(selected_capabilities(response), [])
        self.assertEqual(
            candidate_capabilities(response),
            ["soridormi.walk_velocity", "soridormi.nod_yes"],
        )

    def test_single_capability_case_passes(self) -> None:
        case = {
            "id": "walk",
            "expected_route": "robot_action",
            "expected_capabilities": ["soridormi.walk_velocity"],
            "required_candidates": ["soridormi.walk_velocity"],
        }
        response = {
            "route": "robot_action",
            "intent": "capability:soridormi.walk_velocity",
            "actions": [],
            "candidate_capabilities": [
                {"capability_id": "soridormi.walk_velocity"}
            ],
        }
        self.assertTrue(evaluate_case(case, response).passed)

    def test_wrong_single_capability_fails(self) -> None:
        case = {
            "id": "walk",
            "expected_route": "robot_action",
            "expected_capabilities": ["soridormi.walk_velocity"],
        }
        response = {
            "route": "robot_action",
            "intent": "capability:soridormi.curve_walk",
            "actions": [],
        }
        result = evaluate_case(case, response)
        self.assertFalse(result.passed)
        self.assertIn("selected capabilities", result.reasons[0])

    def test_compound_case_rejects_single_intent(self) -> None:
        case = {
            "id": "compound",
            "expected_route": "robot_action",
            "expected_capabilities": [
                "soridormi.walk_velocity",
                "soridormi.turn_in_place",
                "soridormi.nod_yes",
            ],
            "require_ordered_actions": True,
        }
        response = {
            "route": "robot_action",
            "intent": "capability:soridormi.nod_yes",
            "actions": [],
        }
        result = evaluate_case(case, response)
        self.assertFalse(result.passed)
        self.assertTrue(any("non-empty actions list" in reason for reason in result.reasons))

    def test_compound_case_accepts_exact_ordered_actions(self) -> None:
        case = {
            "id": "compound",
            "expected_route": "robot_action",
            "expected_capabilities": [
                "soridormi.walk_velocity",
                "soridormi.turn_in_place",
                "soridormi.nod_yes",
            ],
            "required_candidates": [
                "soridormi.walk_velocity",
                "soridormi.turn_in_place",
                "soridormi.nod_yes",
            ],
            "require_ordered_actions": True,
        }
        response = {
            "route": "robot_action",
            "intent": "compound_robot_action",
            "actions": [
                {"capability_id": "soridormi.walk_velocity"},
                {"capability_id": "soridormi.turn_in_place"},
                {"capability_id": "soridormi.nod_yes"},
            ],
            "candidate_capabilities": [
                {"capability_id": "soridormi.walk_velocity"},
                {"capability_id": "soridormi.turn_in_place"},
                {"capability_id": "soridormi.nod_yes"},
            ],
        }
        self.assertTrue(evaluate_case(case, response).passed)


if __name__ == "__main__":
    unittest.main()
