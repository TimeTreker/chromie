from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.planner_reentry import incremental_execution_outcome_truth
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
)
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
)
from shared.chromie_contracts.interaction import InteractionResponse, InteractionSpeech
from shared.chromie_contracts.plan import (
    CanonicalPlan,
    CanonicalPlanStep,
    ExecuteGoalPlanOutcome,
    GoalSatisfactionAssessment,
    RespondGoalPlanOutcome,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.situation import CognitiveOpportunity
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
    def test_incremental_truth_marks_one_completed_step_of_multi_step_goal_partial(self) -> None:
        goal_id = "goal-compound"
        plan = CanonicalPlan(
            plan_id="compound",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=1.0,
            goal_ids=[goal_id],
            steps=[
                CanonicalPlanStep(
                    step_id="first",
                    capability_id="chromie.test.first",
                    args={},
                    source_goal_ids=[goal_id],
                ),
                CanonicalPlanStep(
                    step_id="second",
                    capability_id="chromie.test.second",
                    args={},
                    source_goal_ids=[goal_id],
                ),
            ],
            goal_outcomes=[
                ExecuteGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="execute",
                    coverage="complete",
                    step_ids=["first", "second"],
                )
            ],
            goal_satisfaction=GoalSatisfactionAssessment(
                score=1.0,
                status="exact",
                satisfied_goal_ids=[goal_id],
            ),
        )
        truth = incremental_execution_outcome_truth(
            evidence=ExecutionEvidence(
                evidence_id="first-result",
                request_id="first-request",
                step_id="first",
                capability_id="chromie.test.first",
                source_goal_ids=[goal_id],
                status="completed",
                reported_status="completed",
            ),
            plan=plan,
        )

        self.assertEqual(truth["aggregate_status"], "partial")
        self.assertEqual(truth["goal_outcomes"][0]["status"], "partial")
        self.assertEqual(
            truth["goal_outcomes"][0]["unresolved_step_ids"], ["second"]
        )

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
                            "output_mode": "information",
                            "relationship": "new",
                            "confidence": 1.0,
                        },
                        {
                            "local_ref": "blink-result",
                            "outcome": "Blink twice.",
                            "bindings": {"count": 2},
                            "output_mode": "body_action",
                            "relationship": "new",
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
                            "source_text": "Check the weather and blink twice.",
                        },
                        {
                            "goal_id": "goal-excluded-blink",
                            "source_responsibility_refs": ["blink-result"],
                            "source_text": "Check the weather and blink twice.",
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
        self.assertEqual(request.planner_reentry_scope.goal_ids, (goal_id,))
        self.assertEqual(
            request.planner_reentry_scope.trigger,
            "post_execution",
        )
        self.assertEqual(
            request.planner_reentry_scope.source_plan_id,
            original.plan_id,
        )
        self.assertEqual(request.context["result_evidence_reentry"]["source_goal_ids"], [goal_id])
        self.assertEqual(request.context["trusted_terminal_evidence"][0]["evidence_id"], "weather-result")
        self.assertEqual(
            [
                item["local_ref"]
                for item in request.context["core_interpretation"]["responsibilities"]
            ],
            ["weather-result"],
        )
        self.assertEqual(
            [
                item["goal_id"]
                for item in request.context["goal_association_resolution"]["new_goals"]
            ],
            [goal_id],
        )
        self.assertNotIn(
            "source_text",
            request.context["goal_association_resolution"]["new_goals"][0],
        )

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


    def test_non_evidence_time_opportunity_can_reenter_without_false_post_evidence_truth(self) -> None:
        goal_id = "goal-reminder"
        satisfaction = GoalSatisfactionAssessment(
            score=1.0,
            status="exact",
            satisfied_goal_ids=[goal_id],
        )
        replanned = CanonicalPlan(
            plan_id="reminder-due-response",
            planner_tier="fast",
            disposition="respond",
            coverage="complete",
            confidence=0.98,
            goal_ids=[goal_id],
            response_text="It is time.",
            goal_outcomes=[
                RespondGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="respond",
                    coverage="complete",
                    response_text="It is time.",
                    satisfaction=satisfaction,
                )
            ],
            goal_satisfaction=satisfaction,
        )

        class Client:
            request = None

            async def resolve_fast_plan(self, _session, *, request, timeout_ms):
                self.request = request
                return replanned

        class Adapter:
            async def build_planner_owned_response(self, **_kwargs):
                return InteractionResponse(
                    interaction_id="reminder-due",
                    status="ok",
                    speech=[InteractionSpeech(text="It is time.")],
                )

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.agent_client = Client()
        assistant.cognitive_runtime_policy = SimpleNamespace(
            fast_planner_timeout_ms=3000,
            deep_planner_timeout_ms=6000,
        )
        assistant.cognitive_runtime = SimpleNamespace(
            adapter=Adapter(), interaction_ledger=None
        )
        assistant.session_log = lambda *_args, **_kwargs: None
        assistant.build_context = lambda _sid: {"history": []}
        assistant._goal_driven_authority_context = (
            lambda context, **_kwargs: context
        )

        async def get_session():
            return object()

        assistant.get_http_session = get_session
        opportunity = CognitiveOpportunity.create(
            trigger="time_condition",
            goal_ids=[goal_id],
            reason_codes=["planner_time_condition"],
            recommended_cognition="fast",
        )
        responsibility = CognitiveResponsibilityProposal(
            local_ref="resp-reminder",
            outcome="Remind the user at the requested time.",
            output_mode="stateful_effect",
            relationship="new",
            confidence=1.0,
        )

        response = asyncio.run(
            assistant._planner_state_reentry_response(
                source_response=None,
                canonical_plan=None,
                user_request="Remind me later.",
                language="en-US",
                goal_ids=[goal_id],
                evidence_goal_ids=[],
                evidence_refs=[],
                session_id=None,
                phase="time_condition_reentry",
                context_updates={
                    "cognitive_opportunity": opportunity.prompt_projection(),
                    "time_condition": {"condition_id": "condition-reminder"},
                },
                fast_workflow_stage="fast_planner_time_condition_reentry",
                deep_workflow_stage="planner_deep_pass_time_condition_reentry",
                response_source="fast_planner_time_condition_reentry",
                responsibilities_override=[responsibility],
            )
        )

        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(
            response.metadata["planner_state_reentry_ref"],
            opportunity.opportunity_id,
        )
        self.assertEqual(response.metadata["evidence_refs"], [])
        self.assertNotIn("truth_stage", response.speech[0].metadata)
        self.assertNotIn("evidence_refs", response.speech[0].metadata)
        self.assertEqual(
            assistant.agent_client.request.context["cognitive_opportunity"]["trigger"],
            "time_condition",
        )

    def test_slow_situation_opportunity_enters_deep_planner_without_fast_pass(self) -> None:
        goal_id = "goal-recover"
        satisfaction = GoalSatisfactionAssessment(
            score=1.0,
            status="exact",
            satisfied_goal_ids=[goal_id],
        )
        replanned = CanonicalPlan(
            plan_id="recover-deep-response",
            planner_tier="deep",
            disposition="respond",
            coverage="complete",
            confidence=0.98,
            goal_ids=[goal_id],
            response_text="I need to revise the approach.",
            goal_outcomes=[
                RespondGoalPlanOutcome(
                    goal_id=goal_id,
                    disposition="respond",
                    coverage="complete",
                    response_text="I need to revise the approach.",
                    satisfaction=satisfaction,
                )
            ],
            goal_satisfaction=satisfaction,
        )

        class Client:
            fast_calls = 0
            deep_calls = 0

            async def resolve_fast_plan(self, _session, *, request, timeout_ms):
                self.fast_calls += 1
                raise AssertionError("slow readiness must not spend a Fast Planner pass")

            async def resolve_deep_plan(self, _session, *, request, timeout_ms):
                self.deep_calls += 1
                self.request = request
                return replanned

        class Adapter:
            async def build_planner_owned_response(self, **_kwargs):
                return InteractionResponse(
                    interaction_id="recover-deep",
                    status="ok",
                    speech=[InteractionSpeech(text="I need to revise the approach.")],
                )

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.agent_client = Client()
        assistant.cognitive_runtime_policy = SimpleNamespace(
            fast_planner_timeout_ms=3000,
            deep_planner_timeout_ms=6000,
        )
        assistant.cognitive_runtime = SimpleNamespace(
            adapter=Adapter(), interaction_ledger=None
        )
        assistant.session_log = lambda *_args, **_kwargs: None
        assistant.build_context = lambda _sid: {"history": []}
        assistant._goal_driven_authority_context = (
            lambda context, **_kwargs: context
        )

        async def get_session():
            return object()

        assistant.get_http_session = get_session
        opportunity = CognitiveOpportunity.create(
            trigger="situation_revision",
            goal_ids=[goal_id],
            reason_codes=["trusted_situation_revision"],
            recommended_cognition="slow",
        )
        responsibility = CognitiveResponsibilityProposal(
            local_ref="resp-recover",
            outcome="Continue the responsibility safely after the blockage.",
            output_mode="stateful_effect",
            relationship="new",
            confidence=1.0,
        )

        response = asyncio.run(
            assistant._planner_state_reentry_response(
                source_response=None,
                canonical_plan=None,
                user_request="Keep going when you can.",
                language="en-US",
                goal_ids=[goal_id],
                evidence_goal_ids=[],
                evidence_refs=[],
                session_id=None,
                phase="situation_revision_reentry",
                context_updates={
                    "cognitive_opportunity": opportunity.prompt_projection(),
                },
                fast_workflow_stage="fast_planner_situation_revision_reentry",
                deep_workflow_stage="planner_deep_pass_situation_revision_reentry",
                response_source="planner_situation_revision_reentry",
                responsibilities_override=[responsibility],
            )
        )

        self.assertIsNotNone(response)
        self.assertEqual(assistant.agent_client.fast_calls, 0)
        self.assertEqual(assistant.agent_client.deep_calls, 1)
        self.assertEqual(
            assistant.agent_client.request.context["cognitive_opportunity"][
                "recommended_cognition"
            ],
            "slow",
        )

    def test_aggregate_reentry_exposes_failed_terminal_truth_without_host_wording(self) -> None:
        goal_id = "goal-motion"
        original = CanonicalPlan(
            plan_id="motion-plan",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.98,
            goal_ids=[goal_id],
            steps=[
                CanonicalPlanStep(
                    step_id="move",
                    capability_id="soridormi.motion.walk",
                    args={"duration_s": 1},
                    source_goal_ids=[goal_id],
                )
            ],
        )
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-motion-failed",
            turn_id="turn-motion",
            interaction_id="interaction-motion",
            canonical_plan_id=original.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(original),
            canonical_goal_ids=[goal_id],
            aggregate_status="failed",
            evidence=[
                ExecutionEvidence(
                    evidence_id="motion-failed",
                    request_id="request-motion",
                    step_id="move",
                    capability_id="soridormi.motion.walk",
                    source_goal_ids=[goal_id],
                    status="failed",
                    reported_status="failed",
                    reason_code="provider_failed",
                )
            ],
            goal_outcomes=[
                GoalExecutionOutcome(
                    goal_id=goal_id,
                    status="failed",
                    step_ids=["move"],
                    evidence_ids=["motion-failed"],
                    unresolved_step_ids=["move"],
                    reason_codes=["provider_failed"],
                )
            ],
        )
        source = InteractionResponse(
            interaction_id="interaction-motion",
            status="ok",
            metadata={
                "language": "zh-CN",
                "user_turn_envelope": {
                    "normalized_input": {
                        "text": "往前走一下",
                        "language": "zh-CN",
                    }
                },
            },
        )
        captured: dict[str, object] = {}

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.session_log = lambda *_args, **_kwargs: None

        async def capture(**kwargs):
            captured.update(kwargs)
            return InteractionResponse(interaction_id="planner-result", status="ok")

        assistant._planner_state_reentry_response = capture
        response = asyncio.run(
            assistant._plan_evidence_bound_capability_result_response(
                source_response=source,
                bundle=bundle,
                plan=original,
                session_id="session",
            )
        )

        self.assertIsNotNone(response)
        evidence = captured["repeat_check_evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].status, "failed")
        self.assertEqual(evidence[0].data, {})
        truth = captured["context_updates"]["trusted_execution_outcome"]
        self.assertEqual(truth["aggregate_status"], "failed")
        self.assertEqual(truth["goal_outcomes"][0]["status"], "failed")
        self.assertNotIn("speech", truth)

    def test_aggregate_reentry_excludes_already_consumed_sibling_evidence_and_goal(self) -> None:
        first_goal = "goal-walk"
        second_goal = "goal-blink"
        original = CanonicalPlan(
            plan_id="compound-plan",
            planner_tier="fast",
            disposition="execute",
            coverage="complete",
            confidence=0.98,
            goal_ids=[first_goal, second_goal],
            steps=[
                CanonicalPlanStep(
                    step_id="walk",
                    capability_id="soridormi.walk_forward",
                    args={"duration_s": 1},
                    source_goal_ids=[first_goal],
                ),
                CanonicalPlanStep(
                    step_id="blink",
                    capability_id="soridormi.blink_eyes",
                    args={"count": 2},
                    source_goal_ids=[second_goal],
                ),
            ],
            goal_outcomes=[
                ExecuteGoalPlanOutcome(
                    goal_id=first_goal,
                    disposition="execute",
                    coverage="complete",
                    step_ids=["walk"],
                ),
                ExecuteGoalPlanOutcome(
                    goal_id=second_goal,
                    disposition="execute",
                    coverage="complete",
                    step_ids=["blink"],
                ),
            ],
            goal_satisfaction=GoalSatisfactionAssessment(
                score=1.0,
                status="exact",
                satisfied_goal_ids=[first_goal, second_goal],
            ),
        )
        evidence_rows = [
            ExecutionEvidence(
                evidence_id="walk-failed",
                request_id="request-walk",
                step_id="walk",
                capability_id="soridormi.walk_forward",
                source_goal_ids=[first_goal],
                status="failed",
                reported_status="failed",
                reason_code="provider_failed",
            ),
            ExecutionEvidence(
                evidence_id="blink-failed",
                request_id="request-blink",
                step_id="blink",
                capability_id="soridormi.blink_eyes",
                source_goal_ids=[second_goal],
                status="failed",
                reported_status="failed",
                reason_code="provider_failed",
            ),
        ]
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-compound",
            turn_id="turn-compound",
            interaction_id="interaction-compound",
            canonical_plan_id=original.plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint(original),
            canonical_goal_ids=[first_goal, second_goal],
            aggregate_status="failed",
            evidence=evidence_rows,
            goal_outcomes=[
                GoalExecutionOutcome(
                    goal_id=first_goal,
                    status="failed",
                    step_ids=["walk"],
                    evidence_ids=["walk-failed"],
                    unresolved_step_ids=["walk"],
                    reason_codes=["provider_failed"],
                ),
                GoalExecutionOutcome(
                    goal_id=second_goal,
                    status="failed",
                    step_ids=["blink"],
                    evidence_ids=["blink-failed"],
                    unresolved_step_ids=["blink"],
                    reason_codes=["provider_failed"],
                ),
            ],
        )
        source = InteractionResponse(
            interaction_id="interaction-compound",
            status="ok",
            metadata={
                "language": "en-US",
                "incremental_planner_reentry_evidence_ids": ["walk-failed"],
                "user_turn_envelope": {
                    "normalized_input": {
                        "text": "Walk, then blink twice.",
                        "language": "en-US",
                    }
                },
            },
        )
        captured: dict[str, object] = {}
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.session_log = lambda *_args, **_kwargs: None

        async def capture(**kwargs):
            captured.update(kwargs)
            return InteractionResponse(interaction_id="planner-result", status="ok")

        assistant._planner_state_reentry_response = capture
        response = asyncio.run(
            assistant._plan_evidence_bound_capability_result_response(
                source_response=source,
                bundle=bundle,
                plan=original,
                session_id="session",
            )
        )

        self.assertIsNotNone(response)
        self.assertEqual(captured["goal_ids"], [second_goal])
        self.assertEqual(captured["evidence_refs"], ["blink-failed"])
        context = captured["context_updates"]
        self.assertEqual(
            [item["evidence_id"] for item in context["trusted_execution_outcome"]["evidence"]],
            ["blink-failed"],
        )
        self.assertEqual(
            [item["goal_id"] for item in context["trusted_execution_outcome"]["goal_outcomes"]],
            [second_goal],
        )
        self.assertEqual(
            [item["evidence_id"] for item in context["execution_outcome_bundle"]["evidence"]],
            ["blink-failed"],
        )

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
