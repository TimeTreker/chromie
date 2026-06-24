from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.interaction import InteractionResponse


class ConversationStateTests(unittest.TestCase):
    def test_explicit_reset_starts_new_conversation_and_clears_history(self) -> None:
        manager = ConversationStateManager(base_conversation_id="test")
        manager.record_user_turn("s1", "check the weather", route="tool", intent="weather_query")
        original_id = manager.conversation_id

        boundary = manager.prepare_for_user_text("new topic", "s2")

        self.assertTrue(boundary["started_new"])
        self.assertNotEqual(manager.conversation_id, original_id)
        self.assertEqual(manager.get_history(), [])

    def test_followup_keeps_context_after_soft_idle(self) -> None:
        manager = ConversationStateManager(soft_idle_timeout_sec=10, hard_idle_timeout_sec=100)
        manager.record_user_turn("s1", "check the weather")
        manager.last_activity_ms -= 20_000

        boundary = manager.prepare_for_user_text("what about it?", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(boundary["reason"], "followup_reference")

    def test_pending_task_keeps_context_for_new_topic_like_text(self) -> None:
        manager = ConversationStateManager(soft_idle_timeout_sec=10, hard_idle_timeout_sec=100)
        manager.record_user_turn("s1", "check the weather")
        manager.record_pending_task(sid="s1", task_type="weather", summary="weather lookup")
        manager.last_activity_ms -= 20_000

        boundary = manager.prepare_for_user_text("tell me another thing", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(boundary["reason"], "active_pending_task")

    def test_history_respects_turn_and_character_limits(self) -> None:
        manager = ConversationStateManager(max_turns=3, max_context_chars=200)
        for index in range(5):
            manager.record_user_turn(f"s{index}", f"turn {index}")

        history = manager.get_history()

        self.assertEqual(len(history), 3)
        self.assertEqual([turn["text"] for turn in history], ["turn 2", "turn 3", "turn 4"])

    def test_from_env_reads_overrides(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "ORCH_ENABLE_CONVERSATION_STATE": "0",
                "ORCH_CONVERSATION_MAX_TURNS": "4",
            },
            clear=False,
        ):
            manager = ConversationStateManager.from_env()

        self.assertFalse(manager.enabled)
        self.assertEqual(manager.max_turns, 4)

    def test_interaction_response_records_speech_and_named_skill(self) -> None:
        manager = ConversationStateManager()

        manager.record_agent_result(
            "s1",
            InteractionResponse(
                speech=[{"text": "Hello."}],
                skills=[{"skill_id": "soridormi.nod_yes"}],
            ),
        )

        self.assertEqual(manager.get_history()[-1]["text"], "Hello.")
        self.assertEqual(
            manager.snapshot()["active_pending_tasks"][-1]["summary"],
            "soridormi.nod_yes",
        )

    def test_native_interaction_metadata_records_memory_update(self) -> None:
        manager = ConversationStateManager()

        manager.record_agent_result(
            "s1",
            InteractionResponse(
                metadata={
                    "memory_updates": [
                        {
                            "type": "pending_task",
                            "key": "weather",
                            "value": {
                                "type": "weather",
                                "status": "pending",
                                "summary": "weather lookup",
                            },
                        }
                    ]
                }
            ),
        )

        self.assertEqual(
            manager.snapshot()["active_pending_tasks"][-1]["summary"],
            "weather lookup",
        )

    def test_confirmation_pending_task_can_be_closed(self) -> None:
        manager = ConversationStateManager()
        manager.record_pending_task(
            sid="s1",
            task_type="confirmation",
            status="awaiting_confirmation",
            metadata={"confirmation_id": "confirm-1"},
        )

        updated = manager.update_pending_task_status(
            metadata_key="confirmation_id",
            metadata_value="confirm-1",
            status="done",
        )

        self.assertTrue(updated)
        self.assertEqual(manager.snapshot()["active_pending_tasks"], [])

    def test_session_memory_summarizes_active_task_and_reset_clears_it(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        manager.record_user_turn("s1", "walk forward", route="robot_action", intent="capability:soridormi.walk_velocity")
        manager.record_pending_task(
            sid="s1",
            task_type="robot_action",
            summary="soridormi.walk_velocity",
            metadata={"request_ids": ["skill-1"], "remaining_request_ids": ["skill-1"]},
        )

        memory = manager.snapshot()["session_memory"]

        self.assertEqual(memory["conversation_id"], "session")
        self.assertEqual(memory["recent_user_request"], "walk forward")
        self.assertEqual(memory["current_task"]["summary"], "soridormi.walk_velocity")

        boundary = manager.prepare_for_user_text("new session", "s2")

        self.assertTrue(boundary["started_new"])
        self.assertIsNone(manager.snapshot()["session_memory"]["current_task"])
        self.assertEqual(manager.get_history(), [])

    def test_completed_skill_request_closes_active_task_and_can_be_pruned(self) -> None:
        manager = ConversationStateManager(completed_task_retention_sec=0)
        manager.record_agent_result(
            "s1",
            InteractionResponse(
                skills=[{"request_id": "skill-1", "skill_id": "soridormi.nod_yes"}],
            ),
        )

        updated = manager.update_pending_task_status_for_request_id(
            request_id="skill-1",
            status="completed",
        )

        self.assertTrue(updated)
        self.assertEqual(manager.snapshot()["active_pending_tasks"], [])
        self.assertEqual(manager.get_pending_tasks(), [])


if __name__ == "__main__":
    unittest.main()
