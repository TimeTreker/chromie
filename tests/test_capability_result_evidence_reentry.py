from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from orchestrator.orchestrator import VoiceAssistant
from shared.chromie_contracts.interaction import InteractionResponse, InteractionSpeech
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    CanonicalPlanStep,
    GoalSatisfactionAssessment,
    RespondGoalPlanOutcome,
)
from shared.chromie_contracts.tool_result import (
    ToolResultEvidence,
    canonical_value_sha256,
)


async def _planner_evidence_reentry(
    assistant: VoiceAssistant,
    *,
    source_response: InteractionResponse,
    canonical_plan: CanonicalPlan,
    user_request: str,
    language: str,
    goal_ids: list[str],
    evidence: list[ToolResultEvidence],
    session_id: str | None,
    phase: str,
):
    evidence_refs = [item.evidence_id for item in evidence]
    return await assistant._planner_state_reentry_response(
        source_response=source_response,
        canonical_plan=canonical_plan,
        user_request=user_request,
        language=language,
        goal_ids=goal_ids,
        evidence_goal_ids=goal_ids,
        evidence_refs=evidence_refs,
        session_id=session_id,
        phase=phase,
        context_updates={
            "trusted_terminal_evidence": [
                item.model_dump(mode="json") for item in evidence
            ],
            "result_evidence_refs": evidence_refs,
            "result_evidence_reentry": {
                "phase": phase,
                "source_goal_ids": goal_ids,
                "evidence_refs": evidence_refs,
                "planner_authority": "planner",
            },
        },
        fast_workflow_stage="fast_planner_evidence_reentry",
        deep_workflow_stage="planner_deep_pass_evidence_reentry",
        response_source="fast_planner_evidence_reentry",
        repeat_check_evidence=evidence,
    )


