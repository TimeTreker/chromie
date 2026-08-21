from __future__ import annotations

import unittest

from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.goal_list_console import (
    goal_list_change_by_task,
    goal_list_item_text,
)


class GoalListConsoleLoggingTests(unittest.TestCase):
    def test_goal_list_item_is_compact_and_goal_focused(self) -> None:
        snapshot = {
            "goal_id": "goal_123",
            "goal_version": 7,
            "responsibility_status": "open",
            "work_status": "planning",
            "source_task_id": "task_1",
            "goal": {
                "description": "bring the bottle of water",
                "metadata": {"should_not_print": "nested"},
            },
            "metadata": {
                "task_relation": "continue_task",
                "execution_binding": {"canonical_plan_id": "plan_noise"},
            },
        }

        line = goal_list_item_text(
            snapshot,
            bucket="active",
            index=1,
            total=2,
            change="associated",
        )

        self.assertIn("change=associated", line)
        self.assertIn("goal_id=goal_123", line)
        self.assertIn("responsibility=open", line)
        self.assertIn("work=planning", line)
        self.assertIn("relation=continue_task", line)
        self.assertIn("description='bring the bottle of water'", line)
        self.assertNotIn("execution_binding", line)
        self.assertNotIn("plan_noise", line)
        self.assertNotIn("should_not_print", line)

    def test_committed_operations_mark_only_changed_goal_tasks(self) -> None:
        changes = goal_list_change_by_task(
            [
                {
                    "applied": True,
                    "operation": "create",
                    "task_id": "task_new",
                },
                {
                    "applied": True,
                    "relationship": "continue",
                    "task_id": "task_existing",
                },
                {
                    "applied": False,
                    "operation": "modify",
                    "task_id": "task_rejected",
                },
            ]
        )

        self.assertEqual(changes["task_new"], "added")
        self.assertEqual(changes["task_existing"], "associated")
        self.assertNotIn("task_rejected", changes)


if __name__ == "__main__":
    unittest.main()
