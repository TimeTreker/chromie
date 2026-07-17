from __future__ import annotations

import unittest
from typing import Any

from router.app.llm_router import OllamaLLMRouter
from router.app.schema import FastSpeech, RouteDecision, RouteItem, RouteRequest, finalize_decision


WEATHER_CAPABILITY = {
    "capability_id": "chromie.weather.lookup",
    "description": "Read current weather or forecast for a city.",
    "route": "tool",
    "available": True,
    "prompt_tier": "common",
    "effects": ["read_only", "weather_lookup"],
}


class _EmptyReviewRouter(OllamaLLMRouter):
    async def _chat_logged(self, payload: dict[str, Any], *, stage: str, request=None) -> dict[str, Any]:
        return {"message": {"content": ""}, "done": True, "done_reason": "stop"}


class WeatherAffordanceTests(unittest.IsolatedAsyncioTestCase):
    def _router(self) -> _EmptyReviewRouter:
        return _EmptyReviewRouter(
            ollama_url="http://example.invalid",
            model="qwen3:4b",
            review_model="qwen3:4b",
            timeout_ms=800,
            review_timeout_ms=800,
            confidence_threshold=0.55,
        )

    def _weather_request(self, text: str = "重庆今天天气情况怎么样？") -> RouteRequest:
        return RouteRequest(
            sid="weather-recovery-test",
            text=text,
            language="zh-CN",
            context={
                "common_ability_catalog": [WEATHER_CAPABILITY],
                "prompt_capabilities_common": [WEATHER_CAPABILITY],
            },
        )

    def test_weather_tool_route_requires_explicit_weather_cue(self) -> None:
        cases = (
            {
                "text": "你能查天信吗？",
                "location": "天信",
                "expected_route": "clarify",
            },
            {
                "text": "重庆今天的天气怎么样？",
                "location": "重庆",
                "expected_route": "tool",
            },
        )

        for case in cases:
            with self.subTest(text=case["text"]):
                request = RouteRequest(text=case["text"], language="zh-CN")
                decision = finalize_decision(
                    RouteDecision(
                        route="tool",
                        agents=["tool_agent", "speaker_agent"],
                        intent="weather_query",
                        confidence=0.95,
                        language="zh-CN",
                        fast_speech=FastSpeech(
                            text=(
                                "好的，我查一下重庆今天的天气。"
                                if case["expected_route"] == "tool"
                                else "checking_only"
                            ),
                            purpose="acknowledge_and_check",
                            commitment="checking_only",
                        ),
                        metadata={
                            "tool_name": "weather",
                            "weather_query": {
                                "location": case["location"],
                                "date": "today",
                                "units": "metric",
                            },
                        },
                        source="llm",
                    ),
                    request,
                    source="llm",
                )

                result = self._router()._reject_ambiguous_weather_tool_route(
                    request, decision
                )

                self.assertEqual(result.route, case["expected_route"])
                if case["expected_route"] == "clarify":
                    self.assertEqual(result.intent, "ambiguous_tool_or_asr")
                    self.assertIn("conversation_agent", result.agents)
                    self.assertTrue(result.metadata.get("llm_clarification_required"))
                    self.assertEqual(
                        result.metadata.get("rejected_weather_route", {}).get("location"),
                        case["location"],
                    )
                else:
                    self.assertEqual(result.intent, "weather_query")
                    self.assertEqual(
                        result.metadata.get("weather_query", {}).get("location"),
                        case["location"],
                    )

    async def test_empty_review_recovers_weather_misroute_from_catalog_affordance(self) -> None:
        request = self._weather_request()
        bad_quick_decision = finalize_decision(
            RouteDecision(
                route="robot_action",
                intent="physical_motion",
                confidence=1.0,
                language="zh-CN",
                source="llm",
            ),
            request,
            source="llm",
        )

        recovered = await self._router()._review_route_only_robot_action(
            request,
            bad_quick_decision,
        )

        self.assertEqual(recovered.route, "tool")
        self.assertEqual(recovered.intent, "weather_query")
        self.assertEqual(recovered.metadata.get("tool_name"), "weather")
        self.assertEqual(recovered.metadata.get("tool_capability_id"), "chromie.weather.lookup")
        self.assertEqual(recovered.metadata.get("weather_query", {}).get("location"), "重庆")
        self.assertEqual(recovered.metadata.get("weather_query", {}).get("date"), "today")
        self.assertEqual(recovered.fast_speech.text, "好的，我查一下重庆今天的天气。")
        self.assertEqual(recovered.speak_first, "好的，我查一下重庆今天的天气。")
        self.assertIn("weather affordance recovery", recovered.reason or "")

    def test_weather_recovery_requires_catalog_affordance(self) -> None:
        request = RouteRequest(
            sid="no-weather-capability",
            text="重庆今天天气情况怎么样？",
            language="zh-CN",
            context={"common_ability_catalog": []},
        )
        decision = finalize_decision(
            RouteDecision(
                route="robot_action",
                intent="physical_motion",
                confidence=1.0,
                language="zh-CN",
                source="llm",
            ),
            request,
            source="llm",
        )

        recovered = self._router()._recover_weather_affordance_misroute(
            request,
            decision,
            reason="unit_test",
        )

        self.assertEqual(recovered.route, "robot_action")
        self.assertEqual(recovered.intent, "physical_motion")

    def test_semantic_weather_chat_route_item_is_normalized_to_tool_lane(self) -> None:
        request = self._weather_request("what is the weather in Chongqing today")
        request.language = "en-US"
        decision = finalize_decision(
            RouteDecision(
                route="chat",
                routes=[
                    RouteItem(
                        route="chat",
                        intent="confirm_weather",
                        confidence=0.85,
                    )
                ],
                intent="weather_query",
                confidence=0.95,
                language="en-US",
                source="llm",
                metadata={"tool_name": "weather"},
            ),
            request,
            source="llm",
        )

        recovered = self._router()._recover_weather_affordance_misroute(
            request,
            decision,
            reason="unit_test_semantic_weather_chat_route",
        )

        self.assertEqual(recovered.route, "tool")
        self.assertEqual(recovered.agents, ["tool_agent", "speaker_agent"])
        self.assertEqual(recovered.intent, "weather_query")
        self.assertEqual(recovered.metadata.get("tool_name"), "weather")
        self.assertEqual(recovered.metadata.get("weather_query", {}).get("location"), "Chongqing")
        self.assertEqual(recovered.metadata.get("weather_query", {}).get("date"), "today")
        self.assertEqual(
            recovered.metadata.get("weather_affordance_recovery", {}).get("original_route"),
            "chat",
        )

    def test_non_weather_robot_action_is_not_recovered_to_weather_tool(self) -> None:
        request = self._weather_request("往前走15秒，快点。")
        decision = finalize_decision(
            RouteDecision(
                route="robot_action",
                intent="physical_motion",
                confidence=1.0,
                language="zh-CN",
                source="llm",
            ),
            request,
            source="llm",
        )

        recovered = self._router()._recover_weather_affordance_misroute(
            request,
            decision,
            reason="unit_test",
        )

        self.assertEqual(recovered.route, "robot_action")
        self.assertEqual(recovered.intent, "physical_motion")


if __name__ == "__main__":
    unittest.main()
