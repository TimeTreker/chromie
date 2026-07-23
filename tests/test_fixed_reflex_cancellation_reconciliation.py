from __future__ import annotations

import unittest

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest
from shared.chromie_contracts.reflex import CancellationDispatchReceipt


def _create_goal(manager: ConversationStateManager, goal_id: str, text: str) -> None:
    manager.apply_semantic_task_operations_atomically(
        [
            {
                "operation_id": f"create-{goal_id}",
                "operation": "create",
                "goal": {
                    "goal_id": goal_id,
                    "description": text,
                    "source_text": text,
                },
            }
        ],
        sid="sid-create",
        user_text=text,
    )


def _bind_execution(
    manager: ConversationStateManager,
    *,
    goal_id: str,
    interaction_id: str,
    request_ids: list[str],
    skill_ids: list[str] | None = None,
    status: str = "running",
) -> None:
    skills = skill_ids or ["soridormi.walk_forward"] * len(request_ids)
    manager._record_goal_pending_execution(
        sid="sid-run",
        goal_id=goal_id,
        status=status,
        summary=", ".join(skills),
        request_ids=request_ids,
        planning_result="execute",
        planned_skills=[
            {
                "request_id": request_id,
                "skill_id": skill_id,
                "source_goal_ids": [goal_id],
            }
            for request_id, skill_id in zip(request_ids, skills, strict=True)
        ],
        confirmation_pending=False,
        interaction_id=interaction_id,
        turn_id="turn-parent",
        canonical_plan_id="plan-parent",
        canonical_plan_fingerprint="fingerprint-parent",
    )


