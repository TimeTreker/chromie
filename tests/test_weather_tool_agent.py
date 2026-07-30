from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.agents.tool import ToolAgent
from agent.app.capabilities.local import chromie_capability_bundle
from agent.app.capabilities.models import CapabilityRegistry
from agent.app.local_tool_execution import LocalToolExecutor
from agent.app.clients.weather_client import (
    WeatherQuery,
    WeatherReport,
    format_weather_brief,
    format_weather_report,
)
from agent.app.schema import AgentResult, AgentRunRequest, RouteDecision
from agent.app.tool_result_interpreter import ToolResultInterpreter


class _FakeOllama:
    def __init__(self, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.payloads = list(payload) if isinstance(payload, list) else [payload]
        self.prompts: list[str] = []
        self.response_formats: list[Any] = []

    async def generate(self, prompt: str, *, system=None, options=None, response_format="text") -> dict[str, Any]:
        self.prompts.append(prompt)
        self.response_formats.append(response_format)
        index = min(len(self.prompts) - 1, len(self.payloads) - 1)
        return dict(self.payloads[index])




def _services(*, weather_client, **kwargs: Any) -> AgentServices:
    return AgentServices(
        local_tool_executor=LocalToolExecutor(
            CapabilityRegistry.from_bundles([chromie_capability_bundle()]),
            weather_client=weather_client,
        ),
        **kwargs,
    )


class _FakeWeatherClient:
    def __init__(self) -> None:
        self.queries: list[WeatherQuery] = []

    async def lookup(self, query: WeatherQuery) -> WeatherReport:
        self.queries.append(query)
        return WeatherReport(
            location_name=query.location,
            country="China",
            timezone="Asia/Shanghai",
            date="2026-07-08",
            current_temperature_c=32.4,
            apparent_temperature_c=36.0,
            daily_high_c=35.0,
            daily_low_c=28.0,
            precipitation_probability_max=40.0,
            precipitation_sum_mm=1.2,
            weather_code=61,
            wind_speed_kmh=9.0,
        )


class WeatherToolAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_weather_tool_uses_llm_extracted_location_and_speaks_report(self) -> None:
        weather = _FakeWeatherClient()
        agent = ToolAgent(
            _services(
                weather_client=weather,
                ollama=_FakeOllama({"location": "Chongqing", "date": "today", "units": "metric"}),
            )
        )
        request = AgentRunRequest(
            text="what's the weather today in chongqing",
            language="en-US",
            route_decision=RouteDecision(
                route="tool",
                intent="capability:chromie.weather.lookup",
                confidence=0.9,
                language="en-US",
                agents=["tool_agent", "speaker_agent"],
                metadata={"tool_name": "weather"},
            ),
        )

        with self.assertLogs("chromie.agent.tool", level="INFO") as captured:
            result = await agent.run(request, AgentResult())

        logs = "\n".join(captured.output)
        self.assertIn("tool_agent_start", logs)
        self.assertIn("weather_tool_start", logs)
        self.assertIn("weather_query_extract_llm_result", logs)
        self.assertIn("weather_request_params", logs)
        self.assertIn("weather_lookup_done", logs)
        self.assertEqual(weather.queries[0].location, "Chongqing")
        self.assertEqual(weather.queries[0].date, "today")
        self.assertEqual(len(result.speak_immediate), 1)
        self.assertIn("Chongqing", result.speak_immediate[0].text)
        self.assertIn("32°C", result.speak_immediate[0].text)
        self.assertIn("feels like 36°C", result.speak_immediate[0].text)
        self.assertIn("tool_agent", result.handled_by)

    async def test_weather_tool_asks_for_location_when_missing(self) -> None:
        weather = _FakeWeatherClient()
        agent = ToolAgent(
            _services(
                weather_client=weather,
                ollama=_FakeOllama({"location": "", "date": "today", "units": "metric"}),
            )
        )
        request = AgentRunRequest(
            text="今天天气怎么样",
            language="zh-CN",
            route_decision=RouteDecision(
                route="tool",
                intent="capability:chromie.weather.lookup",
                confidence=0.9,
                language="zh-CN",
                agents=["tool_agent"],
                metadata={"tool_name": "weather"},
            ),
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(weather.queries, [])
        self.assertEqual(result.speak_immediate, [])
        self.assertEqual(result.status, "clarify")
        self.assertEqual(result.reason, "weather_location_binding_missing")

    async def test_weather_tool_can_use_goal_interpretation_metadata_without_llm(self) -> None:
        weather = _FakeWeatherClient()
        agent = ToolAgent(_services(weather_client=weather, use_llm=False))
        request = AgentRunRequest(
            text="重庆今天的天气怎么样",
            language="zh-CN",
            route_decision=RouteDecision(
                route="tool",
                intent="capability:chromie.weather.lookup",
                confidence=0.9,
                language="zh-CN",
                agents=["tool_agent"],
                metadata={
                    "tool_name": "weather",
                    "weather_query": {"location": "重庆", "date": "today", "units": "metric"},
                },
            ),
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(weather.queries[0].location, "重庆")
        self.assertIn("重庆今天", result.speak_immediate[0].text)
        self.assertIn("现在约32℃", result.speak_immediate[0].text)

    async def test_weather_tool_composes_a_direct_concise_answer_to_comfort_question(self) -> None:
        weather = _FakeWeatherClient()
        ollama = _FakeOllama(
            {"location": "重庆", "date": "today", "units": "metric"}
        )
        interpreter_ollama = _FakeOllama(
            {
                "spoken_response": "很热呀，现在约32℃，体感36℃。",
                "answer_mode": "direct",
                "selected_facts": [
                    {"evidence_id": "weather_turn", "json_pointer": "/current_temperature_c"},
                    {"evidence_id": "weather_turn", "json_pointer": "/apparent_temperature_c"},
                ],
                "confidence": 0.96,
                "rationale": "The user asked whether it is hot.",
            }
        )
        agent = ToolAgent(
            _services(
                weather_client=weather,
                ollama=ollama,
                tool_result_interpreter=ToolResultInterpreter(interpreter_ollama),
            )
        )
        request = AgentRunRequest(
            text="今天重庆天热不热？",
            language="zh-CN",
            context={
                "mind": {
                    "owner_approved": True,
                    "identity": {
                        "entity_id": "chromie",
                        "name": "Chromie",
                        "kind": "person",
                    },
                    "personality_expression": {
                        "owner_approved": True,
                        "core_traits": ["smart", "curious", "playful"],
                        "answer_style": "Answer directly, then add one or two useful details.",
                    },
                }
            },
            route_decision=RouteDecision(
                route="tool",
                intent="capability:chromie.weather.lookup",
                confidence=0.95,
                language="zh-CN",
                agents=["tool_agent", "speaker_agent"],
                metadata={
                    "tool_name": "weather",
                    "weather_query": {
                        "location": "重庆",
                        "date": "today",
                        "units": "metric",
                    },
                },
            ),
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "很热呀，现在约32℃，体感36℃。",
        )
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(len(interpreter_ollama.prompts), 1)
        self.assertIn("First understand the exact question the user asked", interpreter_ollama.prompts[0])
        self.assertIsInstance(interpreter_ollama.response_formats[0], dict)
        self.assertIn("Chromie personality JSON", interpreter_ollama.prompts[0])
        self.assertIn("playful", interpreter_ollama.prompts[0])
        self.assertEqual(result.metadata["tool_result_interpretation"]["answer_mode"], "direct")
        self.assertEqual(len(result.metadata["tool_results"]), 1)

    async def test_weather_tool_uses_one_short_grounded_fallback_when_composer_is_invalid(self) -> None:
        weather = _FakeWeatherClient()
        ollama = _FakeOllama(
            {"location": "重庆", "date": "today", "units": "metric"}
        )
        interpreter_ollama = _FakeOllama(
            {
                "spoken_response": "",
                "answer_mode": "summary",
                "selected_facts": [],
                "confidence": 0.0,
                "rationale": "",
            }
        )
        agent = ToolAgent(
            _services(
                weather_client=weather,
                ollama=ollama,
                tool_result_interpreter=ToolResultInterpreter(interpreter_ollama),
            )
        )
        request = AgentRunRequest(
            text="重庆今天怎么样？",
            language="zh-CN",
            route_decision=RouteDecision(
                route="tool",
                intent="capability:chromie.weather.lookup",
                confidence=0.95,
                language="zh-CN",
                agents=["tool_agent"],
                metadata={"tool_name": "weather"},
            ),
        )

        result = await agent.run(request, AgentResult())
        speech = result.speak_immediate[0].text

        self.assertEqual(speech, "重庆今天小雨，现在约32℃，体感约36℃。")
        self.assertLessEqual(len(speech), 36)
        self.assertNotIn("降水概率", speech)
        self.assertNotIn("风速", speech)

    async def test_weather_tool_rejects_overlong_chinese_composer_output(self) -> None:
        weather = _FakeWeatherClient()
        ollama = _FakeOllama(
            {"location": "重庆", "date": "today", "units": "metric"}
        )
        interpreter_ollama = _FakeOllama(
            {
                "spoken_response": (
                    "重庆今天有小雨，现在大约32摄氏度，体感36摄氏度，"
                    "最高35摄氏度，降水概率40%，风速9公里每小时。"
                ),
                "answer_mode": "summary",
                "selected_facts": [
                    {"evidence_id": "weather_turn", "json_pointer": "/current_temperature_c"},
                    {"evidence_id": "weather_turn", "json_pointer": "/apparent_temperature_c"},
                    {"evidence_id": "weather_turn", "json_pointer": "/daily_high_c"},
                    {"evidence_id": "weather_turn", "json_pointer": "/precipitation_probability_max"},
                    {"evidence_id": "weather_turn", "json_pointer": "/wind_speed_kmh"},
                ],
                "confidence": 0.9,
                "rationale": "Too verbose.",
            }
        )
        agent = ToolAgent(
            _services(
                weather_client=weather,
                ollama=ollama,
                tool_result_interpreter=ToolResultInterpreter(interpreter_ollama),
            )
        )
        request = AgentRunRequest(
            text="重庆今天热不热？",
            language="zh-CN",
            route_decision=RouteDecision(
                route="tool",
                intent="capability:chromie.weather.lookup",
                confidence=0.95,
                language="zh-CN",
                agents=["tool_agent"],
                metadata={"tool_name": "weather"},
            ),
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "重庆今天小雨，现在约32℃，体感约36℃。",
        )



class WeatherFormattingTests(unittest.TestCase):
    def test_format_weather_brief_keeps_exception_fallback_short(self) -> None:
        report = WeatherReport(
            location_name="重庆",
            country="中国",
            timezone="Asia/Shanghai",
            date="2026-07-08",
            current_temperature_c=31.9,
            apparent_temperature_c=35.2,
            daily_high_c=34.8,
            daily_low_c=27.6,
            precipitation_probability_max=55,
            precipitation_sum_mm=3.4,
            weather_code=63,
            wind_speed_kmh=8.2,
        )

        text = format_weather_brief(report, language="zh-CN")

        self.assertEqual(text, "重庆今天中雨，现在约32℃，体感约35℃。")
        self.assertNotIn("最高", text)
        self.assertNotIn("降水概率", text)
        self.assertNotIn("风速", text)

    def test_format_weather_report_zh(self) -> None:
        report = WeatherReport(
            location_name="重庆",
            country="中国",
            timezone="Asia/Shanghai",
            date="2026-07-08",
            current_temperature_c=31.9,
            apparent_temperature_c=35.2,
            daily_high_c=34.8,
            daily_low_c=27.6,
            precipitation_probability_max=55,
            precipitation_sum_mm=3.4,
            weather_code=63,
            wind_speed_kmh=8.2,
        )

        text = format_weather_report(report, language="zh-CN")

        self.assertIn("重庆今天中雨", text)
        self.assertIn("最高 35℃、最低 28℃", text)
        self.assertIn("降水概率最高约 55%", text)


if __name__ == "__main__":
    unittest.main()
