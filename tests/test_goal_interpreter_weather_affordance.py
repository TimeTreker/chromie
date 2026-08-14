from __future__ import annotations

import inspect
import unittest
from typing import Any
from unittest import mock

from agent.app.cognitive_core.goal_interpreter.schema import (
    FastSpeech,
    RouteDecision,
    RouteItem,
    RouteRequest,
)


WEATHER_CAPABILITY = {
    "capability_id": "chromie.weather.lookup",
    "description": "Read current weather or forecast for a city.",
    "route": "tool",
    "available": True,
    "prompt_tier": "common",
    "effects": ["read_only", "weather_lookup"],
}


class _Catalog:
    async def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        del refresh
        return {
            "catalog_version": 1,
            "capabilities": [WEATHER_CAPABILITY],
        }


class _Interpreter:
    def __init__(self, decision: RouteDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def route(self, request: RouteRequest) -> RouteDecision:
        del request
        self.calls += 1
        return self.decision


class WeatherAffordanceTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _request(text: str, *, language: str = "en-US") -> RouteRequest:
        return RouteRequest(
            sid="weather-contract-test",
            text=text,
            language=language,
            context={"gateway_admission_complete": True},
        )

    async def _interpret(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> tuple[RouteDecision, _Interpreter]:
        from agent.app.cognitive_core.goal_interpreter import engine

        interpreter = _Interpreter(decision)
        with mock.patch.object(engine.settings, "mode", "hybrid"), mock.patch.object(
            engine, "capability_catalog", _Catalog()
        ), mock.patch.object(engine, "goal_interpreter", interpreter):
            result = await engine.interpret_turn(request)
        return result, interpreter

    async def test_weather_semantics_do_not_trigger_host_route_repair(self) -> None:
        request = self._request("what is the weather in Chongqing today")
        result, interpreter = await self._interpret(
            request,
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
        )

        self.assertEqual(interpreter.calls, 1)
        self.assertEqual(result.route, "chat")
        self.assertEqual(result.intent, "weather_query")
        self.assertNotIn("semantic_route_repair", result.metadata)

    async def test_weather_intent_alone_does_not_create_host_conflict(self) -> None:
        request = self._request("what is the weather in Chongqing today")
        result, _ = await self._interpret(
            request,
            RouteDecision(
                route="chat",
                intent="weather_query",
                confidence=0.95,
                language="en-US",
                source="llm",
                metadata={"tool_name": "weather"},
            ),
        )

        self.assertEqual(result.route, "chat")
        self.assertFalse(result.metadata.get("llm_clarification_required", False))

    async def test_underspecified_robot_output_never_uses_keyword_recovery_or_executes(
        self,
    ) -> None:
        request = self._request("重庆今天天气情况怎么样？", language="zh-CN")
        result, interpreter = await self._interpret(
            request,
            RouteDecision(
                route="robot_action",
                intent="physical_motion",
                confidence=1.0,
                language="zh-CN",
                source="llm",
            ),
        )

        self.assertEqual(interpreter.calls, 1)
        self.assertEqual(result.route, "robot_action")
        self.assertEqual(result.intent, "semantic_capability_planning")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.actions, [])
        self.assertEqual(result.candidate_capabilities, [])
        self.assertEqual(
            result.metadata.get("capability_grounding", {}).get("status"),
            "unresolved_requires_planner",
        )
        self.assertTrue(
            result.metadata.get("core_semantic_handoff", {}).get(
                "must_not_execute_partial_route"
            )
        )
        self.assertNotIn("semantic_route_repair", result.metadata)

    async def test_valid_model_weather_contract_is_not_rejected_by_text_keywords(
        self,
    ) -> None:
        request = self._request("你能查天信吗？", language="zh-CN")
        result, _ = await self._interpret(
            request,
            RouteDecision(
                route="tool",
                agents=["tool_agent", "speaker_agent"],
                intent="capability:chromie.weather.lookup",
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
        )

        self.assertEqual(result.route, "tool")
        self.assertEqual(
            result.metadata.get("weather_query", {}).get("location"),
            "天信",
        )
        self.assertNotIn("semantic_route_repair", result.metadata)

    def test_goal_interpreter_source_has_no_weather_phrase_rule(self) -> None:
        source = inspect.getsource(
            __import__(
                "agent.app.cognitive_core.goal_interpreter.engine",
                fromlist=["*"],
            )
        )
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
