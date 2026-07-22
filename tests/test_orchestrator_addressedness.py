from __future__ import annotations

import time
import unittest

from orchestrator.orchestrator import VoiceAssistant


class OrchestratorAddressednessTests(unittest.TestCase):
    def _assistant(self) -> VoiceAssistant:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.addressedness_gate_enabled = True
        assistant.addressedness_engagement_timeout_s = 45.0
        return assistant

    def test_empty_conversation_is_not_engaged(self) -> None:
        context = self._assistant()._interaction_engagement_context(
            {
                "history": [],
                "active_pending_tasks": [],
                "active_task_contexts": [],
            }
        )

        self.assertFalse(context["active"])
        self.assertEqual(context["evidence"], "none")

    def test_recent_exchange_keeps_natural_followups_engaged(self) -> None:
        context = self._assistant()._interaction_engagement_context(
            {
                "history": [
                    {
                        "role": "assistant",
                        "text": "好的。",
                        "ts_ms": time.time() * 1000.0 - 1000.0,
                    }
                ],
                "active_pending_tasks": [],
                "active_task_contexts": [],
            }
        )

        self.assertTrue(context["active"])
        self.assertEqual(context["evidence"], "recent_exchange")

    def test_active_task_keeps_engagement_without_recent_speech(self) -> None:
        context = self._assistant()._interaction_engagement_context(
            {
                "history": [],
                "active_pending_tasks": [{"id": "pending"}],
                "active_task_contexts": [],
            }
        )

        self.assertTrue(context["active"])
        self.assertEqual(context["evidence"], "active_task")

    def test_ignored_ambient_turn_does_not_open_engagement_window(self) -> None:
        context = self._assistant()._interaction_engagement_context(
            {
                "history": [
                    {
                        "role": "user",
                        "text": "他们之后再把传感器结果合并。",
                        "route": "ignore",
                        "ts_ms": time.time() * 1000.0 - 1000.0,
                    }
                ],
                "active_pending_tasks": [],
                "active_task_contexts": [],
            }
        )

        self.assertFalse(context["active"])
        self.assertEqual(context["evidence"], "none")


if __name__ == "__main__":
    unittest.main()
