from __future__ import annotations

import unittest

from agent.app.interaction import AgentResultInteractionAdapter
from agent.app.schema import AgentResult


class AgentInteractionTests(unittest.TestCase):
    def test_adapter_translates_nod_to_named_soridormi_skill(self) -> None:
        result = AgentResult()
        result.add_speak_immediate("Okay.")
        action = result.add_action(
            "robot_pose_controller",
            "head.nod",
            params={"times": 2, "duration_ms": 800},
            timeout_ms=1000,
        )

        response = AgentResultInteractionAdapter().convert(result)

        self.assertEqual(response.speech[0].text, "Okay.")
        self.assertEqual(response.skills[0].request_id, action.id)
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertIsNone(response.skills[0].timeout_ms)
        self.assertEqual(
            response.skills[0].metadata["legacy_action_type"],
            "head.nod",
        )
        self.assertEqual(response.skills[0].metadata["legacy_timeout_ms"], 1000)

    def test_adapter_promotes_single_nod_to_visible_two_cycle_skill(self) -> None:
        result = AgentResult()
        result.add_action(
            "robot_pose_controller",
            "head.nod",
            params={"times": 1},
        )

        response = AgentResultInteractionAdapter().convert(result)

        self.assertEqual(response.skills[0].args, {"count": 2})

    def test_adapter_translates_look_at_user_without_low_level_fields(self) -> None:
        result = AgentResult()
        result.add_action(
            "robot_pose_controller",
            "head.look_at_user",
            params={"duration_ms": 3000},
        )

        response = AgentResultInteractionAdapter().convert(result)

        self.assertEqual(response.skills[0].skill_id, "soridormi.look_at_person")
        self.assertEqual(response.skills[0].args, {"duration_s": 3.0})
        self.assertNotIn("joint_targets", response.model_dump_json())

    def test_blocked_agent_result_becomes_refusal(self) -> None:
        response = AgentResultInteractionAdapter().convert(
            AgentResult(status="blocked", reason="unsafe")
        )

        self.assertEqual(response.status, "refused")
        self.assertEqual(response.reason, "unsafe")


if __name__ == "__main__":
    unittest.main()
