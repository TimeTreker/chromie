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

    def test_walk_without_speed_uses_normal_safe_speed(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk forward for 5 seconds."),
            _result("soridormi.walk_velocity"),
        )
        assert decision is not None
        self.assertEqual(decision.actions[0]["capability_id"], "soridormi.walk_velocity")
        self.assertEqual(decision.actions[0]["args"]["vx_mps"], 0.18)
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 5.0)
        self.assertIsNone(decision.speak_first)

    def test_walk_speed_above_contract_uses_normal_speed_and_warns(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk forward at 1.5 speed for 3 seconds."),
            _result("soridormi.walk_velocity"),
        )
        assert decision is not None
        self.assertEqual(decision.actions[0]["args"]["vx_mps"], 0.18)
        self.assertEqual(
            decision.speak_first,
            "Too fast. Walking normally.",
        )
        self.assertEqual(
            decision.actions[0]["metadata"]["speed_adjustment"]["requested_vx_mps"],
            1.5,
        )

    def test_walk_speed_above_runtime_limit_uses_normal_speed_and_warns(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk forward at 0.25 speed for 10 seconds."),
            _result("soridormi.walk_velocity"),
        )
        assert decision is not None
        self.assertEqual(decision.actions[0]["args"]["vx_mps"], 0.18)
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 10.0)
        self.assertEqual(
            decision.actions[0]["metadata"]["speed_adjustment"]["safe_max_vx_mps"],
            0.2,
        )
        self.assertEqual(
            decision.speak_first,
            "Too fast. Walking normally.",
        )

    def test_sing_while_walking_adds_original_song_speech(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(
                text="sing a song for me while walk forward at 0.25 for 10 seconds"
            ),
            _result("soridormi.walk_velocity"),
        )
        assert decision is not None
        self.assertEqual(decision.actions[0]["capability_id"], "soridormi.walk_velocity")
        self.assertEqual(decision.actions[0]["args"]["vx_mps"], 0.18)
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 10.0)
        self.assertIn("Too fast", decision.speak_first or "")
        self.assertIn("La la", decision.speak_first or "")

    def test_backward_walk_without_speed_uses_safe_backward_speed(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk backward for 2 seconds."),
            _result("soridormi.walk_velocity"),
        )
        assert decision is not None
        self.assertEqual(decision.actions[0]["args"]["vx_mps"], -0.03)
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 2.0)

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
        self.assertEqual(decision.actions[2]["args"]["amplitude"], "small")
        self.assertEqual(decision.actions[2]["args"]["duration_s"], 1.4)

    def test_walk_with_head_nod_and_head_turn_phrase_is_supported(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(
                text=(
                    "Walk forward at 0.2 speed with noding your head for 15 seconds "
                    "and then turn your head to right to say hello"
                )
            ),
            _result(
                "soridormi.walk_velocity",
                "soridormi.nod_yes",
                "soridormi.look_direction",
                "soridormi.turn_in_place",
            ),
        )
        assert decision is not None
        self.assertEqual(decision.intent, "compound_robot_action")
        self.assertEqual(decision.speak_first, "Hello.")
        self.assertEqual(
            [item["capability_id"] for item in decision.actions],
            [
                "soridormi.walk_velocity",
                "soridormi.nod_yes",
                "soridormi.look_direction",
            ],
        )
        self.assertEqual(decision.actions[0]["args"]["vx_mps"], 0.2)
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 15.0)
        self.assertEqual(decision.actions[1]["args"]["count"], 2)
        self.assertEqual(decision.actions[1]["args"]["amplitude"], "small")
        self.assertEqual(decision.actions[1]["args"]["duration_s"], 1.4)
        self.assertEqual(decision.actions[2]["args"]["head_yaw_rad"], 0.35)
        self.assertEqual(decision.actions[2]["args"]["head_pitch_rad"], 0.0)

    def test_head_gesture_duration_is_clamped_to_skill_contract(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="nod your head for 15 seconds"),
            _result("soridormi.nod_yes"),
        )
        assert decision is not None
        self.assertEqual(decision.actions[0]["args"]["duration_s"], 10.0)

    def test_unknown_segment_does_not_partially_execute(self) -> None:
        decision = semantic_robot_decision(
            RouteRequest(text="Walk forward and then make coffee."),
            _result("soridormi.walk_velocity"),
        )
        self.assertIsNone(decision)


if __name__ == "__main__":
    unittest.main()
