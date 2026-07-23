from __future__ import annotations

import asyncio
import unittest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.confirmation import ConfirmationDialogue
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.named_goal_cancellation import (
    NamedGoalCancellationClosureError,
)
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    SkillRequest,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.reflex import CancellationDispatchReceipt
from shared.chromie_contracts.response_composition import canonical_plan_fingerprint


def _plan() -> CanonicalPlan:
    return CanonicalPlan.model_validate(
        {
            "plan_id": "plan-parent",
            "planner_tier": "fast",
            "disposition": "execute",
            "coverage": "complete",
            "confidence": 0.95,
            "goal_ids": ["goal-a", "goal-b"],
            "steps": [
                {
                    "step_id": "step-a",
                    "skill_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-a"],
                },
                {
                    "step_id": "step-b",
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-b"],
                },
            ],
            "goal_outcomes": [
                {
                    "goal_id": "goal-a",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-a"],
                },
                {
                    "goal_id": "goal-b",
                    "disposition": "execute",
                    "coverage": "complete",
                    "step_ids": ["step-b"],
                },
            ],
        }
    )


def _create_goals(manager: ConversationStateManager) -> None:
    manager.apply_semantic_task_operations_atomically(
        [
            {
                "operation_id": "create-a",
                "operation": "create",
                "goal": {
                    "goal_id": "goal-a",
                    "description": "Nod once.",
                    "source_text": "Nod once.",
                },
            },
            {
                "operation_id": "create-b",
                "operation": "create",
                "goal": {
                    "goal_id": "goal-b",
                    "description": "Blink twice.",
                    "source_text": "Blink twice.",
                },
            },
        ],
        sid="sid-create",
        user_text="Nod once and blink twice.",
    )


def _cancel_resolution(goal_ids: list[str]) -> CognitiveRuntimeResolution:
    return CognitiveRuntimeResolution(
        mode="apply",
        status="applied",
        lane="chat",
        goal_association=GoalAssociationResolution(
            turn_id="turn-cancel",
            associations=[
                {
                    "association_id": "assoc-cancel",
                    "relationship": "cancel",
                    "target_goal_ids": goal_ids,
                    "confidence": 0.98,
                }
            ],
            confidence=0.98,
        ),
    )


