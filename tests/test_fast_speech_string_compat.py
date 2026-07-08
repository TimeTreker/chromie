from __future__ import annotations

import unittest

from orchestrator.schemas.route import RouteDecision as OrchestratorRouteDecision
from router.app.llm_router import OllamaLLMRouter
from router.app.schema import RouteDecision, RouteRequest


class FastSpeechStringCompatibilityTests(unittest.TestCase):
    def test_router_route_decision_accepts_fast_speech_string(self) -> None:
        decision = RouteDecision.model_validate(
            {
                "route": "tool",
                "intent": "weather_query",
                "confidence": 0.95,
                "fast_speech": "好的，我查一下重庆今天的天气。",
                "routes": [
                    {
                        "route": "tool",
                        "intent": "weather_query",
                        "confidence": 0.95,
                        "fast_speech": "好的，我查一下重庆今天的天气。",
                    }
                ],
            }
        )

        self.assertEqual(decision.fast_speech.text, "好的，我查一下重庆今天的天气。")
        self.assertEqual(decision.speak_first, "好的，我查一下重庆今天的天气。")
        self.assertEqual(decision.routes[0].fast_speech.text, "好的，我查一下重庆今天的天气。")

    def test_router_decision_from_response_preserves_weather_review_with_fast_speech_string(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )

        decision = router._decision_from_response(
            RouteRequest(text="今天重庆天气怎么样？", language="zh-CN"),
            {
                "message": {
                    "content": (
                        '{"route":"tool","intent":"weather_query","confidence":0.95,'
                        '"metadata":{"tool_name":"weather",'
                        '"weather_query":"today weather in Chongqing"},'
                        '"fast_speech":"好的，我查一下重庆今天的天气。"}'
                    )
                }
            },
            stage="intent_review",
        )

        self.assertEqual(decision.route, "tool")
        self.assertEqual(decision.intent, "weather_query")
        self.assertIsNotNone(decision.fast_speech)
        self.assertEqual(decision.fast_speech.text, "好的，我查一下重庆今天的天气。")
        self.assertEqual(decision.speak_first, "好的，我查一下重庆今天的天气。")

    def test_orchestrator_route_schema_accepts_fast_speech_string(self) -> None:
        decision = OrchestratorRouteDecision.model_validate(
            {
                "route": "tool",
                "intent": "weather_query",
                "confidence": 0.95,
                "language": "zh-CN",
                "fast_speech": "好的，我查一下重庆今天的天气。",
            }
        )

        self.assertEqual(decision.fast_speech.text, "好的，我查一下重庆今天的天气。")


if __name__ == "__main__":
    unittest.main()
