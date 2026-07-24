from __future__ import annotations

import hashlib
import unittest
from typing import Any

from agent.app.tool_result_interpreter import ToolResultInterpreter
from orchestrator.orchestrator import VoiceAssistant
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ModelObservation,
)
from shared.chromie_contracts.interaction import InteractionResponse
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
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs) -> dict[str, Any]:
        del kwargs
        self.prompts.append(prompt)
        return dict(self.payload)


class ToolResultInterpreterTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _request(*, fallback: str = "") -> ToolResultInterpretationRequest:
        data = {
            "location": "重庆",
            "temperature_c": 37.0,
            "apparent_temperature_c": 42.0,
            "wind_speed_kmh": 9.0,
            "precipitation_probability": 18.0,
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
                    "skill_id": "chromie.weather.lookup",
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
                    skill_id="chromie.weather.lookup",
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


if __name__ == "__main__":
    unittest.main()
