from __future__ import annotations

import asyncio
import unittest
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_turn_closure import CognitiveTurnClosure
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.session import SessionTracker
from orchestrator.runtime.skill_runtime import (
    SkillDefinition,
    SkillRuntimeResult,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    SkillResult,
    output_schema_sha256,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)

_TEST_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "additionalProperties": False,
}


def _plan() -> CanonicalPlan:
    return CanonicalPlan(
        plan_id="plan-turn-closure",
        planner_tier="fast",
        disposition="execute",
        coverage="complete",
        confidence=0.96,
        goal_ids=["goal-first", "goal-second"],
        goal_summary="Run two independent test capabilities.",
        steps=[
            {
                "step_id": "step-first",
                "skill_id": "chromie.test.first",
                "args": {},
                "source_goal_ids": ["goal-first"],
            },
            {
                "step_id": "step-second",
                "skill_id": "chromie.test.second",
                "args": {},
                "source_goal_ids": ["goal-second"],
            },
        ],
        goal_outcomes=[
            {
                "goal_id": "goal-first",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["step-first"],
            },
            {
                "goal_id": "goal-second",
                "disposition": "execute",
                "coverage": "complete",
                "step_ids": ["step-second"],
            },
        ],
        goal_satisfaction={
            "score": 1.0,
            "status": "exact",
            "satisfied_goal_ids": ["goal-first", "goal-second"],
        },
    )


def _response(plan: CanonicalPlan) -> InteractionResponse:
    fingerprint = canonical_plan_fingerprint(plan)
    return InteractionResponse(
        interaction_id="interaction-turn-closure",
        skills=[
            {
                "request_id": "request-first",
                "skill_id": "chromie.test.first",
                "timing": "sequential",
                "committed_output_schema_sha256": output_schema_sha256(
                    _TEST_OUTPUT_SCHEMA
                ),
                "metadata": {
                    "source": "goal_driven_canonical_plan",
                    "canonical_plan_id": plan.plan_id,
                    "canonical_plan_fingerprint": fingerprint,
                    "step_id": "step-first",
                    "source_goal_ids": ["goal-first"],
                },
            },
            {
                "request_id": "request-second",
                "skill_id": "chromie.test.second",
                "timing": "sequential",
                "committed_output_schema_sha256": output_schema_sha256(
                    _TEST_OUTPUT_SCHEMA
                ),
                "metadata": {
                    "source": "goal_driven_canonical_plan",
                    "canonical_plan_id": plan.plan_id,
                    "canonical_plan_fingerprint": fingerprint,
                    "step_id": "step-second",
                    "source_goal_ids": ["goal-second"],
                },
            },
        ],
        metadata={
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "turn_id": "turn-closure",
            "language": "en-US",
            "planning_result": "composed_plan",
            "canonical_plan": plan.model_dump(mode="json"),
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": fingerprint,
        },
    )


class _EvidenceRecorder:
    def __init__(self) -> None:
        self.outcomes: list[dict[str, Any]] = []

    def record_outcome(self, bundle, **kwargs) -> None:
        self.outcomes.append({"bundle": bundle, **kwargs})


class _Runtime:
    def __init__(
        self,
        first_result: SkillRuntimeResult | Exception,
        *,
        on_first_execute=None,
    ) -> None:
        self.first_result = first_result
        self.on_first_execute = on_first_execute
        self.calls: list[InteractionResponse] = []
        self.soridormi_invoker = None
        self.soridormi_mode = None
        self._definitions = {
            skill_id: SkillDefinition(
                skill_id=skill_id,
                provider_id="test.provider",
                output_schema=_TEST_OUTPUT_SCHEMA,
            )
            for skill_id in ("chromie.test.first", "chromie.test.second")
        }

    def skill_definition(self, skill_id: str) -> SkillDefinition:
        return self._definitions[skill_id]

    async def execute(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> SkillRuntimeResult:
        del session_id, confirmed_request_ids
        self.calls.append(response)
        if len(self.calls) == 1:
            if self.on_first_execute is not None:
                self.on_first_execute()
            if isinstance(self.first_result, Exception):
                raise self.first_result
            return self.first_result
        return SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            results=[
                SkillResult(
                    request_id=speech.id,
                    skill_id="chromie.speak",
                    status="completed",
                    output={"playback_started": True},
                )
                for speech in response.speech
            ],
        )


