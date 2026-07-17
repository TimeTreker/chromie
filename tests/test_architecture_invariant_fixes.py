from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.plan import CanonicalPlan


class CanonicalPlanOwnershipTests(unittest.TestCase):
    def test_complete_multi_goal_execute_requires_per_goal_outcomes(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "multi-goal execute or respond plans require per-goal outcomes",
        ):
            CanonicalPlan(
                plan_id="under-covered",
                planner_tier="deep",
                disposition="execute",
                coverage="complete",
                confidence=1.0,
                goal_ids=["goal-a", "goal-b"],
                steps=[
                    {
                        "step_id": "step-a",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "source_goal_ids": ["goal-a"],
                    }
                ],
                goal_satisfaction={
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal-a", "goal-b"],
                },
            )

    def test_goal_satisfaction_cannot_reference_unknown_goal(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "goal satisfaction references unknown goal IDs",
        ):
            CanonicalPlan(
                plan_id="foreign-satisfaction",
                planner_tier="deep",
                disposition="execute",
                coverage="complete",
                confidence=1.0,
                goal_ids=["goal-a"],
                steps=[
                    {
                        "step_id": "step-a",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "source_goal_ids": ["goal-a"],
                    }
                ],
                goal_satisfaction={
                    "score": 1.0,
                    "status": "exact",
                    "satisfied_goal_ids": ["goal-foreign"],
                },
            )

    def test_per_goal_satisfaction_cannot_reference_sibling_goal(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "per-goal outcome satisfaction may reference only its own goal ID",
        ):
            CanonicalPlan(
                plan_id="foreign-outcome-satisfaction",
                planner_tier="deep",
                disposition="execute",
                coverage="complete",
                confidence=1.0,
                goal_ids=["goal-a", "goal-b"],
                steps=[
                    {
                        "step_id": "step-a",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "source_goal_ids": ["goal-a"],
                    },
                    {
                        "step_id": "step-b",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "source_goal_ids": ["goal-b"],
                    },
                ],
                goal_outcomes=[
                    {
                        "goal_id": "goal-a",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-a"],
                        "satisfaction": {
                            "score": 1.0,
                            "status": "exact",
                            "satisfied_goal_ids": ["goal-b"],
                        },
                    },
                    {
                        "goal_id": "goal-b",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-b"],
                    },
                ],
            )

    def test_heterogeneous_goal_outcomes_require_mixed_top_level_disposition(self) -> None:
        with self.assertRaises(ValidationError):
            CanonicalPlan(
                plan_id="bad-top-level",
                planner_tier="deep",
                disposition="execute",
                coverage="complete",
                confidence=0.9,
                goal_ids=["goal-a", "goal-b"],
                steps=[
                    {
                        "step_id": "step-a",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "source_goal_ids": ["goal-a"],
                    }
                ],
                goal_outcomes=[
                    {
                        "goal_id": "goal-a",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-a"],
                    },
                    {
                        "goal_id": "goal-b",
                        "disposition": "clarify",
                        "coverage": "partial",
                        "unresolved": ["duration"],
                    },
                ],
            )

    def test_step_sources_must_match_executable_outcome_owners(self) -> None:
        with self.assertRaises(ValidationError):
            CanonicalPlan(
                plan_id="bad-owner",
                planner_tier="deep",
                disposition="execute",
                coverage="complete",
                confidence=0.9,
                goal_ids=["goal-a"],
                steps=[
                    {
                        "step_id": "step-a",
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "source_goal_ids": ["goal-a"],
                    }
                ],
                goal_outcomes=[
                    {
                        "goal_id": "goal-a",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": [],
                    }
                ],
            )

    def test_blocking_resolution_may_only_target_clarify_outcome(self) -> None:
        with self.assertRaises(ValidationError):
            CanonicalPlan(
                plan_id="bad-blocking-owner",
                planner_tier="deep",
                disposition="execute",
                coverage="complete",
                confidence=0.9,
                goal_ids=["goal-a"],
                steps=[
                    {
                        "step_id": "step-a",
                        "skill_id": "soridormi.walk_forward",
                        "args": {"duration_s": 1},
                        "source_goal_ids": ["goal-a"],
                    }
                ],
                parameter_resolutions=[
                    {
                        "step_id": "step-a",
                        "parameter": "duration_s",
                        "strategy": "ask_user",
                        "blocking": True,
                        "source_goal_ids": ["goal-a"],
                    }
                ],
                goal_outcomes=[
                    {
                        "goal_id": "goal-a",
                        "disposition": "execute",
                        "coverage": "complete",
                        "step_ids": ["step-a"],
                    }
                ],
            )


