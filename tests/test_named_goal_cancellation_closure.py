from __future__ import annotations

import asyncio
import unittest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.confirmation import ConfirmationDialogue
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.named_goal_cancellation import (
    NamedGoalCancellationClosureError,
    dispatch_goal_replacement,
    dispatch_named_goal_cancellation,
)
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution
from orchestrator.runtime.playback_transport import transport_for as playback_transport_for
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.reflex import CancellationDispatchReceipt
from shared.chromie_contracts.plan import canonical_plan_fingerprint


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
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                    "timing": "sequential",
                    "source_goal_ids": ["goal-a"],
                },
                {
                    "step_id": "step-b",
                    "capability_id": "soridormi.blink_eyes",
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
        goal_association=GoalAssociationResolution(
            resolution_status="resolved",
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


def _replacement_resolution() -> CognitiveRuntimeResolution:
    return CognitiveRuntimeResolution(
        mode="apply",
        status="applied",
        goal_association=GoalAssociationResolution(
            resolution_status="resolved",
            turn_id="turn-replace",
            new_goals=[
                {
                    "goal_id": "goal-c",
                    "description": "Wave once.",
                    "source_text": "Actually, wave instead.",
                    "supersedes_goal_ids": ["goal-a"],
                }
            ],
            confidence=0.99,
        ),
    )


class NamedGoalCancellationClosureTests(unittest.TestCase):

    def test_dispatch_bridge_reconciles_idle_named_goal_without_legacy_route_kwargs(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-bridge-test")
        _create_goals(manager)

        class _NoRuntimeWork:
            cancel_scope = None

        results, metadata = asyncio.run(
            dispatch_named_goal_cancellation(
                conversation_state=manager,
                interaction_runtime=_NoRuntimeWork(),
                confirmation_dialogue=None,
                resolution=_cancel_resolution(["goal-a"]),
                session_id="sid-cancel",
                user_text="Cancel the nod.",
                language="en-US",
            )
        )

        self.assertTrue(any(item.get("applied") for item in results))
        cancelled = manager._task_context_by_goal_id("goal-a")
        assert cancelled is not None
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(metadata["target_goal_ids"], ["goal-a"])
        self.assertEqual(metadata["cancellation_receipts"], [])


    def test_revoked_multi_goal_confirmation_releases_sibling_for_replanning(self) -> None:
        manager = ConversationStateManager(base_conversation_id="cancel-confirm-test")
        _create_goals(manager)
        dialogue = ConfirmationDialogue(clock=lambda: 100.0)
        response = InteractionResponse(
            interaction_id="interaction-confirm",
            capabilities=[
                {
                    "request_id": "request-a",
                    "capability_id": "soridormi.nod_yes",
                    "args": {"count": 1},
                    "requires_confirmation": True,
                    "metadata": {"source_goal_ids": ["goal-a"]},
                },
                {
                    "request_id": "request-b",
                    "capability_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                    "requires_confirmation": True,
                    "metadata": {"source_goal_ids": ["goal-b"]},
                },
            ],
            metadata={
                "confirmation_prompt": "Can I do those now?",
                "confirmation_prompt_source": "planner_wording_runtime_validated",
            },
        )
        pending = dialogue.begin(
            response,
            confirmed_request_ids={"request-a", "request-b"},
            origin_session_id="sid-confirm",
            conversation_id=manager.conversation_id,
        )
        manager.record_confirmation_scope(
            sid="sid-confirm",
            confirmation_id=pending.confirmation_id,
            interaction_id=response.interaction_id,
            fingerprint=pending.fingerprint,
            expires_at=pending.expires_at,
            response=response,
            confirmed_request_ids={"request-a", "request-b"},
        )
        _, transition = __import__(
            "orchestrator.runtime.named_goal_cancellation",
            fromlist=["_build_confirmation_remainder"],
        )._build_confirmation_remainder(
            confirmation_dialogue=dialogue, target_goal_ids={"goal-a"}
        )
        association = _cancel_resolution(["goal-a"]).goal_association
        assert association is not None and transition is not None

        manager.apply_goal_cancellation_resolution(
            association,
            receipts=[],
            confirmation_transition=transition,
            sid="sid-cancel",
            user_text="Cancel the nod.",
        )

        target = manager._task_context_by_goal_id("goal-a")
        sibling = manager._task_context_by_goal_id("goal-b")
        assert target is not None and sibling is not None
        self.assertEqual(target["status"], "cancelled")
        self.assertEqual(sibling["status"], "planning")
        self.assertEqual(sibling["commitment_state"], "evaluating")
        self.assertEqual(sibling["plan_status"], "confirmation_revoked_requires_replan")
        self.assertEqual(sibling["confirmation"]["status"], "revoked")
        self.assertEqual(sibling["metadata"]["remaining_request_ids"], [])

    def test_replacement_without_live_work_atomically_supersedes_old_and_creates_new(self) -> None:
        manager = ConversationStateManager(base_conversation_id="replace-test")
        _create_goals(manager)
        association = _replacement_resolution().goal_association
        assert association is not None

        results = manager.apply_goal_replacement_resolution(association, receipts=[], confirmation_transition=None, sid='sid-replace', user_text='Actually, wave instead.')

        self.assertTrue(any(item.get("applied") for item in results))
        old = manager._task_context_by_goal_id("goal-a")
        new = manager._task_context_by_goal_id("goal-c")
        assert old is not None and new is not None
        self.assertEqual(old["semantic_goal"]["responsibility_status"], "superseded")
        self.assertEqual(old["metadata"]["superseded_by_goal_ids"], ["goal-c"])
        self.assertEqual(new["semantic_goal"]["responsibility_status"], "open")
        self.assertEqual(new["semantic_goal"]["supersedes_goal_ids"], ["goal-a"])


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
            selected_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            active_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            provider_cancel_failure_evidence=(
                {
                    "interaction_id": "interaction-parent",
                    "request_id": "request-a",
                    "error": "provider failed",
                },
            ),
        )

        with self.assertRaisesRegex(
            ValueError, "provider_cancel_failure"
        ):
            manager.apply_goal_cancellation_resolution(resolution, receipts=[receipt], confirmation_transition=None, sid='sid-cancel', user_text='Cancel the nod.')
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

        playback_transport_for(assistant).abort_output_stream = abort_output_stream
        assistant.session_log = lambda *args, **kwargs: None

        asyncio.run(
            assistant._cancel_interaction_speech(
                CapabilityRequest(
                    request_id="speech-a",
                    capability_id="chromie.speak",
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
            selected_request_bindings=(
                {"interaction_id": "interaction-a", "request_id": "request-a"},
                {"interaction_id": "interaction-b", "request_id": "request-b"},
            ),
            active_request_bindings=(
                {"interaction_id": "interaction-a", "request_id": "request-a"},
                {"interaction_id": "interaction-b", "request_id": "request-b"},
            ),
            cancel_requested_request_bindings=(
                {"interaction_id": "interaction-a", "request_id": "request-a"},
                {"interaction_id": "interaction-b", "request_id": "request-b"},
            ),
            widened=True,
            widening_reason=(
                "provider_supports_only_global_embodied_motion_cancel"
            ),
        )

        results = manager.apply_goal_cancellation_resolution(association, receipts=[receipt], confirmation_transition=None, sid='sid-cancel', user_text='Cancel the nod.')

        self.assertTrue(any(item.get("applied") for item in results))
        target = manager._task_context_by_goal_id("goal-a")
        coaffected = manager._task_context_by_goal_id("goal-b")
        assert target is not None and coaffected is not None
        self.assertEqual(target["status"], "cancelled")
        self.assertEqual(coaffected["status"], "recoverable")
        self.assertEqual(
            coaffected["semantic_goal"]["responsibility_status"], "open"
        )
        self.assertEqual(
            coaffected["plan_status"], "interrupted_by_widened_scope"
        )
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
            selected_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            active_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            cancel_requested_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
        )

        results = manager.apply_goal_cancellation_resolution(association, receipts=[receipt], confirmation_transition=None, sid='sid-cancel', user_text='Cancel the nod.')

        self.assertTrue(
            any(
                item.get("reason") == "atomic_cancellation_persistence_failed"
                for item in results
            )
        )
        unchanged = manager._task_context_by_goal_id("goal-a")
        assert unchanged is not None
        self.assertEqual(unchanged["status"], "running")






if __name__ == "__main__":
    unittest.main()


class RetainedGoalWorkCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_goal_stop_cancels_current_and_preserved_prior_plan_work(self):
        from orchestrator.runtime.capability_runtime import CapabilityDefinition, MockCapabilityProvider
        from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator

        state = ConversationStateManager(base_conversation_id="multi-plan-stop")
        _create_goals(state)
        coordinator = InteractionRuntimeCoordinator(lambda _args: {"scheduled": True})
        coordinator.registry.register(CapabilityDefinition(capability_id="test.work", provider_id="test",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={"type": "object", "properties": {"args": {"type": "object", "properties": {}, "additionalProperties": False}}, "additionalProperties": False},
            interruptible=True, metadata={"cancellation_granularity": "request"}))
        coordinator.runtime.register_provider(MockCapabilityProvider("test", delay_s=1))
        coordinator.runtime.goal_state_provider = lambda: [*state.active_goal_snapshots(), *state.recent_goal_snapshots()]

        def response(name):
            plan = CanonicalPlan(plan_id="plan-" + name, planner_tier="fast", disposition="execute", coverage="complete",
                goal_ids=["goal-a"], confidence=0.99, steps=[{"step_id": name, "capability_id": "test.work", "source_goal_ids": ["goal-a"]}])
            return InteractionResponse(interaction_id=name, capabilities=[{"request_id": name, "capability_id": "test.work",
                "metadata": {"source_goal_ids": ["goal-a"], "canonical_plan_id": plan.plan_id, "canonical_plan_fingerprint": canonical_plan_fingerprint(plan)}}],
                metadata={"goal_ids": ["goal-a"], "turn_id": "turn-" + name, "canonical_plan": plan.model_dump(mode="json"),
                    "canonical_plan_id": plan.plan_id, "canonical_plan_fingerprint": canonical_plan_fingerprint(plan), "planning_result": "composed_plan"})

        old = response("old")
        state.record_interaction_response("old", old)
        first = await coordinator.runtime.submit(old)
        snapshot = await coordinator.runtime.planning_state_snapshot(["goal-a"], "turn-new")
        new = response("new")
        new.metadata["retained_work_activities"] = coordinator.runtime.planning_work_activities(snapshot)
        new.metadata["planning_commit"] = await coordinator.runtime.reserve_planning_submission(snapshot,
            plan_id=new.metadata["canonical_plan_id"], fingerprint=new.metadata["canonical_plan_fingerprint"], prepared_activity_ids=[])
        await coordinator.runtime.record_planning_submission(new, lambda: state.record_interaction_response("new", new))
        second = await coordinator.runtime.submit(new)
        bindings = state.goal_cancellation_bindings(["goal-a"])[0]["runtime_bindings"]
        self.assertEqual({item["interaction_id"] for item in bindings}, {"old", "new"})
        await dispatch_named_goal_cancellation(conversation_state=state, interaction_runtime=coordinator,
            confirmation_dialogue=None, resolution=_cancel_resolution(["goal-a"]), session_id="cancel", user_text="停止这个任务", language="zh-CN")
        results = await asyncio.gather(coordinator.runtime.wait_terminal(first), coordinator.runtime.wait_terminal(second))
        self.assertEqual([result.results[0].status for result in results], ["cancelled", "cancelled"])
        goal = state.goal_cancellation_bindings(["goal-a"])[0]
        self.assertEqual(goal["responsibility_status"], "cancelled")
        self.assertEqual(goal["remaining_request_ids"], [])