class _CancellationAwareRuntime(_Runtime):
    def __init__(self, *, propagate: bool = False) -> None:
        super().__init__(
            SkillRuntimeResult(
                interaction_id="interaction-turn-closure",
                status="cancelled",
            )
        )
        self.propagate = propagate
        self.started = asyncio.Event()
        self.provider_cancel_requested = asyncio.Event()

    async def execute(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> SkillRuntimeResult:
        del session_id, confirmed_request_ids
        self.calls.append(response)
        if len(self.calls) > 1:
            return SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    SkillResult(
                        request_id=speech.id,
                        skill_id="chromie.speak",
                        status="completed",
                        output={"playback_started": True},
                    )
                    for speech in response.speech
                ],
            )

        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.provider_cancel_requested.set()
            if self.propagate:
                raise
            return SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="cancelled",
                results=[
                    SkillResult(
                        request_id="request-first",
                        skill_id="chromie.test.first",
                        provider_id="test.provider",
                        status="cancelled",
                        reason_code="cancelled",
                        message="provider cancellation acknowledged",
                    )
                ],
            )


class _FailingFinalRuntime(_Runtime):
    async def execute(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> SkillRuntimeResult:
        del session_id, confirmed_request_ids
        self.calls.append(response)
        if len(self.calls) == 1:
            assert isinstance(self.first_result, SkillRuntimeResult)
            return self.first_result
        return SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                SkillResult(
                    request_id=speech.id,
                    skill_id="chromie.speak",
                    status="failed",
                    reason_code="playback_failed",
                )
                for speech in response.speech
            ],
        )


