from __future__ import annotations

import unittest

from orchestrator.orchestrator import VoiceAssistant


class _GoalState:
    max_pending_tasks = 8

    def apply_goal_association_resolution(self, *args, **kwargs):
        del args, kwargs
        return [
            {
                "applied": True,
                "operation": "create",
                "goal_id": "goal-weather",
                "task_id": "task-weather",
            }
        ]

    def snapshot(self):
        return {
            "task_contexts": [{}, {}],
            "active_task_contexts": [{}],
            "recent_goal_snapshots": [
                {
                    "goal_id": "goal-old",
                    "responsibility_status": "satisfied",
                    "work_status": "done",
                }
            ],
        }

    def active_goal_snapshots(self, *, limit):
        if limit != self.max_pending_tasks:
            raise AssertionError("unexpected active-goal limit")
        return [{"goal_id": "goal-weather"}]


class GoalCreationObservabilityTests(unittest.TestCase):
    def test_new_goal_logs_post_commit_counts_on_main_thread(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.conversation_state = _GoalState()

        with self.assertLogs("chromie-orchestrator", level="INFO") as captured:
            results = assistant._apply_cognitive_goal_association_stage(
                object(),
                sid="sid-weather",
                user_text="今天晚上重庆热不热？",
                route="tool",
                intent="capability:chromie.weather.lookup",
                source="test",
            )

        self.assertEqual(results[0]["operation"], "create")
        joined = "\n".join(captured.output)
        self.assertIn("goal_list_after_association", joined)
        self.assertIn("applied_operations=", joined)
        self.assertIn("created_goals=1", joined)
        self.assertIn("task_contexts=2", joined)
        self.assertIn("active_tasks=1", joined)
        self.assertIn("active_goals=1", joined)
        self.assertIn("thread=MainThread", joined)
        self.assertIn("is_main_thread=True", joined)
        self.assertIn("active_goal_list=", joined)
        self.assertIn("goal-weather", joined)
        self.assertIn("recent_terminal_goal_list=", joined)
        self.assertIn("goal-old", joined)


    def test_non_create_goal_state_change_also_logs_full_goal_list(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        class ModifyState(_GoalState):
            def apply_goal_association_resolution(self, *args, **kwargs):
                del args, kwargs
                return [
                    {
                        "applied": True,
                        "operation": "modify",
                        "goal_id": "goal-weather",
                        "task_id": "task-weather",
                    }
                ]

        assistant.conversation_state = ModifyState()
        with self.assertLogs("chromie-orchestrator", level="INFO") as captured:
            results = assistant._apply_cognitive_goal_association_stage(
                object(),
                sid="sid-weather-followup",
                user_text="改成明天下午。",
                route="tool",
                intent="weather_query",
                source="test",
            )

        self.assertEqual(results[0]["operation"], "modify")
        joined = "\n".join(captured.output)
        self.assertIn("goal_list_after_association", joined)
        self.assertIn('"operation":"modify"', joined)
        self.assertIn("active_goal_list=", joined)
        self.assertIn("goal-weather", joined)

    def test_count_logging_failure_does_not_undo_goal_commit(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        class BrokenSnapshotState(_GoalState):
            def snapshot(self):
                raise RuntimeError("snapshot unavailable")

        assistant.conversation_state = BrokenSnapshotState()
        with self.assertLogs("chromie-orchestrator", level="WARNING") as captured:
            results = assistant._apply_cognitive_goal_association_stage(
                object(),
                sid="sid-weather",
                user_text="今天晚上重庆热不热？",
                route="tool",
                intent="capability:chromie.weather.lookup",
                source="test",
            )

        self.assertEqual(results[0]["operation"], "create")
        self.assertIn("goal_list_after_association_log_failed", "\n".join(captured.output))

    def test_replayed_create_does_not_log_a_new_goal_count(self):
        assistant = VoiceAssistant.__new__(VoiceAssistant)

        class ReplayState(_GoalState):
            def apply_goal_association_resolution(self, *args, **kwargs):
                del args, kwargs
                return [
                    {
                        "applied": False,
                        "operation": "create",
                        "reason": "operation_already_applied",
                    }
                ]

        assistant.conversation_state = ReplayState()
        with self.assertNoLogs("chromie-orchestrator", level="INFO"):
            results = assistant._apply_cognitive_goal_association_stage(
                object(),
                sid="sid-replay",
                user_text="repeat",
                route="tool",
                intent="test",
                source="test",
            )
        self.assertFalse(results[0]["applied"])


if __name__ == "__main__":
    unittest.main()
