from __future__ import annotations

import asyncio
import json
import unittest
from types import MethodType
from typing import Any
from pathlib import Path

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.schemas.route import RouteDecision


class RuntimeReliabilityStage4Tests(unittest.TestCase):
    def test_agent_disconnect_on_robot_action_fails_closed_without_promising_execution(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        decision = RouteDecision(
            route="robot_action",
            intent="compound_common_catalog_task",
            confidence=0.95,
            actions=[
                {
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                }
            ],
            metadata={},
        )

        response = assistant._agent_exception_safe_response(
            decision,
            user_text="你点点头再眨两下眼睛。",
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.skills, [])
        spoken = " ".join(item.text for item in response.speech)
        self.assertIn("没有动", spoken)
        self.assertNotIn("我会点头", spoken)
        self.assertNotIn("正在执行", spoken)

    def test_agent_disconnect_on_tool_route_refuses_to_invent_result(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        decision = RouteDecision(
            route="tool",
            intent="weather_query",
            confidence=0.95,
            metadata={"tool_name": "weather"},
        )

        response = assistant._agent_exception_safe_response(
            decision,
            user_text="北京天气怎么样？",
        )

        self.assertIsNotNone(response)
        assert response is not None
        spoken = " ".join(item.text for item in response.speech)
        self.assertIn("没查成功", spoken)
        self.assertIn("不能乱说", spoken)
        self.assertNotIn("查询服务", spoken)
        self.assertNotIn("未经验证", spoken)
        self.assertEqual(response.skills, [])


    def test_tool_route_with_capability_task_does_not_use_action_fallback(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        decision = RouteDecision(
            route="tool",
            intent="weather.lookup",
            confidence=0.95,
            metadata={
                "task_list": [
                    {
                        "task_type": "task.execute.capability",
                        "capability_id": "chromie.weather.lookup",
                    }
                ]
            },
        )

        response = assistant._agent_exception_safe_response(
            decision,
            user_text="查一下重庆天气。",
        )

        assert response is not None
        spoken = " ".join(item.text for item in response.speech)
        self.assertIn("没查成功", spoken)
        self.assertNotIn("没有动", spoken)

    def test_warmup_uses_a_one_token_non_thinking_generation(self) -> None:
        source = Path("scripts/warm_ollama.sh").read_text(encoding="utf-8")

        self.assertIn('NUM_PREDICT="${OLLAMA_WARM_NUM_PREDICT:-1}"', source)
        self.assertIn('"think": False', source)


class CognitiveFailureResponseComposerTests(unittest.IsolatedAsyncioTestCase):
    async def test_quality_model_phrases_host_owned_failure_facts(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.failure_response_model = "gemma4:e2b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "smart, warm, and six years old", assistant
        )

        class FakeResponse:
            status = 200

            async def __aenter__(self) -> "FakeResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                return json.dumps(
                    {
                        "response": json.dumps(
                            {"text": "我刚才没查成功，不能乱说。你再问我一次吧。"},
                            ensure_ascii=False,
                        ),
                        "done_reason": "stop",
                    },
                    ensure_ascii=False,
                )

        class FakeSession:
            def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
                self.url = url
                self.payload = json
                return FakeResponse()

        session = FakeSession()
        assistant.get_http_session = MethodType(
            lambda self: asyncio.sleep(0, result=session), assistant
        )
        assistant.session_log = MethodType(lambda self, *args: None, assistant)
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="unsupported",
            fallback_reason="deep planner contract failed",
            metadata={
                "failure_stage": "deep_planner",
                "failure_class": "structured_output_validation",
                "retryable": True,
            },
        )
        decision = RouteDecision(
            route="tool",
            intent="weather.lookup",
            confidence=0.95,
            metadata={},
        )

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            decision,
            user_text="重庆今天热不热？",
            session_id="failure-style",
        )

        assert response is not None
        self.assertEqual(response.metadata["source"], "llm_cognitive_failure_response")
        self.assertEqual(response.metadata["failure_response_model"], "gemma4:e2b")
        self.assertEqual(
            response.metadata["failure_facts"]["failure_stage"],
            "deep_planner",
        )
        spoken = " ".join(item.text for item in response.speech)
        self.assertIn("不能乱说", spoken)
        self.assertNotIn("查询服务", spoken)
        self.assertEqual(session.payload["model"], "gemma4:e2b")
        self.assertFalse(session.payload["think"])
        self.assertIn("verified_result_available", session.payload["prompt"])


    async def test_quality_model_phrases_post_execution_failure_facts(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.failure_response_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "smart, warm, and six years old", assistant
        )

        class FakeResponse:
            status = 200

            async def __aenter__(self) -> "FakeResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                return json.dumps(
                    {
                        "response": json.dumps(
                            {
                                "text": (
                                    "刚才两个动作都没成功，我没有硬来。你再说一次吧。"
                                )
                            },
                            ensure_ascii=False,
                        ),
                        "done_reason": "stop",
                    },
                    ensure_ascii=False,
                )

        class FakeSession:
            def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
                self.url = url
                self.payload = json
                return FakeResponse()

        session = FakeSession()
        assistant.get_http_session = MethodType(
            lambda self: asyncio.sleep(0, result=session), assistant
        )
        assistant.session_log = MethodType(lambda self, *args: None, assistant)
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="robot_action",
            metadata={},
        )
        decision = RouteDecision(
            route="robot_action",
            intent="execution_outcome_failure",
            confidence=1.0,
            metadata={},
        )
        facts = {
            "route": "robot_action",
            "failure_stage": "skill_execution",
            "failure_class": "provider_execution_failed",
            "execution_started": True,
            "verified_result_available": False,
            "retryable": True,
            "goal_statuses": ["failed", "failed"],
        }

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            decision,
            user_text="边走边眨眼睛。",
            session_id="execution-failure-style",
            trusted_failure_facts=facts,
            response_source="llm_execution_failure_response",
        )

        assert response is not None
        self.assertEqual(
            response.metadata["source"],
            "llm_execution_failure_response",
        )
        self.assertTrue(
            response.metadata["failure_facts"]["execution_started"]
        )
        self.assertIn(
            "were attempted but did not complete",
            session.payload["prompt"],
        )
        self.assertIn("没有硬来", " ".join(item.text for item in response.speech))

    async def test_location_not_found_reason_reaches_grounded_failure_composer(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.failure_response_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "smart, warm, and six years old", assistant
        )

        class FakeResponse:
            status = 200

            async def __aenter__(self) -> "FakeResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                return json.dumps(
                    {
                        "response": json.dumps(
                            {
                                "text": "天气网站没认出内乡县，我再试一次。"
                            },
                            ensure_ascii=False,
                        ),
                        "done_reason": "stop",
                    },
                    ensure_ascii=False,
                )

        class FakeSession:
            def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
                self.url = url
                self.payload = json
                return FakeResponse()

        session = FakeSession()
        assistant.get_http_session = MethodType(
            lambda self: asyncio.sleep(0, result=session), assistant
        )
        assistant.session_log = MethodType(lambda self, *args: None, assistant)
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="tool",
            metadata={},
        )
        decision = RouteDecision(
            route="tool",
            intent="execution_outcome_failure",
            confidence=1.0,
            metadata={},
        )

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            decision,
            user_text="河南省内乡县现在下雨了没有？",
            session_id="location-not-found-style",
            trusted_failure_facts={
                "route": "tool",
                "failure_stage": "skill_execution",
                "failure_class": "provider_execution_failed",
                "execution_started": True,
                "verified_result_available": False,
                "retryable": True,
                "reason_codes": ["location_not_found"],
            },
            response_source="llm_execution_failure_response",
        )

        assert response is not None
        self.assertIn("location_not_found", session.payload["prompt"])
        self.assertIn("could not identify the requested place", session.payload["prompt"])
        self.assertIn("没认出内乡县", " ".join(item.text for item in response.speech))

    async def test_failure_response_composer_rejects_language_drift(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.failure_response_model = "gemma4:e2b"
        assistant.ollama_model = "qwen3:4b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant._direct_llm_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._direct_llm_mind_summary = MethodType(
            lambda self: "smart, warm, and six years old", assistant
        )

        class FakeResponse:
            status = 200

            async def __aenter__(self) -> "FakeResponse":
                return self

            async def __aexit__(self, *args: Any) -> None:
                del args

            async def text(self) -> str:
                return json.dumps(
                    {
                        "response": json.dumps(
                            {
                                "text": (
                                    "抱歉，I could not complete the lookup correctly, "
                                    "so please try the request again."
                                )
                            },
                            ensure_ascii=False,
                        ),
                        "done_reason": "stop",
                    },
                    ensure_ascii=False,
                )

        session = type(
            "FakeSession",
            (),
            {"post": lambda self, url, json: FakeResponse()},
        )()
        assistant.get_http_session = MethodType(
            lambda self: asyncio.sleep(0, result=session), assistant
        )
        assistant.session_log = MethodType(lambda self, *args: None, assistant)
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="unsupported",
            metadata={
                "failure_stage": "deep_planner",
                "failure_class": "structured_output_validation",
                "retryable": True,
            },
        )
        decision = RouteDecision(
            route="tool",
            intent="weather.lookup",
            confidence=0.95,
            metadata={},
        )

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            decision,
            user_text="重庆今天热不热？",
            session_id="failure-language",
        )

        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
