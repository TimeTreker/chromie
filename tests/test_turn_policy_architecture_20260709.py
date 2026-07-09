from __future__ import annotations

import unittest

from orchestrator.runtime.deepthinking_policy import (
    DeepThinkingDelegationPolicy,
    DeepThinkingPolicyConfig,
)
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from orchestrator.schemas.route import RouteDecision, RouteItem
from router.app.llm_router import _weather_fast_speech_text, _weather_location_hint
from router.app.schema import RouteRequest
from shared.chromie_contracts.interaction import InteractionResponse


class TurnPolicyArchitecture20260709Test(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = DeepThinkingDelegationPolicy(DeepThinkingPolicyConfig())

    def test_exact_catalog_skill_route_item_does_not_delegate_to_deepthinking(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="capability:soridormi.walk_forward",
            confidence=1.0,
            routes=[
                RouteItem(
                    route="robot_action",
                    intent="capability:soridormi.walk_forward",
                    confidence=1.0,
                    skill_id="soridormi.walk_forward",
                )
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertFalse(delegation.should_delegate)
        self.assertTrue(delegation.high_risk_physical)
        self.assertEqual(delegation.threshold, 0.70)
        self.assertNotIn("high_risk_physical_goal", delegation.reasons)

    def test_parameterized_high_risk_action_still_delegates(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="capability:soridormi.walk_forward",
            confidence=1.0,
            actions=[
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15.0},
                }
            ],
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertTrue(delegation.high_risk_physical)
        self.assertIn("high_risk_physical_goal", delegation.reasons)

    def test_clarification_intent_is_never_deepthinking_robot_action(self) -> None:
        decision = RouteDecision(
            route="robot_action",
            agents=["speaker_agent"],
            intent="clarify_insufficient_information",
            confidence=0.0,
            speak_first='I only heard "W.". What would you like me to do?',
            source="llm",
        )

        delegation = self.policy.evaluate(decision, context={})

        self.assertFalse(delegation.should_delegate)
        self.assertEqual(delegation.reasons, ())

    def test_uncommitted_movement_claim_is_reconciled_before_tts(self) -> None:
        coordinator = InteractionRuntimeCoordinator(lambda payload: {"scheduled": True})
        response = InteractionResponse(
            speech=[{"text": "好的，我这就往前走十五秒。"}],
            skills=[],
            metadata={"language": "zh-CN", "route_final": "deep_thought"},
        )

        prepared = coordinator.prepare_response(response, session_id="sid-test")
        spoken = " ".join(item.text for item in prepared.speech)

        self.assertNotIn("我这就往前走", spoken)
        self.assertIn("不会说已经执行", spoken)
        self.assertTrue(prepared.metadata.get("truth_reconciled"))

    def test_chinese_weather_ack_does_not_duplicate_today(self) -> None:
        request = RouteRequest(
            text="今天重庆天气怎么样？",
            language="zh-CN",
        )

        self.assertEqual(_weather_location_hint(request.text), "重庆")
        self.assertEqual(_weather_fast_speech_text(request), "好的，我查一下重庆今天的天气。")


if __name__ == "__main__":
    unittest.main()