class AtomicSemanticOperationTests(unittest.TestCase):
    @staticmethod
    def create_operation(operation_id: str, goal_id: str) -> dict:
        return {
            "operation_id": operation_id,
            "operation": "create",
            "goal": {
                "goal_id": goal_id,
                "description": f"Handle {goal_id}.",
                "source_text": f"Handle {goal_id}.",
            },
        }

    def test_malformed_later_operation_is_rejected_before_mutation(self) -> None:
        manager = ConversationStateManager(base_conversation_id="atomic")

        with self.assertRaises(ValueError):
            manager.apply_semantic_task_operations_atomically(
                [
                    self.create_operation("create-a", "goal-a"),
                    {"operation_id": "bad", "operation": "modify"},
                ],
                sid="s1",
                user_text="Handle A.",
            )

        self.assertEqual(manager.active_goal_snapshots(), [])

    def test_state_rejection_rolls_back_earlier_operation(self) -> None:
        manager = ConversationStateManager(base_conversation_id="atomic")

        results = manager.apply_semantic_task_operations_atomically(
            [
                self.create_operation("create-a", "goal-a"),
                {
                    "operation_id": "modify-missing",
                    "operation": "modify",
                    "target_task_ids": ["missing-task"],
                    "goal_update": {"description": "Updated."},
                },
            ],
            sid="s1",
            user_text="Handle A.",
        )

        self.assertEqual(manager.active_goal_snapshots(), [])
        self.assertTrue(results[0]["rolled_back"])
        self.assertEqual(results[0]["reason"], "atomic_semantic_transaction_rolled_back")
        self.assertEqual(results[1]["reason"], "unknown_task_id")

    def test_atomic_batch_persists_once_after_all_operations_succeed(self) -> None:
        manager = ConversationStateManager(
            base_conversation_id="atomic",
            task_store_enabled=True,
        )
        with patch.object(manager, "persist_task_contexts", return_value=True) as persist:
            results = manager.apply_semantic_task_operations_atomically(
                [
                    self.create_operation("create-a", "goal-a"),
                    self.create_operation("create-b", "goal-b"),
                ],
                sid="s1",
                user_text="Handle A and B.",
            )

        self.assertTrue(all(item["applied"] for item in results))
        persist.assert_called_once_with()
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-a", "goal-b"],
        )

    def test_atomic_entrypoints_share_one_transaction_primitive(self) -> None:
        operation_manager = ConversationStateManager(base_conversation_id="operations")
        with patch.object(
            operation_manager,
            "_commit_semantic_state_transaction",
            wraps=operation_manager._commit_semantic_state_transaction,
        ) as commit:
            operation_manager.apply_semantic_task_operations_atomically(
                [self.create_operation("create-operation", "goal-operation")],
                sid="s1",
                user_text="Handle the operation goal.",
            )
        commit.assert_called_once()

        association_manager = ConversationStateManager(base_conversation_id="association")
        with patch.object(
            association_manager,
            "_commit_semantic_state_transaction",
            wraps=association_manager._commit_semantic_state_transaction,
        ) as commit:
            association_manager.apply_goal_association_resolution(
                {
                    "turn_id": "turn-association",
                    "new_goals": [
                        {
                            "goal_id": "goal-association",
                            "description": "Handle the associated goal.",
                            "source_text": "Handle the associated goal.",
                        }
                    ],
                    "confidence": 0.9,
                    "reason_summary": "A new independent goal.",
                },
                sid="s1",
                user_text="Handle the associated goal.",
                atomic=True,
            )
        commit.assert_called_once()

    def test_atomic_goal_association_persists_once(self) -> None:
        manager = ConversationStateManager(
            base_conversation_id="association",
            task_store_enabled=True,
        )
        with patch.object(manager, "persist_task_contexts", return_value=True) as persist:
            results = manager.apply_goal_association_resolution(
                {
                    "turn_id": "turn-persist",
                    "new_goals": [
                        {
                            "goal_id": "goal-persist",
                            "description": "Persist this goal.",
                            "source_text": "Persist this goal.",
                        }
                    ],
                    "confidence": 0.9,
                    "reason_summary": "A new independent goal.",
                },
                sid="s1",
                user_text="Persist this goal.",
                atomic=True,
            )

        self.assertTrue(all(item["applied"] for item in results))
        persist.assert_called_once_with()
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-persist"],
        )

    def test_persistence_failure_rolls_back_through_shared_primitive(self) -> None:
        manager = ConversationStateManager(
            base_conversation_id="atomic",
            task_store_enabled=True,
        )
        with patch.object(manager, "persist_task_contexts", return_value=False):
            manager.last_task_store_error = "disk unavailable"
            results = manager.apply_semantic_task_operations_atomically(
                [self.create_operation("create-a", "goal-a")],
                sid="s1",
                user_text="Handle A.",
            )

        self.assertEqual(manager.active_goal_snapshots(), [])
        self.assertFalse(results[0]["applied"])
        self.assertTrue(results[0]["rolled_back"])
        self.assertEqual(results[0]["reason"], "atomic_semantic_persistence_failed")
        self.assertEqual(results[0]["persistence_error"], "disk unavailable")


if __name__ == "__main__":
    unittest.main()
