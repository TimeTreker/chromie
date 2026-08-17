from __future__ import annotations

import asyncio
import json
import unittest
from types import MethodType
from typing import Any
from pathlib import Path

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.runtime.host_settings import HostSettingsSnapshot


class RuntimeReliabilityStage4Tests(unittest.TestCase):








    def test_warmup_uses_a_one_token_non_thinking_generation(self) -> None:
        source = Path("scripts/warm_ollama.sh").read_text(encoding="utf-8")

        self.assertIn('NUM_PREDICT="${OLLAMA_WARM_NUM_PREDICT:-1}"', source)
        self.assertIn('"think": False', source)


class CognitiveFailureResponseComposerTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _configure_model_generation(assistant: VoiceAssistant) -> None:
        assistant.host_settings = HostSettingsSnapshot.from_env(
            project_root=Path("/tmp"),
            environ={},
        )

    async def test_quality_model_phrases_host_owned_failure_facts(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.failure_response_model = "gemma4:e2b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._owner_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._owner_mind_summary = MethodType(
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
                                "text": "这次我还没有可靠结果，所以我先不乱说。",
                                "capability_state": "unknown",
                                "execution_state": "not_attempted",
                                "result_state": "not_observed",
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
            lane="unsupported",
            fallback_reason="deep planner contract failed",
            metadata={
                "failure_stage": "deep_planner",
                "failure_class": "structured_output_validation",
                "retryable": True,
            },
        )

        response = await assistant._compose_cognitive_failure_response(
            resolution,
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
        self.assertIn("不乱说", spoken)
        self.assertNotIn("查询服务", spoken)
        self.assertEqual(session.payload["model"], "gemma4:e2b")
        self.assertFalse(session.payload["think"])
        self.assertIn("verified_result_available", session.payload["prompt"])
        self.assertEqual(
            response.metadata["failure_facts"]["capability_state"],
            "unknown",
        )
        self.assertEqual(
            response.metadata["failure_facts"]["execution_state"],
            "not_attempted",
        )
        self.assertEqual(
            response.metadata["failure_facts"]["result_state"],
            "not_observed",
        )



    async def test_pre_dispatch_selected_weather_capability_uses_user_facing_failure_composer(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.failure_response_model = "gemma4:e2b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._owner_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._owner_mind_summary = MethodType(
            lambda self: "smart, warm, and six years old", assistant
        )
        assistant.session_log = MethodType(lambda self, *args: None, assistant)

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
                                "text": "这次还没有可靠结果，我先不乱说。",
                                "capability_state": "available",
                                "execution_state": "not_attempted",
                                "result_state": "not_observed",
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
        resolution = CognitiveRuntimeResolution(
            mode="apply",
            status="error",
            lane="tool",
            fallback_reason="goal association contract failed",
            metadata={
                "failure_stage": "goal_association",
                "failure_class": "structured_output_validation",
                "failure_domain": "model_contract",
                "retryable": True,
            },
        )

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            user_text="帮我查一下重庆明天是晴天还是阴天。",
            session_id="weather-pre-dispatch",
            trusted_failure_facts={
                "selected_capability_ids": ["chromie.weather.lookup"],
                "execution_started": False,
                "verified_result_available": False,
                "retryable": True,
            },
        )

        assert response is not None
        spoken = " ".join(item.text for item in response.speech)
        self.assertEqual(response.metadata["source"], "llm_cognitive_failure_response")
        self.assertIn("还没有可靠结果", spoken)
        self.assertNotIn("安排", spoken)
        self.assertNotIn("不会", spoken)
        self.assertNotIn("没学会", spoken)
        self.assertIn("Do not expose internal planning, arrangement", session.payload["prompt"])
        self.assertNotIn('"failure_stage"', session.payload["prompt"])
        self.assertNotIn("structured_output_validation", session.payload["prompt"])
        self.assertNotIn("goal_association", session.payload["prompt"])
        self.assertIn('"capability_state": "available"', session.payload["prompt"])
        facts = response.metadata["failure_facts"]
        self.assertEqual(
            facts["selected_capability_ids"],
            ["chromie.weather.lookup"],
        )
        self.assertTrue(facts["capability_available_at_interpretation"])
        self.assertTrue(facts["failure_before_provider_dispatch"])
        self.assertFalse(facts["missing_ability"])
        self.assertFalse(facts["user_action_required"])
        self.assertEqual(facts["capability_state"], "available")
        self.assertEqual(facts["execution_state"], "not_attempted")
        self.assertEqual(facts["result_state"], "not_observed")
        self.assertEqual(
            session.payload["format"]["properties"]["capability_state"]["const"],
            "available",
        )

    async def test_quality_model_phrases_post_execution_failure_facts(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.failure_response_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._owner_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._owner_mind_summary = MethodType(
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
                                    "刚才两个动作都没成功，所以我没有硬来，请再说一次吧。"
                                ),
                                "capability_state": "unknown",
                                "execution_state": "attempted",
                                "result_state": "not_observed",
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
        self._configure_model_generation(assistant)
        assistant.failure_response_model = "gemma4:12b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._owner_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._owner_mind_summary = MethodType(
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
                                "text": "天气网站没认出内乡县，我再试一次。",
                                "capability_state": "unknown",
                                "execution_state": "attempted",
                                "result_state": "not_observed",
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

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            user_text="河南省内乡县现在下雨了没有？",
            session_id="location-not-found-style",
            trusted_failure_facts={
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

    async def test_missing_ability_failure_state_preserves_understanding_without_execution(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.failure_response_model = "gemma4:e2b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._owner_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._owner_mind_summary = MethodType(
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
                                    "我知道你想找附近好吃的地方，不过这个我现在还不会查，对不起呀。"
                                ),
                                "capability_state": "unavailable",
                                "execution_state": "not_attempted",
                                "result_state": "not_observed",
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
            lane="chat",
            metadata={
                "failure_stage": "goal_interpretation",
                "failure_class": "missing_ability",
            },
        )

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            user_text="帮我找重庆龙兴天街附近好吃的餐厅。",
            session_id="missing-ability-state",
            trusted_failure_facts={
                "missing_ability": True,
                "execution_started": False,
                "verified_result_available": False,
            },
        )

        self.assertIsNotNone(response)
        assert response is not None
        facts = response.metadata["failure_facts"]
        self.assertTrue(facts["user_input_understood"])
        self.assertTrue(facts["missing_ability"])
        self.assertEqual(facts["capability_state"], "unavailable")
        self.assertEqual(facts["execution_state"], "not_attempted")
        self.assertEqual(facts["result_state"], "not_observed")
        self.assertEqual(facts["provider_request_count"], 0)

    async def test_failure_response_composer_rejects_semantic_state_drift(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.failure_response_model = "gemma4:e2b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant.normalize_tts_candidate = MethodType(
            lambda self, text: str(text).strip(), assistant
        )
        assistant.is_valid_tts_text = MethodType(
            lambda self, text: bool(str(text).strip()), assistant
        )
        assistant._owner_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._owner_mind_summary = MethodType(
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
                                "text": "我没找到附近好吃的店，对不起呀。",
                                "capability_state": "unavailable",
                                "execution_state": "attempted",
                                "result_state": "not_observed",
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
            lane="chat",
            metadata={
                "failure_stage": "goal_interpretation",
                "failure_class": "missing_ability",
            },
        )

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            user_text="帮我找重庆龙兴天街附近好吃的餐厅。",
            session_id="failure-state-drift",
        )

        self.assertIsNone(response)

    async def test_failure_response_composer_rejects_language_drift(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        self._configure_model_generation(assistant)
        assistant.failure_response_model = "gemma4:e2b"
        assistant.ollama_model = "qwen3:4b"
        assistant.llm_url = "http://localhost:11434/api/generate"
        assistant._owner_identity_json = MethodType(
            lambda self: '{"name":"Chromie"}', assistant
        )
        assistant._owner_mind_summary = MethodType(
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
                                ),
                                "capability_state": "unknown",
                                "execution_state": "not_attempted",
                                "result_state": "not_observed",
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

        response = await assistant._compose_cognitive_failure_response(
            resolution,
            user_text="重庆今天热不热？",
            session_id="failure-language",
        )

        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
