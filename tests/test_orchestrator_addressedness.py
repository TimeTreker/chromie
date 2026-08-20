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

    def test_other_in_flight_turn_keeps_overlapping_request_engaged(self) -> None:
        class _InFlightTask:
            @staticmethod
            def done() -> bool:
                return False

        assistant = self._assistant()
        assistant.active_turn_tasks = {_InFlightTask(): "sid-first"}

        context = assistant._interaction_engagement_context(
            {
                "history": [],
                "active_pending_tasks": [],
                "active_task_contexts": [],
            },
            session_id="sid-second",
        )

        self.assertTrue(context["active"])
        self.assertEqual(context["evidence"], "in_flight_turn")

    def test_gateway_suppressed_ambient_turn_does_not_open_engagement_window(self) -> None:
        context = self._assistant()._interaction_engagement_context(
            {
                "history": [
                    {
                        "role": "user",
                        "text": "他们之后再把传感器结果合并。",
                        "metadata": {
                            "user_turn_envelope": {
                                "admission": "suppress",
                                "attention": {"speech_act": "ambient_report"},
                            }
                        },
                        "ts_ms": time.time() * 1000.0 - 1000.0,
                    }
                ],
                "active_pending_tasks": [],
                "active_task_contexts": [],
            }
        )

        self.assertFalse(context["active"])
        self.assertEqual(context["evidence"], "none")

    def test_admitted_user_turn_opens_engagement_window_from_explicit_evidence(self) -> None:
        context = self._assistant()._interaction_engagement_context(
            {
                "history": [
                    {
                        "role": "user",
                        "text": "你帮我看一下天气。",
                        "metadata": {
                            "accepted_dialogue_evidence": True,
                            "user_turn_envelope": {"admission": "admit"},
                        },
                        "ts_ms": time.time() * 1000.0 - 1000.0,
                    }
                ],
                "active_pending_tasks": [],
                "active_task_contexts": [],
            }
        )

        self.assertTrue(context["active"])
        self.assertEqual(context["evidence"], "recent_exchange")


if __name__ == "__main__":
    unittest.main()