class FixedReflexCancellationReconciliationTests(unittest.TestCase):
    def test_current_interaction_cancels_every_selected_goal_request(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reflex-current")
        for goal_id, request_id in (("goal-a", "request-a"), ("goal-b", "request-b")):
            _create_goal(manager, goal_id, goal_id)
            _bind_execution(
                manager,
                goal_id=goal_id,
                interaction_id="interaction-parent",
                request_ids=[request_id],
            )

        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-stop",
            requested_scope="current_interaction",
            effective_scope="current_interaction",
            interaction_ids=("interaction-parent",),
            affected_goal_ids=("goal-a", "goal-b"),
            selected_request_ids=("request-a", "request-b"),
            selected_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
                {"interaction_id": "interaction-parent", "request_id": "request-b"},
            ),
            active_request_ids=("request-a",),
            active_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            queued_request_ids=("request-b",),
            queued_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-b"},
            ),
            cancel_requested_request_ids=("request-a",),
            cancel_requested_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
        )

        results = manager.apply_reflex_cancellation_receipt(
            receipt,
            revoked_confirmation=None,
            sid="sid-stop",
            user_text="Stop.",
            intent="cancel_current_interaction",
        )

        self.assertTrue(any(item.get("operation") == "fixed_reflex_receipt_reconciliation" for item in results))
        for goal_id in ("goal-a", "goal-b"):
            context = manager._task_context_by_goal_id(goal_id)
            assert context is not None
            self.assertEqual(context["status"], "cancelled")
            self.assertEqual(context["metadata"]["remaining_request_ids"], [])
            self.assertEqual(
                context["metadata"]["request_statuses"][
                    "request-a" if goal_id == "goal-a" else "request-b"
                ],
                "cancelled",
            )

    def test_motion_scope_partially_cancels_goal_and_preserves_other_work(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reflex-motion")
        _create_goal(manager, "goal-a", "Walk and report status.")
        _bind_execution(
            manager,
            goal_id="goal-a",
            interaction_id="interaction-parent",
            request_ids=["request-motion", "request-report"],
            skill_ids=["soridormi.walk_forward", "chromie.report"],
        )
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-stop-motion",
            requested_scope="embodied_motion",
            effective_scope="embodied_motion",
            interaction_ids=("interaction-parent",),
            affected_goal_ids=("goal-a",),
            selected_request_ids=("request-motion",),
            selected_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-motion"},
            ),
            active_request_ids=("request-motion",),
            active_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-motion"},
            ),
            cancel_requested_request_ids=("request-motion",),
            cancel_requested_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-motion"},
            ),
        )

        manager.apply_reflex_cancellation_receipt(
            receipt,
            revoked_confirmation=None,
            sid="sid-stop",
            user_text="Stop moving.",
            intent="stop_embodied_motion",
        )

        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        self.assertEqual(context["status"], "recoverable")
        self.assertEqual(context["plan_status"], "partially_cancelled")
        self.assertEqual(
            context["metadata"]["remaining_request_ids"],
            ["request-report"],
        )
        self.assertEqual(
            context["metadata"]["request_statuses"]["request-motion"],
            "cancelled",
        )

    def test_provider_failure_keeps_goal_recoverable_and_uncertain(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reflex-failure")
        _create_goal(manager, "goal-a", "Walk.")
        _bind_execution(
            manager,
            goal_id="goal-a",
            interaction_id="interaction-parent",
            request_ids=["request-a"],
        )
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-stop-motion",
            requested_scope="embodied_motion",
            effective_scope="embodied_motion",
            interaction_ids=("interaction-parent",),
            affected_goal_ids=("goal-a",),
            selected_request_ids=("request-a",),
            selected_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            active_request_ids=("request-a",),
            active_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            cancel_requested_request_ids=("request-a",),
            cancel_requested_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            provider_cancel_failures=("request-a:provider timeout",),
            provider_cancel_failure_evidence=(
                {
                    "interaction_id": "interaction-parent",
                    "request_id": "request-a",
                    "error": "provider timeout",
                },
            ),
        )

        manager.apply_reflex_cancellation_receipt(
            receipt,
            revoked_confirmation=None,
            sid="sid-stop",
            user_text="Stop moving.",
            intent="stop_embodied_motion",
        )

        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        self.assertEqual(context["status"], "recoverable")
        self.assertEqual(context["plan_status"], "cancellation_uncertain")
        self.assertEqual(
            context["metadata"]["remaining_request_ids"],
            ["request-a"],
        )
        self.assertEqual(
            context["metadata"]["request_statuses"]["request-a"],
            "cancellation_uncertain",
        )

    def test_global_host_preflight_cancel_is_unknown_start_not_success(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reflex-host")
        _create_goal(manager, "goal-a", "Walk.")
        _bind_execution(
            manager,
            goal_id="goal-a",
            interaction_id="interaction-preflight",
            request_ids=["request-a"],
            status="scheduled",
        )
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-emergency",
            requested_scope="global_emergency",
            effective_scope="global_emergency",
            interaction_ids=("interaction-preflight",),
            host_interaction_ids=("interaction-preflight",),
            dispatch_failures=("skill_runtime:RuntimeError:unavailable",),
            host_task_cancel_requested_interaction_ids=("interaction-preflight",),
            emergency_stop_evidence={
                "status": "unconfirmed",
                "output": {"stopped": True, "emergency": True, "safe_idle": False},
            },
        )

        manager.apply_reflex_cancellation_receipt(
            receipt,
            revoked_confirmation=None,
            sid="sid-emergency",
            user_text="Emergency stop!",
            intent="global_emergency_stop",
        )

        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        self.assertEqual(context["status"], "recoverable")
        self.assertEqual(context["plan_status"], "cancellation_uncertain")
        self.assertFalse(context["metadata"]["safe_idle_verified"])
        self.assertIn(
            "host_workflow_cancel_requested_unknown_start",
            context["metadata"]["reflex_cancellation_uncertainty_reasons"],
        )

    def test_revoked_confirmation_is_committed_in_same_transaction(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reflex-confirmation")
        _create_goal(manager, "goal-a", "Walk.")
        response = InteractionResponse(
            interaction_id="interaction-confirm",
            skills=[
                SkillRequest(
                    request_id="request-a",
                    skill_id="soridormi.walk_forward",
                    requires_confirmation=True,
                    metadata={"source_goal_ids": ["goal-a"]},
                )
            ],
        )
        manager.record_confirmation_scope(
            sid="sid-confirm",
            confirmation_id="confirmation-a",
            interaction_id="interaction-confirm",
            fingerprint="confirmation-fingerprint",
            expires_at=100.0,
            response=response,
            confirmed_request_ids={"request-a"},
        )
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-stop",
            requested_scope="current_interaction",
            effective_scope="current_interaction",
        )

        manager.apply_reflex_cancellation_receipt(
            receipt,
            revoked_confirmation={
                "confirmation_id": "confirmation-a",
                "confirmed_request_ids": ["request-a"],
            },
            sid="sid-stop",
            user_text="Stop.",
            intent="cancel_current_interaction",
        )

        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        self.assertEqual(context["status"], "cancelled")
        self.assertEqual(
            context["confirmation"]["status"],
            "operational_interrupt",
        )
        confirmation_records = [
            task
            for task in manager._pending_tasks
            if (task.get("metadata") or {}).get("confirmation_id")
            == "confirmation-a"
        ]
        self.assertTrue(confirmation_records)
        self.assertTrue(
            all(task["status"] == "cancelled" for task in confirmation_records)
        )

    def test_output_only_does_not_cancel_embodied_goal_for_pre_action_speech(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reflex-output")
        _create_goal(manager, "goal-a", "Walk.")
        _bind_execution(
            manager,
            goal_id="goal-a",
            interaction_id="interaction-parent",
            request_ids=["request-motion"],
        )
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-quiet",
            requested_scope="output_only",
            effective_scope="output_only",
            interaction_ids=("interaction-parent",),
            affected_goal_ids=("goal-a",),
            selected_request_ids=("speech-pre-action",),
            selected_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "speech-pre-action"},
            ),
            active_request_ids=("speech-pre-action",),
            active_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "speech-pre-action"},
            ),
            cancel_requested_request_ids=("speech-pre-action",),
            cancel_requested_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "speech-pre-action"},
            ),
            output_invalidation_requested=True,
        )

        manager.apply_reflex_cancellation_receipt(
            receipt,
            revoked_confirmation=None,
            sid="sid-quiet",
            user_text="Stop talking.",
            intent="stop_current_output",
        )

        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        self.assertEqual(context["status"], "running")
        self.assertEqual(
            context["metadata"]["remaining_request_ids"],
            ["request-motion"],
        )
        self.assertTrue(context["metadata"]["output_cancellation_recorded"])

    def test_persistence_failure_rolls_back_fixed_reflex_goal_changes(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reflex-persist")
        _create_goal(manager, "goal-a", "Walk.")
        _bind_execution(
            manager,
            goal_id="goal-a",
            interaction_id="interaction-parent",
            request_ids=["request-a"],
        )
        manager.task_store_enabled = True

        def fail_persistence() -> bool:
            manager.last_task_store_error = "disk unavailable"
            return False

        manager.persist_task_contexts = fail_persistence  # type: ignore[method-assign]
        receipt = CancellationDispatchReceipt(
            source_turn_id="turn-stop",
            requested_scope="current_interaction",
            effective_scope="current_interaction",
            interaction_ids=("interaction-parent",),
            affected_goal_ids=("goal-a",),
            selected_request_ids=("request-a",),
            selected_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
            queued_request_ids=("request-a",),
            queued_request_bindings=(
                {"interaction_id": "interaction-parent", "request_id": "request-a"},
            ),
        )

        results = manager.apply_reflex_cancellation_receipt(
            receipt,
            revoked_confirmation=None,
            sid="sid-stop",
            user_text="Stop.",
            intent="cancel_current_interaction",
        )

        self.assertTrue(
            any(
                item.get("reason")
                == "atomic_reflex_cancellation_persistence_failed"
                for item in results
            )
        )
        context = manager._task_context_by_goal_id("goal-a")
        assert context is not None
        self.assertEqual(context["status"], "running")


if __name__ == "__main__":
    unittest.main()