class CognitiveTurnLoopClosureTests(unittest.IsolatedAsyncioTestCase):
    def _assistant(
        self,
        runtime: _Runtime,
        response: InteractionResponse,
    ) -> tuple[VoiceAssistant, str, _EvidenceRecorder]:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.interaction_runtime = runtime
        assistant.playback_generation = 4
        assistant.sessions = SessionTracker(enabled=True)
        session_id = assistant.sessions.create()
        assistant.conversation_state = ConversationStateManager(
            base_conversation_id="turn-closure"
        )
        assistant.conversation_state.apply_goal_association_resolution(
            {
                "turn_id": "turn-closure",
                "new_goals": [
                    {
                        "goal_id": "goal-first",
                        "description": "Run the first test capability.",
                        "source_text": "Run two test capabilities.",
                    },
                    {
                        "goal_id": "goal-second",
                        "description": "Run the second test capability.",
                        "source_text": "Run two test capabilities.",
                    },
                ],
                "confidence": 0.98,
                "reason_summary": "Two independent goals.",
            },
            sid=session_id,
            user_text="Run two test capabilities.",
            route="tool",
            intent="compound_test",
            atomic=True,
        )
        assistant.conversation_state.record_agent_result(session_id, response)
        evidence = _EvidenceRecorder()
        assistant.cognitive_evidence = evidence
        assistant.session_log = lambda *args, **kwargs: None
        assistant.maybe_session_done = lambda *args, **kwargs: None
        assistant._record_experience = lambda **kwargs: None
        assistant._prepared_interaction_response_for_record = (
            lambda response, **kwargs: response
        )

        async def no_recovery(self, *args, **kwargs) -> bool:
            return False

        assistant._maybe_stage_body_recovery_confirmation = MethodType(
            no_recovery,
            assistant,
        )
        return assistant, session_id, evidence

    def test_runtime_result_interaction_id_mismatch_fails_closed(self) -> None:
        plan = _plan()
        response = _response(plan)
        execution = SkillRuntimeResult(
            interaction_id="interaction-from-another-turn",
            status="completed",
        )
        closure = CognitiveTurnClosure(_Runtime(execution))

        with self.assertRaisesRegex(
            ValueError,
            "interaction_id does not match InteractionResponse",
        ):
            closure.build(
                response=response,
                execution=execution,
                session_id="session-turn-closure",
            )

    def test_committed_pre_action_speech_result_is_auxiliary_evidence(
        self,
    ) -> None:
        plan = _plan()
        raw_response = _response(plan).model_dump(mode="json")
        raw_response["speech"] = [
            {
                "id": "speech-pre-action",
                "text": "I am starting now.",
                "timing": "sequential",
            }
        ]
        response = InteractionResponse.model_validate(raw_response)
        execution = SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            results=[
                SkillResult(
                    request_id="speech-pre-action",
                    skill_id="chromie.speak",
                    status="completed",
                ),
                SkillResult(
                    request_id="request-first",
                    skill_id="chromie.test.first",
                    status="completed",
                ),
                SkillResult(
                    request_id="request-second",
                    skill_id="chromie.test.second",
                    status="completed",
                ),
            ],
        )

        bundle = CognitiveTurnClosure(_Runtime(execution)).build(
            response=response,
            execution=execution,
            session_id="session-turn-closure",
        )

        self.assertIsNotNone(bundle)
        self.assertEqual(bundle.aggregate_status, "completed")
        self.assertEqual(
            [item.request_id for item in bundle.evidence],
            ["request-first", "request-second"],
        )
        self.assertEqual(
            bundle.metadata["ignored_non_plan_result_count"],
            1,
        )

    async def test_partial_execution_is_reconciled_and_summarized_once(self) -> None:
        plan = _plan()
        response = _response(plan)
        runtime = _Runtime(
            SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="failed",
                results=[
                    SkillResult(
                        request_id="request-first",
                        skill_id="chromie.test.first",
                        provider_id="test.provider",
                        status="completed",
                        output={"summary": "The first check passed"},
                    )
                ],
            )
        )
        assistant, session_id, evidence = self._assistant(runtime, response)

        execution = await assistant.execute_interaction_response(
            response,
            session_id,
            reset_playback=False,
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(len(runtime.calls), 2)
        final_response = runtime.calls[1]
        self.assertEqual(final_response.skills, [])
        self.assertEqual(
            [item.metadata["goal_status"] for item in final_response.speech],
            ["completed", "not_run"],
        )
        self.assertIn("The first check passed", final_response.speech[0].text)
        self.assertEqual(
            response.metadata["execution_outcome_bundle"]["aggregate_status"],
            "partial",
        )
        contexts = {
            item["semantic_goal"]["goal_id"]: item
            for item in assistant.conversation_state.snapshot()["task_contexts"]
        }
        self.assertEqual(contexts["goal-first"]["status"], "done")
        self.assertEqual(contexts["goal-second"]["status"], "failed")
        self.assertEqual(
            contexts["goal-second"]["metadata"]["execution_outcome_status"],
            "not_run",
        )
        self.assertEqual(len(evidence.outcomes), 1)
        self.assertEqual(
            evidence.outcomes[0]["delivery_status"],
            "speech_runtime_completed",
        )

    async def test_newer_turn_suppresses_stale_final_speech_but_keeps_evidence(self) -> None:
        plan = _plan()
        response = _response(plan)
        assistant_ref: dict[str, VoiceAssistant] = {}

        def make_stale() -> None:
            assistant_ref["assistant"].playback_generation += 1

        runtime = _Runtime(
            SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    SkillResult(
                        request_id="request-first",
                        skill_id="chromie.test.first",
                        status="completed",
                    ),
                    SkillResult(
                        request_id="request-second",
                        skill_id="chromie.test.second",
                        status="completed",
                    ),
                ],
            ),
            on_first_execute=make_stale,
        )
        assistant, session_id, evidence = self._assistant(runtime, response)
        assistant_ref["assistant"] = assistant

        await assistant.execute_interaction_response(
            response,
            session_id,
            reset_playback=False,
        )

        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual(
            response.metadata["cognitive_turn_closure_status"],
            "suppressed_stale",
        )
        self.assertEqual(evidence.outcomes[0]["delivery_status"], "suppressed")
        self.assertEqual(evidence.outcomes[0]["suppression_reason"], "stale_turn")

    async def test_exception_before_results_becomes_not_run_and_gets_safe_final(self) -> None:
        plan = _plan()
        response = _response(plan)
        runtime = _Runtime(RuntimeError("provider setup failed"))
        assistant, session_id, evidence = self._assistant(runtime, response)

        execution = await assistant.execute_interaction_response(
            response,
            session_id,
            reset_playback=False,
        )

        self.assertEqual(execution.status, "failed")
        self.assertEqual(len(runtime.calls), 2)
        self.assertEqual(
            [item.metadata["goal_status"] for item in runtime.calls[1].speech],
            ["not_run", "not_run"],
        )
        self.assertEqual(
            response.metadata["execution_outcome_bundle"]["aggregate_status"],
            "not_run",
        )
        self.assertEqual(len(evidence.outcomes), 1)

    async def test_observability_failure_does_not_duplicate_final_response(self) -> None:
        plan = _plan()
        response = _response(plan)
        runtime = _Runtime(
            SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    SkillResult(
                        request_id="request-first",
                        skill_id="chromie.test.first",
                        status="completed",
                    ),
                    SkillResult(
                        request_id="request-second",
                        skill_id="chromie.test.second",
                        status="completed",
                    ),
                ],
            )
        )
        assistant, session_id, evidence = self._assistant(runtime, response)

        def fail_observability(**kwargs: Any) -> None:
            del kwargs
            raise RuntimeError("journal unavailable")

        assistant._record_experience = fail_observability
        execution = await assistant.execute_interaction_response(
            response,
            session_id,
            reset_playback=False,
        )

        self.assertEqual(execution.status, "completed")
        self.assertEqual(len(runtime.calls), 2)
        self.assertEqual(len(evidence.outcomes), 1)
        self.assertEqual(
            response.metadata["cognitive_turn_closure_status"],
            "speech_runtime_completed",
        )

    async def test_undelivered_final_speech_is_not_added_to_history(self) -> None:
        plan = _plan()
        response = _response(plan)
        runtime = _FailingFinalRuntime(
            SkillRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    SkillResult(
                        request_id="request-first",
                        skill_id="chromie.test.first",
                        status="completed",
                    ),
                    SkillResult(
                        request_id="request-second",
                        skill_id="chromie.test.second",
                        status="completed",
                    ),
                ],
            )
        )
        assistant, session_id, evidence = self._assistant(runtime, response)

        await assistant.execute_interaction_response(
            response,
            session_id,
            reset_playback=False,
        )

        self.assertEqual(len(runtime.calls), 2)
        self.assertEqual(
            [
                item
                for item in assistant.conversation_state.get_history()
                if item["role"] == "assistant"
            ],
            [],
        )
        self.assertEqual(
            evidence.outcomes[0]["delivery_status"],
            "speech_runtime_failed",
        )

    def test_changed_output_schema_cannot_expose_provider_output(self) -> None:
        plan = _plan()
        response = _response(plan)
        secret_output = "must-not-cross-the-schema-commitment"
        execution = SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                SkillResult(
                    request_id="request-first",
                    skill_id="chromie.test.first",
                    provider_id="test.provider",
                    status="completed",
                    output={"summary": secret_output},
                )
            ],
        )
        runtime = _Runtime(execution)
        runtime._definitions["chromie.test.first"] = SkillDefinition(
            skill_id="chromie.test.first",
            provider_id="test.provider",
            output_schema={
                **_TEST_OUTPUT_SCHEMA,
                "required": ["summary"],
            },
        )

        bundle = CognitiveTurnClosure(runtime).build(
            response=response,
            execution=execution,
            session_id="turn-closure",
        )

        self.assertIsNotNone(bundle)
        observation = bundle.evidence[0].observation
        self.assertIsNotNone(observation)
        self.assertEqual(observation.status, "schema_unavailable")
        self.assertEqual(observation.data, {})
        self.assertEqual(
            observation.validation_errors,
            ["committed_output_schema_digest_mismatch"],
        )
        self.assertEqual(
            bundle.evidence[0].metadata["output_schema_gate_reason"],
            "committed_output_schema_digest_mismatch",
        )
        self.assertNotIn(secret_output, bundle.model_dump_json())

    def test_missing_output_schema_commitment_fails_closed(self) -> None:
        plan = _plan()
        raw_response = _response(plan).model_dump(mode="json")
        raw_response["skills"][0].pop(
            "committed_output_schema_sha256",
            None,
        )
        response = InteractionResponse.model_validate(raw_response)
        secret_output = "legacy-live-schema-output"
        execution = SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                SkillResult(
                    request_id="request-first",
                    skill_id="chromie.test.first",
                    provider_id="test.provider",
                    status="completed",
                    output={"summary": secret_output},
                )
            ],
        )
        runtime = _Runtime(execution)

        bundle = CognitiveTurnClosure(runtime).build(
            response=response,
            execution=execution,
            session_id="turn-closure",
        )

        self.assertIsNotNone(bundle)
        observation = bundle.evidence[0].observation
        self.assertIsNotNone(observation)
        self.assertEqual(observation.status, "schema_unavailable")
        self.assertEqual(
            observation.validation_errors,
            ["committed_output_schema_digest_missing"],
        )
        self.assertNotIn(secret_output, bundle.model_dump_json())

    def test_empty_committed_provider_schema_fails_closed(self) -> None:
        plan = _plan()
        raw_response = _response(plan).model_dump(mode="json")
        raw_response["skills"][0][
            "committed_output_schema_sha256"
        ] = output_schema_sha256({})
        response = InteractionResponse.model_validate(raw_response)
        secret_output = "undeclared-provider-payload"
        execution = SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                SkillResult(
                    request_id="request-first",
                    skill_id="chromie.test.first",
                    provider_id="test.provider",
                    status="completed",
                    output={"summary": secret_output},
                )
            ],
        )
        runtime = _Runtime(execution)
        runtime._definitions["chromie.test.first"] = SkillDefinition(
            skill_id="chromie.test.first",
            provider_id="test.provider",
            output_schema={},
        )

        bundle = CognitiveTurnClosure(runtime).build(
            response=response,
            execution=execution,
            session_id="turn-closure",
        )

        self.assertIsNotNone(bundle)
        observation = bundle.evidence[0].observation
        self.assertIsNotNone(observation)
        self.assertEqual(observation.status, "schema_unavailable")
        self.assertEqual(
            observation.validation_errors,
            ["committed_output_schema_absent"],
        )
        self.assertNotIn(secret_output, bundle.model_dump_json())

    async def test_active_cancellation_retains_outcomes_and_suppresses_stale_final(
        self,
    ) -> None:
        plan = _plan()
        response = _response(plan)
        runtime = _CancellationAwareRuntime()
        assistant, session_id, evidence = self._assistant(runtime, response)

        task = asyncio.create_task(
            assistant.execute_interaction_response(
                response,
                session_id,
                reset_playback=False,
            )
        )
        await runtime.started.wait()
        assistant.playback_generation += 1
        task.cancel()
        execution = await task

        self.assertTrue(runtime.provider_cancel_requested.is_set())
        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            [
                (result.request_id, result.status)
                for result in execution.results
            ],
            [("request-first", "cancelled")],
        )
        self.assertEqual(len(runtime.calls), 1)
        self.assertNotIn("post_execution_response", response.metadata)
        self.assertEqual(
            response.metadata["cognitive_turn_closure_status"],
            "suppressed_stale",
        )

        bundle = response.metadata["execution_outcome_bundle"]
        self.assertEqual(bundle["aggregate_status"], "failed")
        self.assertEqual(
            [item["status"] for item in bundle["evidence"]],
            ["cancelled", "not_run"],
        )
        self.assertEqual(
            [item["status"] for item in bundle["goal_outcomes"]],
            ["cancelled", "not_run"],
        )
        self.assertEqual(bundle["evidence"][0]["reason_code"], "cancelled")
        self.assertTrue(bundle["evidence"][1]["missing_result"])

        contexts = {
            item["semantic_goal"]["goal_id"]: item
            for item in assistant.conversation_state.snapshot()["task_contexts"]
        }
        self.assertEqual(contexts["goal-first"]["status"], "cancelled")
        self.assertEqual(
            contexts["goal-first"]["metadata"]["execution_outcome_status"],
            "cancelled",
        )
        self.assertEqual(contexts["goal-second"]["status"], "failed")
        self.assertEqual(
            contexts["goal-second"]["metadata"]["execution_outcome_status"],
            "not_run",
        )

        self.assertEqual(len(evidence.outcomes), 1)
        self.assertIsNone(evidence.outcomes[0]["final_response"])
        self.assertEqual(evidence.outcomes[0]["delivery_status"], "suppressed")
        self.assertEqual(
            evidence.outcomes[0]["suppression_reason"],
            "stale_turn",
        )

    async def test_propagated_runtime_cancellation_closes_cognitive_turn_under_shield(
        self,
    ) -> None:
        plan = _plan()
        response = _response(plan)
        runtime = _CancellationAwareRuntime(propagate=True)
        assistant, session_id, evidence = self._assistant(runtime, response)

        task = asyncio.create_task(
            assistant.execute_interaction_response(
                response,
                session_id,
                reset_playback=False,
            )
        )
        await runtime.started.wait()
        assistant.playback_generation += 1
        task.cancel()
        execution = await task

        self.assertFalse(task.cancelled())
        self.assertTrue(runtime.provider_cancel_requested.is_set())
        self.assertEqual(execution.status, "cancelled")
        self.assertEqual(
            [
                (result.request_id, result.status)
                for result in execution.results
            ],
            [
                ("request-first", "cancelled"),
                ("request-second", "cancelled"),
            ],
        )
        self.assertTrue(
            all(
                result.reason_code
                == "interaction_cancelled_terminal_result_unavailable"
                for result in execution.results
            )
        )
        self.assertEqual(len(runtime.calls), 1)
        self.assertNotIn("post_execution_response", response.metadata)
        self.assertEqual(
            response.metadata["cognitive_turn_closure_status"],
            "suppressed_stale",
        )

        bundle = response.metadata["execution_outcome_bundle"]
        self.assertEqual(bundle["aggregate_status"], "cancelled")
        self.assertEqual(
            [item["status"] for item in bundle["evidence"]],
            ["cancelled", "cancelled"],
        )
        self.assertEqual(
            [item["status"] for item in bundle["goal_outcomes"]],
            ["cancelled", "cancelled"],
        )
        self.assertTrue(
            all(
                not item["missing_result"]
                for item in bundle["evidence"]
            )
        )

        contexts = {
            item["semantic_goal"]["goal_id"]: item
            for item in assistant.conversation_state.snapshot()["task_contexts"]
        }
        self.assertEqual(contexts["goal-first"]["status"], "cancelled")
        self.assertEqual(contexts["goal-second"]["status"], "cancelled")
        self.assertEqual(
            [
                contexts[goal_id]["metadata"]["execution_outcome_status"]
                for goal_id in ("goal-first", "goal-second")
            ],
            ["cancelled", "cancelled"],
        )

        self.assertEqual(len(evidence.outcomes), 1)
        self.assertIsNone(evidence.outcomes[0]["final_response"])
        self.assertEqual(evidence.outcomes[0]["delivery_status"], "suppressed")
        self.assertEqual(
            evidence.outcomes[0]["suppression_reason"],
            "stale_turn",
        )


if __name__ == "__main__":
    unittest.main()
