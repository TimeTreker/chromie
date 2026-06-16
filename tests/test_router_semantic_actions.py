from __future__ import annotations

import unittest

from router.app.capability_catalog import CapabilityCatalogResult
from router.app.schema import RouteRequest
from router.app.semantic_actions import semantic_robot_decision


def _result(*ids: str) -> CapabilityCatalogResult:
    return CapabilityCatalogResult(
        query="test",
        matched=True,
        suggested_route="robot_action",
        suggested_agents=["capability_agent", "safety_agent", "speaker_agent"],
        catalog_version=2,
        matches=[
            {
                "capability_id": capability_id,
                "available": True,
                "interaction_executable": True,
                "score": 0.5,
            }
            for capability_id in ids
        ],
    )


class RouterSemanticActionTests(unittest.TestCase):
    def test_straight_walk_does_not_choose_curve_walk(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk forward at 0.15 speed for five seconds."),
            _result("soridormi.curve_walk", "soridormi.walk_velocity"),
        )
        assert decision is not None
        self.assertEqual(decision.intent, "capability:soridormi.walk_velocity")
        self.assertEqual(decision.actions[0]["args"]["vx_mps"], 0.15)
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 5.0)
        self.assertEqual(decision.actions[0]["args"]["yaw_radps"], 0.0)

    def test_curve_word_is_required_for_curve_walk(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk in a curve to the left for 3 seconds."),
            _result("soridormi.curve_walk", "soridormi.walk_velocity"),
        )
        assert decision is not None
        self.assertEqual(decision.actions[0]["capability_id"], "soridormi.curve_walk")
        self.assertEqual(decision.actions[0]["args"]["yaw_radps"], -0.1)

    def test_compound_command_preserves_order_and_arguments(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(
                text="Walk forward for 10s and then turn left and then nod head twice."
            ),
            _result(
                "soridormi.walk_velocity",
                "soridormi.turn_in_place",
                "soridormi.nod_yes",
            ),
        )
        assert decision is not None
        self.assertEqual(decision.intent, "compound_robot_action")
        self.assertEqual(
            [item["capability_id"] for item in decision.actions],
            [
                "soridormi.walk_velocity",
                "soridormi.turn_in_place",
                "soridormi.nod_yes",
            ],
        )
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 10.0)
        self.assertEqual(decision.actions[1]["args"]["yaw_radps"], -0.12)
        self.assertEqual(decision.actions[2]["args"]["count"], 2)

    def test_unknown_segment_does_not_partially_execute(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk forward and then make coffee."),
            _result("soridormi.walk_velocity"),
        )
        self.assertIsNone(decision)


if __name__ == "__main__":
    unittest.main()