class PlannerEvidenceReentryContractTests(unittest.TestCase):
    def test_terminal_evidence_is_digest_bound(self) -> None:
        data = {"location": "重庆", "rain_probability": 10}
        evidence = ToolResultEvidence(
            evidence_id="weather-result",
            tool_id="chromie.weather.lookup",
            status="completed",
            data=data,
            output_sha256=canonical_value_sha256(data),
        )
        self.assertEqual(evidence.evidence_id, "weather-result")

    def test_host_reentry_uses_fast_planner_and_preserves_goal_binding(self) -> None:
        goal_id = "goal-weather"
        satisfaction = GoalSatisfactionAssessment(
            score=1.0,
            status="exact",
            satisfied_goal_ids=[goal_id],
        )
        replanned = CanonicalPlan(
            plan_id="result-answer",
            planner_tier="fast",
            disposition="respond",
            coverage="complete",
            confidence=0.98,
            goal_ids=[goal_id],
            response_text="上午不会下雨。",
            goal_outcomes=[
                RespondGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="respond",
                    coverage="complete",
                    response_text="上午不会下雨。",
                    satisfaction=satisfaction,
                )
            ],
            goal_satisfaction=satisfaction,
        )
        original = CanonicalPlan(
            plan_id="weather-read",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.98,
            goal_ids=[goal_id],
            steps=[
                CanonicalPlanStep(
                    step_id="lookup",
                    capability_id="chromie.weather.lookup",
                    args={"location": "重庆"},
                    source_goal_ids=[goal_id],
                )
            ],
        )

        class Client:
            request = None

            async def resolve_fast_plan(self, _session, *, request, timeout_ms):
                self.request = request
                return replanned

        class Adapter:
            async def build_planner_owned_response(self, **_kwargs):
                return InteractionResponse(
                    interaction_id="answer",
                    status="ok",
                    speech=[InteractionSpeech(text="上午不会下雨。")],
                )

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.agent_client = Client()
        assistant.cognitive_runtime_policy = SimpleNamespace(fast_planner_timeout_ms=3000)
        assistant.cognitive_runtime = SimpleNamespace(
            adapter=Adapter(), interaction_ledger=None
        )
        assistant.session_log = lambda *_args, **_kwargs: None
        assistant.build_context = lambda _sid: {"history": []}

        async def get_session():
            return object()

        assistant.get_http_session = get_session
        data = {"location": "重庆", "rain_probability": 10}
        evidence = ToolResultEvidence(
            evidence_id="weather-result",
            tool_id="chromie.weather.lookup",
            status="completed",
            data=data,
            output_sha256=canonical_value_sha256(data),
        )
        source = InteractionResponse(
            interaction_id="weather",
            status="ok",
            metadata={
                "goal_interpretation": {
                    "responsibilities": [
                        {
                            "local_ref": "weather-result",
                            "outcome": "Determine whether rain is expected this morning.",
                            "bindings": {},
                            "output_mode": "capability_work",
                            "relationship": "new",
                            "completion_requires_work": True,
                            "completion_requires_fresh_evidence": True,
                            "confidence": 1.0,
                        }
                    ]
                },
                "goal_association": {
                    "associations": [],
                    "new_goals": [
                        {
                            "goal_id": goal_id,
                            "source_responsibility_refs": ["weather-result"],
                        }
                    ],
                },
            },
        )

        response = asyncio.run(
            _planner_evidence_reentry(assistant,
                source_response=source,
                canonical_plan=original,
                user_request="今天上午会下雨吗？",
                language="zh-CN",
                goal_ids=[goal_id],
                evidence=[evidence],
                session_id="session",
                phase="post_execution",
            )
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.speech[0].metadata["truth_stage"], "post_evidence")
        self.assertEqual(response.speech[0].metadata["evidence_refs"], ["weather-result"])
        request = assistant.agent_client.request
        self.assertEqual(request.context["result_evidence_reentry"]["source_goal_ids"], [goal_id])
        self.assertEqual(request.context["trusted_terminal_evidence"][0]["evidence_id"], "weather-result")

        assistant._turn_speech_events = {
            "session": [
                {
                    "event_id": "speech-event-existing",
                    "session_id": "session",
                    "status": "playback_started",
                    "text": "上午不会下雨。",
                }
            ]
        }
        duplicate = asyncio.run(
            _planner_evidence_reentry(assistant,
                source_response=source,
                canonical_plan=original,
                user_request="今天上午会下雨吗？",
                language="zh-CN",
                goal_ids=[goal_id],
                evidence=[evidence],
                session_id="session",
                phase="post_execution",
            )
        )
        self.assertIsNotNone(duplicate)
        assert duplicate is not None
        self.assertEqual(duplicate.speech, [])

    def test_host_reentry_fails_closed_without_originating_responsibility(self) -> None:
        goal_id = "goal-weather"
        original = CanonicalPlan(
            plan_id="weather-read",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.98,
            goal_ids=[goal_id],
            steps=[
                CanonicalPlanStep(
                    step_id="lookup",
                    capability_id="chromie.weather.lookup",
                    args={"location": "重庆"},
                    source_goal_ids=[goal_id],
                )
            ],
        )

        class Client:
            called = False

            async def resolve_fast_plan(self, _session, *, request, timeout_ms):
                self.called = True
                raise AssertionError("Planner must not run without Responsibility provenance")

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.agent_client = Client()
        assistant.session_log = lambda *_args, **_kwargs: None

        def unexpected_context(_sid):
            raise AssertionError("Host must reject before rebuilding Planner context")

        assistant.build_context = unexpected_context
        data = {"location": "重庆", "rain_probability": 10}
        evidence = ToolResultEvidence(
            evidence_id="weather-result",
            tool_id="chromie.weather.lookup",
            status="completed",
            data=data,
            output_sha256=canonical_value_sha256(data),
        )
        source = InteractionResponse(
            interaction_id="weather",
            status="ok",
            metadata={
                "goal_association": {
                    "associations": [],
                    "new_goals": [
                        {
                            "goal_id": goal_id,
                            "source_responsibility_refs": ["weather-result"],
                        }
                    ],
                }
            },
        )

        response = asyncio.run(
            _planner_evidence_reentry(assistant,
                source_response=source,
                canonical_plan=original,
                user_request="今天上午会下雨吗？",
                language="zh-CN",
                goal_ids=[goal_id],
                evidence=[evidence],
                session_id="session",
                phase="post_execution",
            )
        )

        self.assertIsNone(response)
        self.assertFalse(assistant.agent_client.called)


if __name__ == "__main__":
    unittest.main()
