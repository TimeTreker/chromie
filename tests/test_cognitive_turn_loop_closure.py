from __future__ import annotations

import asyncio
import unittest
from types import MethodType
from typing import Any

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.cognitive_turn_closure import CognitiveTurnClosure
from orchestrator.runtime.interaction_coordinator import CapabilityInteractionDispatch
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.session import SessionTracker
from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition,
    CapabilityRuntimeResult,
    schema_valid_completion_evidence_policy,
)
from shared.chromie_contracts.execution_outcome import (
    ClaimQualificationPolicy,
    claim_qualification_policy_sha256,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    CapabilityResult,
    output_schema_sha256,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)

_TEST_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"user_summary": {"type": "string"}},
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
                "capability_id": "chromie.test.first",
                "args": {},
                "source_goal_ids": ["goal-first"],
            },
            {
                "step_id": "step-second",
                "capability_id": "chromie.test.second",
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
    completion_digest = claim_qualification_policy_sha256(
        schema_valid_completion_evidence_policy()
    )
    return InteractionResponse(
        interaction_id="interaction-turn-closure",
        capabilities=[
            {
                "request_id": "request-first",
                "capability_id": "chromie.test.first",
                "timing": "sequential",
                "committed_output_schema_sha256": output_schema_sha256(
                    _TEST_OUTPUT_SCHEMA
                ),
                "committed_completion_evidence_sha256": completion_digest,
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
                "capability_id": "chromie.test.second",
                "timing": "sequential",
                "committed_output_schema_sha256": output_schema_sha256(
                    _TEST_OUTPUT_SCHEMA
                ),
                "committed_completion_evidence_sha256": completion_digest,
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
        first_result: CapabilityRuntimeResult,
        *,
        on_first_execute=None,
    ) -> None:
        self.first_result = first_result
        self.on_first_execute = on_first_execute
        self.calls: list[InteractionResponse] = []
        self.session_ids: list[str | None] = []
        self.soridormi_invoker = None
        self._definitions = {
            capability_id: CapabilityDefinition(
                capability_id=capability_id,
                provider_id="test.provider",
                output_schema=_TEST_OUTPUT_SCHEMA,
            )
            for capability_id in ("chromie.test.first", "chromie.test.second")
        }

    def capability_definition(self, capability_id: str) -> CapabilityDefinition:
        return self._definitions[capability_id]

    async def submit_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> CapabilityInteractionDispatch:
        del confirmed_request_ids
        self.session_ids.append(session_id)
        self.calls.append(response)
        if len(self.calls) == 1:
            if self.on_first_execute is not None:
                self.on_first_execute()
            execution = self.first_result
        else:
            execution = CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id=speech.id,
                        capability_id="chromie.speak",
                        status="completed",
                        output={"playback_started": True},
                    )
                    for speech in response.speech
                ],
            )
        return CapabilityInteractionDispatch(
            source_response=response,
            runtime_response=response,
            receipt=None,
            immediate_execution=execution,
            preexecuted_results=[],
            preexecuted_traces=[],
        )

    async def wait_dispatch(
        self,
        dispatch: CapabilityInteractionDispatch,
    ) -> CapabilityRuntimeResult:
        assert dispatch.immediate_execution is not None
        return dispatch.immediate_execution




class _FailingFinalRuntime(_Runtime):
    async def submit_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None = None,
    ) -> CapabilityInteractionDispatch:
        del confirmed_request_ids
        self.session_ids.append(session_id)
        self.calls.append(response)
        if len(self.calls) == 1:
            execution = self.first_result
        else:
            execution = CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="failed",
                results=[
                    CapabilityResult(
                        request_id=speech.id,
                        capability_id="chromie.speak",
                        status="failed",
                        reason_code="playback_failed",
                    )
                    for speech in response.speech
                ],
            )
        return CapabilityInteractionDispatch(
            source_response=response,
            runtime_response=response,
            receipt=None,
            immediate_execution=execution,
            preexecuted_results=[],
            preexecuted_traces=[],
        )


