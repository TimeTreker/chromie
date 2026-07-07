from __future__ import annotations

import unittest

from orchestrator.runtime.deepthinking_policy import (
    DeepThinkingDelegationPolicy,
    DeepThinkingPolicyConfig,
)
from orchestrator.schemas.route import RouteDecision, RouteItem


class DeepThinkingDelegationPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = DeepThinkingDelegationPolicy(DeepThinkingPolicyConfig())

    def test_simple_exact_low_risk_body_action_does_not_delegate(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="soridormi.nod_yes",
            confidence=0.92,
            actions=[{"skill_id": "soridormi.nod_yes", "args": {"count": 1}}],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertFalse(delegation.should_delegate)
        self.assertFalse(delegation.high_risk_physical)
        self.assertEqual(delegation.threshold, 0.70)

    def test_high_risk_navigation_goal_delegates_even_with_high_confidence(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="soridormi.walk_forward",
            confidence=0.99,
            actions=[{"skill_id": "soridormi.walk_forward", "args": {"seconds": 3}}],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertTrue(delegation.high_risk_physical)
        self.assertIn("high_risk_physical_goal", delegation.reasons)
        self.assertEqual(delegation.threshold, 0.95)

    def test_high_confidence_compound_low_risk_body_actions_do_not_delegate(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="compound_low_risk_gesture",
            confidence=0.91,
            actions=[
                {"skill_id": "soridormi.nod_yes", "args": {"count": 1}},
                {"skill_id": "soridormi.wave_hand", "args": {"count": 1}},
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertFalse(delegation.should_delegate)
        self.assertTrue(delegation.compound_action)
        self.assertEqual(delegation.threshold, 0.82)


    def test_router_capability_id_navigation_action_delegates(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="compound_common_catalog_task",
            confidence=0.99,
            actions=[
                {
                    "capability_id": "soridormi.walk_velocity",
                    "args": {"vx_mps": 0.15, "duration_s": 3.0},
                    "sequence": 0,
                    "confidence": 0.98,
                },
                {
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                    "sequence": 1,
                    "confidence": 0.98,
                },
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertTrue(delegation.high_risk_physical)
        self.assertTrue(delegation.compound_action)
        self.assertIn("high_risk_physical_goal", delegation.reasons)
        self.assertEqual(delegation.threshold, 0.95)

    def test_router_action_live_perception_flag_delegates(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="compound_common_catalog_task",
            confidence=0.96,
            actions=[
                {
                    "capability_id": "soridormi.inspect_object",
                    "args": {"object": "phone"},
                    "requires_live_perception": True,
                }
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertIn("requires_live_perception", delegation.reasons)

    def test_selected_candidate_high_risk_metadata_delegates(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="compound_common_catalog_task",
            confidence=0.99,
            actions=[
                {
                    "capability_id": "soridormi.move_base",
                    "args": {"distance_m": 0.5},
                    "confidence": 0.99,
                }
            ],
            candidate_capabilities=[
                {
                    "capability_id": "soridormi.move_base",
                    "available": True,
                    "interaction_executable": True,
                    "safety_class": "guarded_operation",
                    "effects": ["mobile_base_motion"],
                }
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertTrue(delegation.high_risk_physical)

    def test_low_confidence_compound_body_action_delegates(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="compound_low_risk_gesture",
            confidence=0.76,
            actions=[
                {"skill_id": "soridormi.nod_yes", "args": {"count": 1}},
                {"skill_id": "soridormi.wave_hand", "args": {"count": 1}},
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertIn("confidence_below_0.82", delegation.reasons)

    def test_missing_desired_ability_delegates_and_preserves_original_route(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="blink_eyes",
            confidence=0.94,
            metadata={
                "desired_abilities": [
                    {
                        "ability_id": "social.blink_eyes",
                        "status": "missing_ability",
                        "reason": "no eye actuator skill is available",
                    }
                ]
            },
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})
        delegated = self.policy.delegate_decision(decision, delegation)

        self.assertTrue(delegation.should_delegate)
        self.assertEqual(delegated.route, "deep_thought")
        self.assertEqual(delegated.intent, "deep_thought_policy_delegate")
        self.assertEqual(delegated.agents, ["deepthinking_agent", "speaker_agent"])
        metadata = delegated.metadata["orchestrator_deepthinking_delegation"]
        self.assertEqual(metadata["original_route"], "robot_action")
        self.assertIn("missing_or_desired_ability", metadata["reasons"])
        self.assertIn("SkillRuntime", metadata["note"])

    def test_route_item_can_request_deepthinking_without_physical_risk(self) -> None:
        decision = RouteDecision(
            route="chat",
            intent="mixed_request",
            confidence=0.96,
            routes=[
                RouteItem(
                    route="chat",
                    intent="greeting",
                    confidence=0.98,
                    lane="immediate_speech",
                    direct_to_tts=True,
                    text="Hi.",
                ),
                RouteItem(
                    route="deep_thought",
                    intent="plan_complex_task",
                    confidence=0.82,
                    lane="deepthought",
                    requires_mind=True,
                ),
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertIn("route_item_requests_deepthinking", delegation.reasons)

    def test_disabled_policy_never_delegates(self) -> None:
        policy = DeepThinkingDelegationPolicy(
            DeepThinkingPolicyConfig(enabled=False)
        )
        decision = RouteDecision(
            route="robot_action",
            intent="soridormi.walk_forward",
            confidence=0.1,
            actions=[{"skill_id": "soridormi.walk_forward"}],
        )

        delegation = policy.evaluate(decision, context={"user_state": "frustrated"})

        self.assertFalse(delegation.should_delegate)


if __name__ == "__main__":
    unittest.main()