class NamedGoalCancellationClosureTests(unittest.TestCase):
    def test_active_goal_dispatch_uses_exact_runtime_binding_and_commits_receipt(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-test")
        _create_goals(manager)
        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        context["status"] = "running"
        context["commitment_state"] = "executing"
        context["metadata"] = {
            **context.get("metadata", {}),
            "interaction_id": "interaction-parent",
            "canonical_plan_id": "plan-parent",
            "canonical_plan_fingerprint": "fingerprint-parent",
            "remaining_request_ids": ["request-a"],
        }

        class Runtime:
            def __init__(self) -> None:
                self.directives = []

            async def cancel_scope(self, directive):
                self.directives.append(directive)
                return CancellationDispatchReceipt(
                    source_turn_id=directive.source_turn_id,
                    requested_scope="specific_goal",
                    effective_scope="specific_goal",
                    interaction_ids=("interaction-parent",),
                    target_goal_ids=("goal-a",),
                    expected_plan_id="plan-parent",
                    expected_plan_fingerprint="fingerprint-parent",
                    affected_goal_ids=("goal-a",),
                    selected_request_ids=("request-a",),
                    queued_request_ids=("request-a",),
                )

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.conversation_state = manager
        assistant.interaction_runtime = Runtime()
        assistant.confirmation_dialogue = ConfirmationDialogue()
        assistant.session_log = lambda *args, **kwargs: None
        resolution = _cancel_resolution(["goal-a"])
        decision = RouteDecision(
            route="chat",
            intent="cancel_goal",
            confidence=0.95,
            source="llm",
            language="en-US",
        )

        results, metadata = asyncio.run(
            assistant._dispatch_named_goal_cancellation(
                resolution,
                session_id="sid-cancel",
                user_text="Cancel the nod.",
                decision=decision,
            )
        )

        self.assertTrue(any(item.get("applied") for item in results))
        self.assertEqual(metadata["target_goal_ids"], ["goal-a"])
        self.assertEqual(len(assistant.interaction_runtime.directives), 1)
        directive = assistant.interaction_runtime.directives[0]
        self.assertEqual(directive.foreground_interaction_id, "interaction-parent")
        self.assertEqual(directive.expected_plan_id, "plan-parent")
        self.assertEqual(
            directive.expected_plan_fingerprint, "fingerprint-parent"
        )
        cancelled = manager._task_context_by_goal_id("goal-a")
        assert cancelled is not None
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(
            cancelled["metadata"]["cancellation_source_turn_id"],
            "turn-cancel",
        )
        sibling = manager._task_context_by_goal_id("goal-b")
        assert sibling is not None
        self.assertNotEqual(sibling["status"], "cancelled")

    def test_provider_cancel_failure_rolls_back_goal_state(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-test")
        _create_goals(manager)
        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        context["status"] = "running"
        context["commitment_state"] = "executing"
        context["metadata"] = {
            **context.get("metadata", {}),
            "interaction_id": "interaction-parent",
            "canonical_plan_id": "plan-parent",
            "canonical_plan_fingerprint": "fingerprint-parent",
            "remaining_request_ids": ["request-a"],
        }
        resolution = _cancel_resolution(["goal-a"]).goal_association
        assert resolution is not None
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-cancel",
            requested_scope="specific_goal",
            effective_scope="specific_goal",
            interaction_ids=("interaction-parent",),
            target_goal_ids=("goal-a",),
            expected_plan_id="plan-parent",
            expected_plan_fingerprint="fingerprint-parent",
            affected_goal_ids=("goal-a",),
            selected_request_ids=("request-a",),
            active_request_ids=("request-a",),
            provider_cancel_failures=("request-a:provider failed",),
        )

        with self.assertRaisesRegex(
            ValueError, "provider_cancel_failure"
        ):
            manager.apply_goal_cancellation_resolution(
                resolution,
                receipts=[receipt],
                confirmation_transition=None,
                sid="sid-cancel",
                user_text="Cancel the nod.",
                route="chat",
                intent="cancel_goal",
            )
        unchanged = manager._task_context_by_goal_id("goal-a")
        assert unchanged is not None
        self.assertEqual(unchanged["status"], "running")

    def test_speech_cancel_without_scheduling_receipt_aborts_shared_output(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        invalidations: list[bool] = []
        aborts: list[bool] = []
        assistant._cancel_scheduled_playback_before_start = (
            lambda *args, **kwargs: []
        )
        assistant._invalidate_output_state = (
            lambda *, cancel_cognitive_work: invalidations.append(
                cancel_cognitive_work
            )
        )

        async def abort_output_stream() -> None:
            aborts.append(True)

        assistant.abort_output_stream = abort_output_stream
        assistant.session_log = lambda *args, **kwargs: None

        asyncio.run(
            assistant._cancel_interaction_speech(
                SkillRequest(
                    request_id="speech-a",
                    skill_id="chromie.speak",
                    args={
                        "text": "Starting.",
                        "metadata": {"session_id": "sid-speech"},
                    },
                ),
                {},
            )
        )

        self.assertEqual(invalidations, [False])
        self.assertEqual(aborts, [True])

    def test_provider_scope_widening_reconciles_coaffected_goal(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-test")
        _create_goals(manager)
        for goal_id, interaction_id, request_id in (
            ("goal-a", "interaction-a", "request-a"),
            ("goal-b", "interaction-b", "request-b"),
        ):
            context = manager._task_context_by_goal_id(goal_id)
            assert context is not None
            context["status"] = "running"
            context["commitment_state"] = "executing"
            context["metadata"] = {
                **context.get("metadata", {}),
                "interaction_id": interaction_id,
                "canonical_plan_id": "plan-parent",
                "canonical_plan_fingerprint": "fingerprint-parent",
                "remaining_request_ids": [request_id],
            }

        association = _cancel_resolution(["goal-a"]).goal_association
        assert association is not None
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-cancel",
            requested_scope="specific_goal",
            effective_scope="embodied_motion",
            interaction_ids=("interaction-a", "interaction-b"),
            target_goal_ids=("goal-a",),
            expected_plan_id="plan-parent",
            expected_plan_fingerprint="fingerprint-parent",
            affected_goal_ids=("goal-a", "goal-b"),
            selected_request_ids=("request-a", "request-b"),
            active_request_ids=("request-a", "request-b"),
            cancel_requested_request_ids=("request-a", "request-b"),
            widened=True,
            widening_reason=(
                "provider_supports_only_global_embodied_motion_cancel"
            ),
        )

        results = manager.apply_goal_cancellation_resolution(
            association,
            receipts=[receipt],
            confirmation_transition=None,
            sid="sid-cancel",
            user_text="Cancel the nod.",
            route="chat",
            intent="cancel_goal",
        )

        self.assertTrue(any(item.get("applied") for item in results))
        target = manager._task_context_by_goal_id("goal-a")
        coaffected = manager._task_context_by_goal_id("goal-b")
        assert target is not None and coaffected is not None
        self.assertEqual(target["status"], "cancelled")
        self.assertEqual(coaffected["status"], "cancelled")
        self.assertTrue(
            coaffected["metadata"]["cancellation_scope_widened"]
        )

    def test_persistence_failure_rolls_back_atomic_goal_state(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-test")
        _create_goals(manager)
        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        context["status"] = "running"
        context["metadata"] = {
            **context.get("metadata", {}),
            "interaction_id": "interaction-parent",
            "canonical_plan_id": "plan-parent",
            "canonical_plan_fingerprint": "fingerprint-parent",
            "remaining_request_ids": ["request-a"],
        }
        manager.task_store_enabled = True

        def fail_persistence() -> bool:
            manager.last_task_store_error = "disk unavailable"
            return False

        manager.persist_task_contexts = fail_persistence  # type: ignore[method-assign]
        association = _cancel_resolution(["goal-a"]).goal_association
        assert association is not None
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-cancel",
            requested_scope="specific_goal",
            effective_scope="specific_goal",
            interaction_ids=("interaction-parent",),
            target_goal_ids=("goal-a",),
            expected_plan_id="plan-parent",
            expected_plan_fingerprint="fingerprint-parent",
            affected_goal_ids=("goal-a",),
            selected_request_ids=("request-a",),
            active_request_ids=("request-a",),
            cancel_requested_request_ids=("request-a",),
        )

        results = manager.apply_goal_cancellation_resolution(
            association,
            receipts=[receipt],
            confirmation_transition=None,
            sid="sid-cancel",
            user_text="Cancel the nod.",
            route="chat",
            intent="cancel_goal",
        )

        self.assertTrue(
            any(
                item.get("reason") == "atomic_cancellation_persistence_failed"
                for item in results
            )
        )
        unchanged = manager._task_context_by_goal_id("goal-a")
        assert unchanged is not None
        self.assertEqual(unchanged["status"], "running")


    def test_dispatch_persistence_failure_reports_uncertain_result(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-test")
        _create_goals(manager)
        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        context["status"] = "running"
        context["commitment_state"] = "executing"
        context["metadata"] = {
            **context.get("metadata", {}),
            "interaction_id": "interaction-parent",
            "canonical_plan_id": "plan-parent",
            "canonical_plan_fingerprint": "fingerprint-parent",
            "remaining_request_ids": ["request-a"],
        }
        manager.task_store_enabled = True

        def fail_persistence() -> bool:
            manager.last_task_store_error = "disk unavailable"
            return False

        manager.persist_task_contexts = fail_persistence  # type: ignore[method-assign]

        class Runtime:
            async def cancel_scope(self, directive):
                return CancellationDispatchReceipt(
                    source_turn_id=directive.source_turn_id,
                    requested_scope="specific_goal",
                    effective_scope="specific_goal",
                    interaction_ids=("interaction-parent",),
                    target_goal_ids=("goal-a",),
                    expected_plan_id="plan-parent",
                    expected_plan_fingerprint="fingerprint-parent",
                    affected_goal_ids=("goal-a",),
                    selected_request_ids=("request-a",),
                    active_request_ids=("request-a",),
                    cancel_requested_request_ids=("request-a",),
                )

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.conversation_state = manager
        assistant.interaction_runtime = Runtime()
        assistant.confirmation_dialogue = ConfirmationDialogue()
        assistant.session_log = lambda *args, **kwargs: None
        resolution = _cancel_resolution(["goal-a"])
        decision = RouteDecision(
            route="chat",
            intent="cancel_goal",
            confidence=0.95,
            source="llm",
            language="en-US",
        )

        with self.assertRaises(NamedGoalCancellationClosureError) as raised:
            asyncio.run(
                assistant._dispatch_named_goal_cancellation(
                    resolution,
                    session_id="sid-cancel",
                    user_text="Cancel the nod.",
                    decision=decision,
                )
            )

        error = raised.exception
        self.assertEqual(error.stage, "goal_state_reconciliation")
        self.assertTrue(error.runtime_dispatch_attempted)
        response = assistant._named_goal_cancellation_failure_response(
            error,
            user_text="Cancel the nod.",
        )
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(
            response.metadata["source"],
            "host_specific_goal_cancel_result_uncertain",
        )
        self.assertIn("final state", response.speech[0].text)
        self.assertNotIn("before acting", response.speech[0].text)
        unchanged = manager._task_context_by_goal_id("goal-a")
        assert unchanged is not None
        self.assertEqual(unchanged["status"], "running")

    def test_shared_confirmation_request_rejects_partial_cancel_without_mutation(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-test")
        _create_goals(manager)
        plan = CanonicalPlan.model_validate(
            {
                "plan_id": "plan-shared",
                "planner_tier": "fast",
                "disposition": "execute",
                "coverage": "complete",
                "confidence": 0.95,
                "goal_ids": ["goal-a", "goal-b"],
                "steps": [
                    {
                        "step_id": "step-shared",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 1},
                        "timing": "sequential",
                        "source_goal_ids": ["goal-a", "goal-b"],
                    }
                ],
                "goal_outcomes": [
                    {
                        "goal_id": "goal-a",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-shared"],
                    },
                    {
                        "goal_id": "goal-b",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-shared"],
                    },
                ],
            }
        )
        fingerprint = canonical_plan_fingerprint(plan)
        response = InteractionResponse(
            interaction_id="interaction-shared",
            skills=[
                SkillRequest(
                    request_id="request-shared",
                    skill_id="soridormi.nod_yes",
                    args={"count": 1},
                    timing="sequential",
                    requires_confirmation=True,
                    metadata={
                        "source": "goal_driven_canonical_plan",
                        "step_id": "step-shared",
                        "source_goal_ids": ["goal-a", "goal-b"],
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                    },
                )
            ],
            requires_confirmation=True,
            metadata={
                "canonical_plan": plan.model_dump(mode="json"),
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "planning_result": "composed_plan",
            },
        )
        manager.record_agent_result("sid-parent", response)
        dialogue = ConfirmationDialogue(ttl_s=30.0)
        pending = dialogue.begin(
            response,
            confirmed_request_ids={"request-shared"},
            origin_session_id="sid-parent",
            conversation_id=manager.conversation_id,
            language="en-US",
        )
        manager.record_confirmation_scope(
            sid="sid-parent",
            confirmation_id=pending.confirmation_id,
            interaction_id=response.interaction_id,
            fingerprint=pending.fingerprint,
            expires_at=pending.expires_at,
            response=response,
            confirmed_request_ids=set(pending.confirmed_request_ids),
        )

        class Runtime:
            called = False

            async def cancel_scope(self, directive):  # pragma: no cover
                self.called = True
                raise AssertionError("scope conflict must fail before dispatch")

        runtime = Runtime()
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.conversation_state = manager
        assistant.interaction_runtime = runtime
        assistant.confirmation_dialogue = dialogue
        assistant.session_log = lambda *args, **kwargs: None
        decision = RouteDecision(
            route="chat",
            intent="cancel_goal",
            confidence=0.95,
            source="llm",
            language="en-US",
        )

        with self.assertRaises(NamedGoalCancellationClosureError) as raised:
            asyncio.run(
                assistant._dispatch_named_goal_cancellation(
                    _cancel_resolution(["goal-a"]),
                    session_id="sid-cancel",
                    user_text="Cancel only the first goal.",
                    decision=decision,
                )
            )

        error = raised.exception
        self.assertEqual(error.stage, "confirmation_scope_conflict")
        self.assertFalse(error.runtime_dispatch_attempted)
        self.assertFalse(runtime.called)
        self.assertIsNotNone(dialogue.pending)
        assert dialogue.pending is not None
        self.assertEqual(dialogue.pending.confirmation_id, pending.confirmation_id)
        failure = assistant._named_goal_cancellation_failure_response(
            error,
            user_text="Cancel only the first goal.",
        )
        self.assertIsNotNone(failure)
        assert failure is not None
        self.assertEqual(
            failure.metadata["source"],
            "host_specific_goal_cancel_scope_conflict",
        )
        for goal_id in ("goal-a", "goal-b"):
            context = manager._task_context_by_goal_id(goal_id)
            assert context is not None
            self.assertNotEqual(context["status"], "cancelled")

    def test_partial_confirmation_rebuild_preserves_only_untargeted_goal(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-test")
        _create_goals(manager)
        plan = _plan()
        fingerprint = canonical_plan_fingerprint(plan)
        response = InteractionResponse(
            interaction_id="interaction-parent",
            speech=[
                InteractionSpeech(
                    id="speech-parent",
                    text="I will nod once and blink twice.",
                    timing="sequential",
                    metadata={
                        "covers_goal_ids": ["goal-a", "goal-b"],
                        "source_goal_ids": ["goal-a", "goal-b"],
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                    },
                )
            ],
            skills=[
                SkillRequest(
                    request_id="request-a",
                    skill_id="soridormi.nod_yes",
                    args={"count": 1},
                    timing="sequential",
                    requires_confirmation=True,
                    metadata={
                        "source": "goal_driven_canonical_plan",
                        "step_id": "step-a",
                        "source_goal_ids": ["goal-a"],
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                    },
                ),
                SkillRequest(
                    request_id="request-b",
                    skill_id="soridormi.blink_eyes",
                    args={"count": 2},
                    timing="sequential",
                    requires_confirmation=True,
                    metadata={
                        "source": "goal_driven_canonical_plan",
                        "step_id": "step-b",
                        "source_goal_ids": ["goal-b"],
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                    },
                ),
            ],
            requires_confirmation=True,
            metadata={
                "canonical_plan": plan.model_dump(mode="json"),
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "planning_result": "composed_plan",
            },
        )
        manager.record_agent_result("sid-parent", response)
        dialogue = ConfirmationDialogue(ttl_s=30.0)
        pending = dialogue.begin(
            response,
            confirmed_request_ids={"request-a", "request-b"},
            origin_session_id="sid-parent",
            conversation_id=manager.conversation_id,
            language="en-US",
        )
        manager.record_confirmation_scope(
            sid="sid-parent",
            confirmation_id=pending.confirmation_id,
            interaction_id=response.interaction_id,
            fingerprint=pending.fingerprint,
            expires_at=pending.expires_at,
            response=response,
            confirmed_request_ids=set(pending.confirmed_request_ids),
        )

        class Runtime:
            async def cancel_scope(self, directive):  # pragma: no cover
                raise AssertionError("pending confirmation must not dispatch runtime work")

        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.conversation_state = manager
        assistant.interaction_runtime = Runtime()
        assistant.confirmation_dialogue = dialogue
        assistant.session_log = lambda *args, **kwargs: None
        resolution = _cancel_resolution(["goal-a"])
        decision = RouteDecision(
            route="chat",
            intent="cancel_goal",
            confidence=0.95,
            source="llm",
            language="en-US",
        )

        _, metadata = asyncio.run(
            assistant._dispatch_named_goal_cancellation(
                resolution,
                session_id="sid-cancel",
                user_text="Cancel the nod but keep the blink.",
                decision=decision,
            )
        )

        replacement = dialogue.pending
        self.assertIsNotNone(replacement)
        assert replacement is not None
        self.assertNotEqual(replacement.confirmation_id, pending.confirmation_id)
        self.assertEqual(len(replacement.response.skills), 1)
        remaining = replacement.response.skills[0]
        self.assertEqual(remaining.skill_id, "soridormi.blink_eyes")
        self.assertNotEqual(remaining.request_id, "request-b")
        child_plan = CanonicalPlan.model_validate(
            replacement.response.metadata["canonical_plan"]
        )
        self.assertEqual(child_plan.goal_ids, ["goal-b"])
        self.assertEqual(child_plan.metadata["plan_relation"], "confirmation_remainder")
        self.assertEqual(metadata["confirmation_transition"]["old_confirmation_id"], pending.confirmation_id)

        cancelled = manager._task_context_by_goal_id("goal-a")
        preserved = manager._task_context_by_goal_id("goal-b")
        assert cancelled is not None and preserved is not None
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(preserved["status"], "awaiting_confirmation")
        self.assertEqual(
            preserved["confirmation"]["confirmation_id"],
            replacement.confirmation_id,
        )
        approved = dialogue.resolve("yes")
        self.assertEqual(approved.decision, "approved")
        self.assertEqual(
            approved.confirmed_request_ids,
            frozenset({remaining.request_id}),
        )


if __name__ == "__main__":
    unittest.main()
