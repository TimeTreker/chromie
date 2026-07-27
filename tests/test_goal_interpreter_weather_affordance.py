from __future__ import annotations

import inspect
import json
import unittest
from typing import Any

from agent.app.cognitive_core.goal_interpreter.model_interpreter import OllamaGoalInterpreter
from agent.app.cognitive_core.goal_interpreter.schema import FastSpeech, RouteDecision, RouteItem, RouteRequest, finalize_decision


WEATHER_CAPABILITY = {
    "capability_id": "chromie.weather.lookup",
    "description": "Read current weather or forecast for a city.",
    "route": "tool",
    "available": True,
    "prompt_tier": "common",
    "effects": ["read_only", "weather_lookup"],
}


class _EmptyReviewInterpreter(OllamaGoalInterpreter):
    async def _chat_logged(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request=None,
    ) -> dict[str, Any]:
        return {"message": {"content": ""}, "done": True, "done_reason": "stop"}


class _SemanticRepairInterpreter(OllamaGoalInterpreter):
    async def _chat_logged(
        self,
        payload: dict[str, Any],
        *,
        stage: str,
        request=None,
    ) -> dict[str, Any]:
        if stage != "semantic_route_repair":
            raise AssertionError(f"unexpected review stage {stage!r}")
        return {
            "message": {
                "content": json.dumps(
                    {
                        "route": "tool",
                        "intent": "weather_query",
                        "confidence": 0.96,
                    }
                )
            },
            "done": True,
            "done_reason": "stop",
        }


class WeatherAffordanceTests(unittest.IsolatedAsyncioTestCase):
    def _interpreter(self, cls=_EmptyReviewInterpreter):
        return cls(
            ollama_url="http://example.invalid",
            model="qwen3:4b",
            review_model="qwen3:4b",
            timeout_ms=800,
            review_timeout_ms=800,
            confidence_threshold=0.55,
        )

    @staticmethod
    def _request(text: str) -> RouteRequest:
        return RouteRequest(
            sid="weather-contract-test",
            text=text,
            language="en-US",
            context={
                "common_ability_catalog": [WEATHER_CAPABILITY],
                "prompt_capabilities_common": [WEATHER_CAPABILITY],
            },
        )

    async def test_weather_route_contract_is_repaired_by_semantic_model(self) -> None:
        request = self._request("what is the weather in Chongqing today")
        inconsistent = finalize_decision(
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

        repaired = await self._interpreter(_SemanticRepairInterpreter)._repair_route_intent_contract(
            request,
            inconsistent,
        )

        self.assertEqual(repaired.route, "tool")
        self.assertEqual(repaired.intent, "weather_query")
        self.assertNotIn("tool_name", repaired.metadata)
        self.assertNotIn("weather_query", repaired.metadata)
        self.assertEqual(
            repaired.metadata.get("semantic_route_repair", {}).get("status"),
            "repaired",
        )

    async def test_failed_weather_contract_repair_clarifies(self) -> None:
        request = self._request("what is the weather in Chongqing today")
        inconsistent = finalize_decision(
            RouteDecision(
                route="chat",
                intent="weather_query",
                confidence=0.95,
                language="en-US",
                source="llm",
                metadata={"tool_name": "weather"},
            ),
            request,
            source="llm",
        )

        result = await self._interpreter()._repair_route_intent_contract(
            request,
            inconsistent,
        )

        self.assertEqual(result.route, "clarify")
        self.assertEqual(result.intent, "clarify_uncertain_request")
        self.assertTrue(result.metadata.get("llm_clarification_required"))
        self.assertIn("semantic repair failed", result.reason or "")

    async def test_failed_underspecified_robot_review_never_uses_keyword_recovery(
        self,
    ) -> None:
        request = self._request("重庆今天天气情况怎么样？")
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

        result = await self._interpreter()._review_route_only_robot_action(
            request,
            bad_quick_decision,
        )

        self.assertEqual(result.route, "clarify")
        self.assertEqual(result.intent, "clarify_uncertain_request")
        self.assertEqual(result.skills if hasattr(result, "skills") else [], [])
        self.assertIn("semantic review failed", result.reason or "")

    async def test_valid_model_weather_contract_is_not_rejected_by_text_keywords(
        self,
    ) -> None:
        request = self._request("你能查天信吗？")
        decision = finalize_decision(
            RouteDecision(
                route="tool",
                agents=["tool_agent", "speaker_agent"],
                intent="weather_query",
                confidence=0.95,
                language="zh-CN",
                fast_speech=FastSpeech(
                    text="好的，我查一下。",
                    purpose="acknowledge_and_check",
                    commitment="checking_only",
                    must_not_claim_completion=True,
                ),
                metadata={
                    "tool_name": "weather",
                    "weather_query": {
                        "location": "天信",
                        "date": "today",
                        "units": "metric",
                    },
                },
                source="llm",
            ),
            request,
            source="llm",
        )

        result = await self._interpreter()._repair_route_intent_contract(
            request,
            decision,
        )

        self.assertIs(result, decision)
        self.assertEqual(result.route, "tool")
        self.assertEqual(
            result.metadata.get("weather_query", {}).get("location"),
            "天信",
        )

    def test_goal_interpreter_source_has_no_weather_phrase_rule(self) -> None:
        source = inspect.getsource(__import__("agent.app.cognitive_core.goal_interpreter.engine", fromlist=["*"]))
        for forbidden in (
            "_is_weather_like_text",
            "_ZH_WEATHER_TERMS",
            "_EN_WEATHER_TERMS",
            "_weather_location_hint",
            "weather_route_without_explicit_weather_cue",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
