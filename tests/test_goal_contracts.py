from __future__ import annotations

import unittest

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.goal import (
    ActiveGoalSnapshot,
    GoalAssociation,
    GoalSet,
    stable_goal_operation_id,
)
from shared.chromie_contracts.semantic_task import SemanticGoal, TaskContextSnapshot


class GoalContractTests(unittest.TestCase):
    def test_goal_association_requires_existing_target_except_new(self) -> None:
        with self.assertRaises(ValueError):
            GoalAssociation(
                association_id="assoc-1",
                relationship="modify",
                target_goal_ids=[],
            )

        association = GoalAssociation(
            association_id="assoc-2",
            relationship="new",
            target_goal_ids=[],
            confidence=0.9,
        )
        self.assertEqual(association.relationship, "new")

    def test_goal_set_preserves_independent_goals(self) -> None:
        goal_set = GoalSet(
            turn_id="turn-weather-coffee",
            goals=[
                SemanticGoal(
                    goal_id="goal-weather",
                    description="Report the current weather.",
                    source_text="Check the weather and bring coffee.",
                ),
                SemanticGoal(
                    goal_id="goal-coffee",
                    description="Obtain coffee for the user.",
                    source_text="Check the weather and bring coffee.",
                ),
            ],
            confidence=0.97,
        )
        self.assertEqual([goal.goal_id for goal in goal_set.goals], ["goal-weather", "goal-coffee"])

    def test_replay_safe_goal_operation_id_is_stable_and_target_order_independent(self) -> None:
        first = stable_goal_operation_id(
            turn_id="turn-42",
            ordinal=0,
            relationship="modify",
            target_goal_ids=["goal-b", "goal-a"],
        )
        second = stable_goal_operation_id(
            turn_id="turn-42",
            ordinal=0,
            relationship="modify",
            target_goal_ids=["goal-a", "goal-b"],
        )
        different = stable_goal_operation_id(
            turn_id="turn-42",
            ordinal=1,
            relationship="modify",
            target_goal_ids=["goal-a", "goal-b"],
        )
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)

    def test_task_snapshot_maps_to_goal_snapshot_without_losing_version_or_gaps(self) -> None:
        task = TaskContextSnapshot(
            task_id="task-coffee",
            status="waiting_for_user",
            semantic_goal=SemanticGoal(
                description="Obtain coffee for the user.",
                source_text="Bring me coffee.",
                constraints={"temperature": "unknown"},
            ),
            goal_version=3,
            plan_version=2,
            open_information_gaps=[
                {
                    "gap_id": "coffee-temperature",
                    "description": "Preferred coffee temperature.",
                    "preferred_resolution": "ask_user",
                }
            ],
            commitment_state="waiting_for_user",
            last_user_update="Make it the usual.",
            metadata={"updated_ms": 12345},
        )

        goal = ActiveGoalSnapshot.from_task_snapshot(task)

        self.assertEqual(goal.goal_id, "task-coffee")
        self.assertEqual(goal.goal_version, 3)
        self.assertEqual(goal.goal.version, 3)
        self.assertEqual(goal.source_task_id, "task-coffee")
        self.assertEqual(goal.open_information_gaps[0].gap_id, "coffee-temperature")
        self.assertEqual(goal.metadata["compatibility_source"], "semantic_task")
        self.assertEqual(goal.metadata["plan_version"], 2)


class ActiveGoalProjectionTests(unittest.TestCase):
    @staticmethod
    def _create_goal(manager: ConversationStateManager, operation_id: str, description: str) -> None:
        manager.record_user_turn(
            operation_id,
            description,
            route="deep_thought",
            intent="create semantic goal",
            metadata={
                "source": "llm",
                "semantic_task_operations": [
                    {
                        "operation_id": operation_id,
                        "operation": "create",
                        "confidence": 0.99,
                        "goal": {
                            "description": description,
                            "source_text": description,
                        },
                        "requires_replan": True,
                    }
                ],
            },
        )

    def test_active_goal_projection_is_bounded_and_goal_first(self) -> None:
        manager = ConversationStateManager(max_pending_tasks=4)
        self._create_goal(manager, "op-one", "Check the weather.")
        self._create_goal(manager, "op-two", "Obtain coffee.")
        self._create_goal(manager, "op-three", "Remember the user's preference.")

        goals = manager.active_goal_snapshots(limit=2)

        self.assertEqual(len(goals), 2)
        self.assertEqual(goals[-1]["goal"]["description"], "Remember the user's preference.")
        self.assertIn("goal_id", goals[0])
        self.assertIn("source_task_id", goals[0])
        self.assertNotIn("task_relation", goals[0])

    def test_zero_limit_returns_no_goals(self) -> None:
        manager = ConversationStateManager()
        self._create_goal(manager, "op-one", "Check the weather.")
        self.assertEqual(manager.active_goal_snapshots(limit=0), [])


if __name__ == "__main__":
    unittest.main()
