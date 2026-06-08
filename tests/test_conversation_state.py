from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.runtime.conversation_state import ConversationStateManager


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
