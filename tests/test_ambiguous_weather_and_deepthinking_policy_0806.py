from __future__ import annotations

import unittest

from orchestrator.runtime.deepthinking_policy import (
    DeepThinkingDelegationPolicy,
    DeepThinkingPolicyConfig,
)
from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision
from router.app.llm_router import OllamaLLMRouter
from router.app.schema import FastSpeech, RouteDecision, RouteRequest, finalize_decision


class AmbiguousWeatherAndDeepthinkingPolicy0806Tests(unittest.TestCase):
    def test_weather_tool_route_without_weather_cue_becomes_llm_clarify(self) -> None:
        request = RouteRequest(text="你能查天信吗？", language="zh-CN")
        decision = finalize_decision(
            RouteDecision(
                route="tool",
                agents=["tool_agent", "speaker_agent"],
                intent="weather_query",
                confidence=0.95,
                language="zh-CN",
                fast_speech=FastSpeech(
                    text="checking_only",
                    purpose="acknowledge_and_check",
                    commitment="checking_only",
                ),
                metadata={
                    "tool_name": "weather",
                    "weather_query": {"location": "天信", "date": "today", "units": "metric"},
                },
                source="llm",
            ),
            request,
            source="llm",
        )

        router = OllamaLLMRouter(ollama_url="http://example.invalid", model="test", timeout_ms=800, confidence_threshold=0.55)
        rejected = router._reject_ambiguous_weather_tool_route(request, decision)

        self.assertEqual(rejected.route, "clarify")
        self.assertEqual(rejected.intent, "ambiguous_tool_or_asr")
        self.assertIn("conversation_agent", rejected.agents)
        self.assertIsNone(rejected.speak_first)
        self.assertTrue(rejected.metadata.get("llm_clarification_required"))
        self.assertEqual(
            rejected.metadata.get("rejected_weather_route", {}).get("location"),
            "天信",
        )

    def test_explicit_weather_tool_route_is_not_rejected(self) -> None:
        request = RouteRequest(text="重庆今天的天气怎么样？", language="zh-CN")
        decision = finalize_decision(
            RouteDecision(
                route="tool",
                agents=["tool_agent", "speaker_agent"],
                intent="weather_query",
                confidence=0.95,
                language="zh-CN",
                fast_speech=FastSpeech(text="好的，我查一下重庆今天的天气。"),
                metadata={
                    "tool_name": "weather",
                    "weather_query": {"location": "重庆", "date": "today", "units": "metric"},
                },
                source="llm",
            ),
            request,
            source="llm",
        )

        router = OllamaLLMRouter(ollama_url="http://example.invalid", model="test", timeout_ms=800, confidence_threshold=0.55)
        kept = router._reject_ambiguous_weather_tool_route(request, decision)

        self.assertEqual(kept.route, "tool")
        self.assertEqual(kept.intent, "weather_query")
        self.assertEqual(kept.metadata.get("weather_query", {}).get("location"), "重庆")

    def test_fast_speech_contract_marker_is_not_playable_text(self) -> None:
        decision = RouteDecision.model_validate(
            {
                "route": "tool",
                "intent": "weather_query",
                "confidence": 0.95,
                "fast_speech": {
                    "text": "checking_only",
                    "purpose": "acknowledge_and_check",
                    "commitment": "checking_only",
                },
                "speak_first": "checking_only",
            }
        )

        self.assertEqual(decision.fast_speech.text, "")
        self.assertIsNone(decision.speak_first)

    def test_exact_physical_capability_without_router_args_uses_capability_lane(self) -> None:
        policy = DeepThinkingDelegationPolicy(DeepThinkingPolicyConfig())
        decision = OrchestratorRouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="capability:soridormi.walk_forward",
            confidence=1.0,
            source="llm",
        )

        delegation = policy.evaluate(decision, context={})

        self.assertFalse(delegation.should_delegate)
        self.assertTrue(delegation.high_risk_physical)
        self.assertEqual(delegation.threshold, 0.95)

    def test_exact_physical_capability_still_delegates_when_uncertain(self) -> None:
        policy = DeepThinkingDelegationPolicy(DeepThinkingPolicyConfig())
        decision = OrchestratorRouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent="capability:soridormi.walk_forward",
            confidence=0.60,
            source="llm",
        )

        delegation = policy.evaluate(decision, context={})

        self.assertTrue(delegation.should_delegate)
        self.assertIn("confidence_below_0.95", delegation.reasons)


if __name__ == "__main__":
    unittest.main()
