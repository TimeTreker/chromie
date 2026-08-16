from __future__ import annotations

import hashlib
import unittest
from typing import Any

from agent.app.tool_result_interpreter import ToolResultInterpreter
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.mind import MindManager
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ModelObservation,
)
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.mind import default_mind_profile
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import canonical_plan_fingerprint
from shared.chromie_contracts.tool_result import (
    ToolResultEvidence,
    ToolResultFactReference,
    ToolResultInterpretation,
    ToolResultInterpretationRequest,
    canonical_value_sha256,
)


class _ScriptedOllama:
    def __init__(self, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.payloads = list(payload) if isinstance(payload, list) else [payload]
        self.prompts: list[str] = []
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs) -> dict[str, Any]:
        self.prompts.append(prompt)
        self.calls.append(dict(kwargs))
        if not self.payloads:
            raise AssertionError("unexpected extra model call")
        return dict(self.payloads.pop(0))


class ToolResultInterpreterTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _request(*, fallback: str = "") -> ToolResultInterpretationRequest:
        data = {
            "location": "重庆",
            "temperature_c": 37.0,
            "apparent_temperature_c": 42.0,
            "wind_speed_kmh": 9.0,
            "precipitation_probability": 18.0,
            "condition": "雷雨",
        }
        return ToolResultInterpretationRequest(
            sid="tool-turn",
            user_request="今天重庆天热不热？",
            language="zh-CN",
            evidence=[
                ToolResultEvidence(
                    evidence_id="weather-result",
                    tool_id="chromie.weather.lookup",
                    status="completed",
                    data=data,
                    output_sha256=canonical_value_sha256(data),
                )
            ],
            fallback_response=fallback,
            max_spoken_chars=48,
            context={
                "identity": default_mind_profile().prompt_context()["identity"],
                "personality_expression": default_mind_profile().prompt_context()[
                    "personality_expression"
                ],
            },
        )

    async def test_decimal_temperature_does_not_consume_sentence_budget(self) -> None:
        ollama = _ScriptedOllama(
            {
                "spoken_response": "重庆现在非常热，体感温度达到了40.3℃。而且现在还在下雷雨呢。",
                "answer_mode": "direct",
                "selected_facts": [
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/apparent_temperature_c",
                    },
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/condition",
                    },
                ],
                "confidence": 0.98,
                "rationale": "The apparent temperature and condition directly answer the question.",
            }
        )
        request = self._request().model_copy(
            update={
                "evidence": [
                    self._request().evidence[0].model_copy(
                        update={
                            "data": {
                                **self._request().evidence[0].data,
                                "apparent_temperature_c": 40.3,
                            },
                            "output_sha256": canonical_value_sha256(
                                {
                                    **self._request().evidence[0].data,
                                    "apparent_temperature_c": 40.3,
                                }
                            ),
                        }
                    )
                ]
            }
        )

        result = await ToolResultInterpreter(ollama).interpret(request)

        self.assertEqual(result.status, "resolved")
        self.assertEqual(
            result.spoken_response,
            "重庆现在非常热，体感温度达到了40.3℃。而且现在还在下雷雨呢。",
        )

    async def test_selects_only_relevant_facts_and_keeps_complete_evidence(self) -> None:
        ollama = _ScriptedOllama(
            {
                "spoken_response": "很热，现在37℃，体感42℃。",
                "answer_mode": "direct",
                "selected_facts": [
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/temperature_c",
                    },
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/apparent_temperature_c",
                    },
                ],
                "confidence": 0.97,
                "rationale": "Temperature and apparent temperature answer the question.",
            }
        )

        result = await ToolResultInterpreter(ollama).interpret(self._request())

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.spoken_response, "很热，现在37℃，体感42℃。")
        self.assertEqual(len(result.selected_facts), 2)
        self.assertTrue(result.metadata["full_tool_result_retained"])
        self.assertNotIn("wind_speed", result.spoken_response)
        self.assertIn("Interpret trusted tool results", ollama.prompts[0])
        self.assertIn("owner-approved personality JSON", ollama.prompts[0])
        self.assertIn("Answer the user's actual question first", ollama.prompts[0])
        self.assertNotIn("customer-service", result.spoken_response)

    async def test_decoder_schema_enumerates_exact_evidence_pointers(self) -> None:
        ollama = _ScriptedOllama(
            {
                "spoken_response": "很热，现在37℃。",
                "answer_mode": "direct",
                "selected_facts": [
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/temperature_c",
                    }
                ],
                "confidence": 0.9,
                "rationale": "",
            }
        )
        result = await ToolResultInterpreter(ollama).interpret(self._request())
        self.assertEqual(result.status, "resolved")
        schema = ollama.calls[0]["response_format"]
        item_schema = schema["properties"]["selected_facts"]["items"]
        variant = item_schema["anyOf"][0]
        self.assertEqual(
            variant["properties"]["evidence_id"]["const"],
            "weather-result",
        )
        pointers = variant["properties"]["json_pointer"]["enum"]
        self.assertIn("/temperature_c", pointers)
        self.assertIn("/apparent_temperature_c", pointers)
        self.assertNotIn("/data/temperature_c", pointers)
        self.assertIn("available_scalar_json_pointers", ollama.prompts[0])
        self.assertIn("never add a /data prefix", ollama.prompts[0])

    async def test_rejects_unselected_numeric_claim_and_uses_bounded_fallback(self) -> None:
        ollama = _ScriptedOllama(
            {
                "spoken_response": "很热，现在37℃，降水概率80%。",
                "answer_mode": "direct",
                "selected_facts": [
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/temperature_c",
                    }
                ],
                "confidence": 0.9,
                "rationale": "",
            }
        )

        result = await ToolResultInterpreter(ollama).interpret(
            self._request(fallback="重庆很热，现在37℃，体感42℃。")
        )

        self.assertEqual(result.status, "fallback")
        self.assertEqual(result.spoken_response, "重庆很热，现在37℃，体感42℃。")

    async def test_over_budget_grounded_answer_fails_without_semantic_repair(self) -> None:
        ollama = _ScriptedOllama(
            [
                {
                    "spoken_response": "要带哦！重庆今天有雷雨。降雨概率很大。",
                    "answer_mode": "direct",
                    "selected_facts": [
                        {"evidence_id": "weather-result", "json_pointer": "/condition"},
                        {
                            "evidence_id": "weather-result",
                            "json_pointer": "/precipitation_probability",
                        },
                    ],
                    "confidence": 0.96,
                    "rationale": "Grounded but over the sentence budget.",
                },
                {
                    "spoken_response": "这份旧式修复输出不应被调用。",
                    "answer_mode": "direct",
                    "selected_facts": [
                        {"evidence_id": "weather-result", "json_pointer": "/condition"}
                    ],
                    "confidence": 1.0,
                    "rationale": "should not run",
                },
            ]
        )

        result = await ToolResultInterpreter(ollama).interpret(self._request())

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(len(ollama.calls), 1)
        self.assertFalse(result.metadata["dto_regeneration_attempted"])
        self.assertNotIn("contract_repair_attempted", result.metadata)

    async def test_does_not_classify_workflow_narration_with_phrase_rules(self) -> None:
        ollama = _ScriptedOllama(
            {
                "spoken_response": "请求的任务已完成。观测结果是37℃。",
                "answer_mode": "direct",
                "selected_facts": [
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/temperature_c",
                    }
                ],
                "confidence": 0.9,
                "rationale": "",
            }
        )

        result = await ToolResultInterpreter(ollama).interpret(self._request())

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.spoken_response, "请求的任务已完成。观测结果是37℃。")

    async def test_effectful_truth_audit_rejects_overclaim_without_rewriting(self) -> None:
        data = {
            "completed": True,
            "no_motion": True,
            "summary": "provider request completed without motion",
        }
        canonical_plan = CanonicalPlan(
            plan_id="plan-embodied-result",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.9,
            goal_ids=["goal-walk", "goal-water"],
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 2.0},
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-water",
                    "disposition": "unavailable",
                    "coverage": "complete",
                    "unresolved": ["No pickup capability."],
                },
            ],
        )
        request = ToolResultInterpretationRequest(
            sid="effectful-result",
            user_request="往前走，然后帮我拿杯水。",
            language="zh-CN",
            evidence=[
                ToolResultEvidence(
                    evidence_id="walk-result",
                    tool_id="soridormi.walk_forward",
                    status="completed",
                    data=data,
                    output_sha256=canonical_value_sha256(data),
                )
            ],
            max_spoken_chars=72,
            max_sentences=2,
            context={
                "canonical_plan_resolution": canonical_plan.model_dump(mode="json"),
                "effectful_result_review_required": True,
            },
        )
        candidate = {
            "spoken_response": "都完成了，而且我保证很安全。",
            "answer_mode": "direct",
            "selected_facts": [
                {"evidence_id": "walk-result", "json_pointer": "/completed"}
            ],
            "confidence": 0.99,
            "rationale": "overclaim",
        }
        audit = {
            "violations": ["cross_goal_overclaim", "safety_guarantee"],
            "reason_summary": "The candidate exceeds observed evidence.",
        }
        ollama = _ScriptedOllama([candidate, audit])

        result = await ToolResultInterpreter(ollama).interpret(request)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(len(ollama.calls), 2)
        self.assertEqual(
            ollama.calls[1]["prompt_family"],
            "tool_result_interpreter.truth_audit",
        )
        self.assertIn("immutable ToolResultTruthAudit", ollama.prompts[1])
        self.assertNotIn("complete corrected ToolResultModelOutput", ollama.prompts[1])
        self.assertTrue(result.metadata["result_truth_audit_attempted"])

    async def test_effectful_truth_audit_rejects_unavailable_sibling_overclaim(self) -> None:
        walk_data = {"completed": True, "motion_observed": True}
        canonical_plan = CanonicalPlan(
            plan_id="plan-walk-sing-result",
            planner_tier="deep",
            disposition="mixed",
            coverage="complete",
            confidence=0.98,
            goal_ids=["goal-walk", "goal-sing"],
            steps=[
                {
                    "step_id": "walk",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15.0},
                    "source_goal_ids": ["goal-walk"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["walk"],
                },
                {
                    "goal_id": "goal-sing",
                    "disposition": "unavailable",
                    "coverage": "complete",
                    "unresolved": ["No qualified singing provider is available."],
                },
            ],
        )
        request = ToolResultInterpretationRequest(
            sid="effectful-mixed-vocal-result",
            user_request="往前走，同时唱歌。",
            language="zh-CN",
            evidence=[
                ToolResultEvidence(
                    evidence_id="walk-result",
                    tool_id="soridormi.walk_forward",
                    status="completed",
                    data=walk_data,
                    output_sha256=canonical_value_sha256(walk_data),
                )
            ],
            max_spoken_chars=72,
            max_sentences=2,
            context={
                "canonical_plan_resolution": canonical_plan.model_dump(mode="json"),
                "effectful_result_review_required": True,
            },
        )
        ollama = _ScriptedOllama(
            [
                {
                    "spoken_response": "走路和唱歌都完成啦！",
                    "answer_mode": "direct",
                    "selected_facts": [
                        {"evidence_id": "walk-result", "json_pointer": "/completed"}
                    ],
                    "confidence": 0.99,
                    "rationale": "overclaim",
                },
                {
                    "violations": ["cross_goal_overclaim"],
                    "reason_summary": "Singing is unavailable in the immutable Plan.",
                },
            ]
        )

        result = await ToolResultInterpreter(ollama).interpret(request)

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn('"goal_id":"goal-sing"', ollama.prompts[1])
        self.assertIn('"disposition":"unavailable"', ollama.prompts[1])

    async def test_effectful_truth_audit_accepts_without_rewriting(self) -> None:
        request = self._request().model_copy(
            update={
                "context": {
                    **self._request().context,
                    "effectful_result_review_required": True,
                }
            }
        )
        candidate = {
            "spoken_response": "很热，现在37℃。",
            "answer_mode": "direct",
            "selected_facts": [
                {"evidence_id": "weather-result", "json_pointer": "/temperature_c"}
            ],
            "confidence": 0.95,
            "rationale": "exact fact",
        }
        audit = {"violations": [], "reason_summary": "Grounded in selected evidence."}
        ollama = _ScriptedOllama([candidate, audit])

        result = await ToolResultInterpreter(ollama).interpret(request)

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.spoken_response, candidate["spoken_response"])
        self.assertEqual(len(ollama.calls), 2)
        self.assertTrue(result.metadata["result_truth_audit"]["accepted"])

    async def test_rejects_unknown_fact_pointer(self) -> None:
        ollama = _ScriptedOllama(
            {
                "spoken_response": "很热。",
                "answer_mode": "direct",
                "selected_facts": [
                    {
                        "evidence_id": "weather-result",
                        "json_pointer": "/not_present",
                    }
                ],
                "confidence": 0.8,
                "rationale": "",
            }
        )

        result = await ToolResultInterpreter(ollama).interpret(self._request())

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.spoken_response, "")