class CognitiveTurnLoopClosureTests(unittest.IsolatedAsyncioTestCase):
    async def _execute_detached(
        self,
        assistant: VoiceAssistant,
        response: InteractionResponse,
        session_id: str,
    ) -> CapabilityRuntimeResult:
        await assistant._dispatch_detached_interaction(
            response,
            session_id,
            confirmed_request_ids=None,
            reset_playback=False,
            mark_session_done=False,
        )
        tasks = list(assistant.active_capability_result_tasks)
        self.assertEqual(len(tasks), 1)
        return await tasks[0]

    def _assistant(
        self,
        runtime: _Runtime,
        response: InteractionResponse,
    ) -> tuple[VoiceAssistant, str, _EvidenceRecorder]:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.interaction_runtime = runtime
        assistant.playback_generation = 4
        assistant.playback_queue = asyncio.Queue()
        assistant.active_synthesis_tasks = set()
        assistant.is_playing_audio = False
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
        assistant.conversation_state.record_interaction_response(session_id, response)
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
        execution = CapabilityRuntimeResult(
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

    def test_incremental_turn_closure_emits_exact_terminal_evidence_with_stable_identity(self) -> None:
        plan = _plan()
        response = _response(plan)
        first_result = CapabilityResult(
            request_id="request-first",
            capability_id="chromie.test.first",
            provider_id="test.provider",
            status="completed",
            output={"user_summary": "first"},
        )
        second_result = CapabilityResult(
            request_id="request-second",
            capability_id="chromie.test.second",
            provider_id="test.provider",
            status="completed",
            output={"user_summary": "second"},
        )
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            results=[first_result, second_result],
        )
        closure = CognitiveTurnClosure(_Runtime(execution))

        evidence = closure.build_terminal_evidence(
            response=response,
            result=first_result,
            session_id="session-turn-closure",
        )
        bundle = closure.build(
            response=response,
            execution=execution,
            session_id="session-turn-closure",
        )

        self.assertIsNotNone(evidence)
        self.assertIsNotNone(bundle)
        assert evidence is not None
        assert bundle is not None
        self.assertEqual(evidence.request_id, "request-first")
        self.assertEqual(evidence.status, "completed")
        self.assertFalse(evidence.missing_result)
        self.assertNotIn("request-second", evidence.model_dump_json())
        final_first = next(
            item for item in bundle.evidence if item.request_id == "request-first"
        )
        self.assertEqual(evidence.evidence_id, final_first.evidence_id)
        self.assertEqual(evidence.request_id, final_first.request_id)
        self.assertEqual(evidence.step_id, final_first.step_id)
        self.assertEqual(evidence.status, final_first.status)
        self.assertEqual(evidence.observation, final_first.observation)

    def test_completion_evidence_policy_digest_mismatch_fails_qualification_closed(self) -> None:
        plan = _plan()
        response = _response(plan)
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            results=[
                CapabilityResult(
                    request_id="request-first",
                    capability_id="chromie.test.first",
                    provider_id="test.provider",
                    status="completed",
                    output={"user_summary": "first"},
                ),
                CapabilityResult(
                    request_id="request-second",
                    capability_id="chromie.test.second",
                    provider_id="test.provider",
                    status="completed",
                    output={"user_summary": "second"},
                ),
            ],
        )
        runtime = _Runtime(execution)
        runtime._definitions["chromie.test.first"] = CapabilityDefinition(
            capability_id="chromie.test.first",
            provider_id="test.provider",
            output_schema=_TEST_OUTPUT_SCHEMA,
            completion_evidence_policy=ClaimQualificationPolicy(
                claim="changed completion claim",
                requirement_groups=[
                    {"requirements": [{"source": "execution_observation"}]}
                ],
            ),
        )

        bundle = CognitiveTurnClosure(runtime).build(
            response=response,
            execution=execution,
            session_id="turn-closure",
        )

        self.assertIsNotNone(bundle)
        assert bundle is not None
        first = bundle.evidence[0]
        second = bundle.evidence[1]
        self.assertTrue(first.metadata["completion_qualification_required"])
        self.assertEqual(
            first.metadata["completion_evidence_gate_reason"],
            "committed_completion_evidence_digest_mismatch",
        )
        self.assertIsNone(first.completion_qualification)
        self.assertIsNotNone(second.completion_qualification)
        assert second.completion_qualification is not None
        self.assertEqual(second.completion_qualification.status, "established")

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
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="completed",
            results=[
                CapabilityResult(
                    request_id="speech-pre-action",
                    capability_id="chromie.speak",
                    status="completed",
                ),
                CapabilityResult(
                    request_id="request-first",
                    capability_id="chromie.test.first",
                    status="completed",
                ),
                CapabilityResult(
                    request_id="request-second",
                    capability_id="chromie.test.second",
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
            CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="failed",
                results=[
                    CapabilityResult(
                        request_id="request-first",
                        capability_id="chromie.test.first",
                        provider_id="test.provider",
                        status="completed",
                        output={"user_summary": "The first check passed"},
                    )
                ],
            )
        )
        assistant, session_id, evidence = self._assistant(runtime, response)

        execution = await self._execute_detached(assistant, response, session_id)

        self.assertEqual(execution.status, "failed")
        self.assertEqual(len(runtime.calls), 2)
        final_response = runtime.calls[1]
        self.assertEqual(final_response.capabilities, [])
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
            CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id="request-first",
                        capability_id="chromie.test.first",
                        status="completed",
                    ),
                    CapabilityResult(
                        request_id="request-second",
                        capability_id="chromie.test.second",
                        status="completed",
                    ),
                ],
            ),
            on_first_execute=make_stale,
        )
        assistant, session_id, evidence = self._assistant(runtime, response)
        assistant_ref["assistant"] = assistant

        await self._execute_detached(assistant, response, session_id)

        self.assertEqual(len(runtime.calls), 1)
        self.assertEqual(
            response.metadata["cognitive_turn_closure_status"],
            "suppressed_stale",
        )
        self.assertEqual(evidence.outcomes[0]["delivery_status"], "suppressed")
        self.assertEqual(evidence.outcomes[0]["suppression_reason"], "stale_turn")

    async def test_completed_ordinary_overlap_delivers_after_newer_turn_finishes(self) -> None:
        plan = _plan()
        response = _response(plan)
        assistant_ref: dict[str, VoiceAssistant] = {}
        newer_session: dict[str, str] = {}

        def make_overlap() -> None:
            assistant = assistant_ref["assistant"]
            assistant.playback_generation += 1
            sid = assistant.sessions.create()
            newer_session["sid"] = sid

            async def finish_newer_turn() -> None:
                await asyncio.sleep(0.01)
                assistant.sessions.state[sid]["done_logged"] = True

            asyncio.create_task(finish_newer_turn())

        runtime = _Runtime(
            CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id="request-first",
                        capability_id="chromie.test.first",
                        status="completed",
                    ),
                    CapabilityResult(
                        request_id="request-second",
                        capability_id="chromie.test.second",
                        status="completed",
                    ),
                ],
            ),
            on_first_execute=make_overlap,
        )
        assistant, session_id, evidence = self._assistant(runtime, response)
        assistant_ref["assistant"] = assistant

        await self._execute_detached(assistant, response, session_id)

        self.assertEqual(len(runtime.calls), 2)
        self.assertEqual(runtime.session_ids, [session_id, None])
        self.assertEqual(
            response.metadata["cognitive_turn_closure_status"],
            "speech_runtime_completed",
        )
        deferred = response.metadata["post_execution_response"]["metadata"][
            "deferred_outcome_delivery"
        ]
        self.assertEqual(deferred["reason"], "ordinary_overlap")
        self.assertEqual(deferred["waited_for_session_ids"], [newer_session["sid"]])
        self.assertEqual(evidence.outcomes[0]["delivery_status"], "speech_runtime_completed")
        self.assertEqual(evidence.outcomes[0]["suppression_reason"], "")

    async def test_terminal_failure_without_results_becomes_not_run_and_gets_safe_final(self) -> None:
        plan = _plan()
        response = _response(plan)
        runtime = _Runtime(
            CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="failed",
            )
        )
        assistant, session_id, evidence = self._assistant(runtime, response)

        execution = await self._execute_detached(assistant, response, session_id)

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
            CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id="request-first",
                        capability_id="chromie.test.first",
                        status="completed",
                    ),
                    CapabilityResult(
                        request_id="request-second",
                        capability_id="chromie.test.second",
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
        execution = await self._execute_detached(assistant, response, session_id)

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
            CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="completed",
                results=[
                    CapabilityResult(
                        request_id="request-first",
                        capability_id="chromie.test.first",
                        status="completed",
                    ),
                    CapabilityResult(
                        request_id="request-second",
                        capability_id="chromie.test.second",
                        status="completed",
                    ),
                ],
            )
        )
        assistant, session_id, evidence = self._assistant(runtime, response)

        await self._execute_detached(assistant, response, session_id)

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
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                CapabilityResult(
                    request_id="request-first",
                    capability_id="chromie.test.first",
                    provider_id="test.provider",
                    status="completed",
                    output={"summary": secret_output},
                )
            ],
        )
        runtime = _Runtime(execution)
        runtime._definitions["chromie.test.first"] = CapabilityDefinition(
            capability_id="chromie.test.first",
            provider_id="test.provider",
            output_schema={
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
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
        raw_response["capabilities"][0].pop(
            "committed_output_schema_sha256",
            None,
        )
        response = InteractionResponse.model_validate(raw_response)
        secret_output = "legacy-live-schema-output"
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                CapabilityResult(
                    request_id="request-first",
                    capability_id="chromie.test.first",
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
        raw_response["capabilities"][0][
            "committed_output_schema_sha256"
        ] = output_schema_sha256({})
        response = InteractionResponse.model_validate(raw_response)
        secret_output = "undeclared-provider-payload"
        execution = CapabilityRuntimeResult(
            interaction_id=response.interaction_id,
            status="failed",
            results=[
                CapabilityResult(
                    request_id="request-first",
                    capability_id="chromie.test.first",
                    provider_id="test.provider",
                    status="completed",
                    output={"summary": secret_output},
                )
            ],
        )
        runtime = _Runtime(execution)
        runtime._definitions["chromie.test.first"] = CapabilityDefinition(
            capability_id="chromie.test.first",
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
            ["current_output_schema_invalid"],
        )
        self.assertNotIn(secret_output, bundle.model_dump_json())