class _FakeToolResultAgentClient:
    async def interpret_tool_result(self, session, *, request, timeout_ms=None):
        del session, timeout_ms
        self.request = request
        return ToolResultInterpretation(
            status="resolved",
            spoken_response="很热，现在37℃，体感42℃。",
            answer_mode="direct",
            selected_facts=[
                ToolResultFactReference(
                    evidence_id="evidence-weather",
                    json_pointer="/temperature_c",
                ),
                ToolResultFactReference(
                    evidence_id="evidence-weather",
                    json_pointer="/apparent_temperature_c",
                ),
            ],
            confidence=0.96,
            rationale="Directly answers the comfort question.",
        )


class ToolResultHostIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_host_accepts_one_evidence_bound_spoken_summary(self) -> None:
        plan = CanonicalPlan(
            plan_id="plan-weather",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.98,
            goal_ids=["goal-weather"],
            goal_summary="Check whether Chongqing is hot.",
            steps=[
                {
                    "step_id": "step-weather",
                    "capability_id": "chromie.weather.lookup",
                    "source_goal_ids": ["goal-weather"],
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-weather"],
                }
            ],
        )
        data = {
            "temperature_c": 37.0,
            "apparent_temperature_c": 42.0,
            "wind_speed_kmh": 9.0,
        }
        encoded = str(data).encode("utf-8")
        observation = ModelObservation(
            status="available",
            data=data,
            schema_validated=True,
            output_sha256=hashlib.sha256(encoded).hexdigest(),
            output_size_bytes=len(encoded),
        )
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-weather",
            turn_id="turn-weather",
            interaction_id="interaction-weather",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(plan),
            canonical_goal_ids=["goal-weather"],
            aggregate_status="completed",
            evidence=[
                ExecutionEvidence(
                    evidence_id="evidence-weather",
                    request_id="request-weather",
                    step_id="step-weather",
                    capability_id="chromie.weather.lookup",
                    source_goal_ids=["goal-weather"],
                    status="completed",
                    observation=observation,
                )
            ],
            goal_outcomes=[
                GoalExecutionOutcome(
                    goal_id="goal-weather",
                    status="completed",
                    step_ids=["step-weather"],
                    evidence_ids=["evidence-weather"],
                    completed_step_ids=["step-weather"],
                )
            ],
        )
        source_response = InteractionResponse(
            interaction_id="interaction-weather",
            metadata={
                "language": "zh-CN",
                "user_turn_envelope": {
                    "normalized_input": {
                        "text": "今天重庆天热不热？",
                        "language": "zh-CN",
                    }
                },
            },
        )
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.agent_client = _FakeToolResultAgentClient()
        assistant.mind = MindManager(default_mind_profile())
        assistant.tool_result_interpreter_timeout_ms = 5500
        assistant.session_log = lambda *args, **kwargs: None

        async def get_http_session():
            return object()

        assistant.get_http_session = get_http_session

        response = await assistant._compose_evidence_bound_tool_result_response(
            source_response=source_response,
            bundle=bundle,
            plan=plan,
            session_id="tool-turn",
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(len(response.speech), 1)
        self.assertEqual(response.speech[0].text, "很热，现在37℃，体感42℃。")
        self.assertEqual(
            response.speech[0].metadata["source"],
            "evidence_bound_tool_result_interpretation",
        )
        self.assertEqual(
            len(assistant.agent_client.request.evidence[0].data),
            3,
        )
        self.assertTrue(response.metadata["full_tool_result_retained"])
        self.assertEqual(
            assistant.agent_client.request.context["canonical_plan_resolution"][
                "plan_id"
            ],
            plan.plan_id,
        )
        self.assertIn(
            "smart",
            assistant.agent_client.request.context["personality_expression"][
                "core_traits"
            ],
        )
        self.assertEqual(assistant.agent_client.request.max_spoken_chars, 72)
        self.assertEqual(assistant.agent_client.request.max_sentences, 2)


if __name__ == "__main__":
    unittest.main()
