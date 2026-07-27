from __future__ import annotations

import unittest

from orchestrator.runtime.conversation_state import ConversationStateManager


class ConversationToolEvidenceTests(unittest.TestCase):
    def test_schema_validated_tool_evidence_is_retained_for_followups(self) -> None:
        manager = ConversationStateManager(base_conversation_id="tool-followup")
        manager.record_agent_result(
            "sid-weather",
            {
                "metadata": {
                    "user_request": "Is Beijing hot today?",
                    "canonical_plan_id": "plan-weather",
                    "source_goal_ids": ["goal-weather"],
                    "execution_outcome_bundle": {
                        "goal_outcomes": [
                            {"goal_id": "goal-weather", "status": "completed"}
                        ],
                        "evidence": [
                            {
                                "evidence_id": "evidence-weather",
                                "skill_id": "chromie.weather.lookup",
                                "status": "completed",
                                "observation": {
                                    "status": "available",
                                    "schema_validated": True,
                                    "data": {
                                        "location": "Beijing",
                                        "apparent_temperature_c": 35.0,
                                    },
                                },
                            }
                        ],
                    },
                },
                "speech": [{"text": "It feels hot today."}],
            },
        )

        snapshot = manager.snapshot()
        evidence = snapshot["recent_tool_evidence"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["tool_id"], "chromie.weather.lookup")
        self.assertEqual(evidence[0]["data"]["apparent_temperature_c"], 35.0)
        self.assertEqual(
            snapshot["session_memory"]["recent_tool_evidence"][0]["evidence_id"],
            "evidence-weather",
        )

    def test_unvalidated_tool_payload_is_not_retained(self) -> None:
        manager = ConversationStateManager(base_conversation_id="tool-reject")
        manager.record_agent_result(
            "sid-weather",
            {
                "metadata": {
                    "execution_outcome_bundle": {
                        "evidence": [
                            {
                                "evidence_id": "untrusted",
                                "skill_id": "chromie.weather.lookup",
                                "status": "completed",
                                "observation": {
                                    "status": "available",
                                    "schema_validated": False,
                                    "data": {"location": "Beijing"},
                                },
                            }
                        ]
                    }
                }
            },
        )
        self.assertEqual(manager.snapshot()["recent_tool_evidence"], [])

    def test_reset_clears_recent_tool_evidence(self) -> None:
        manager = ConversationStateManager(base_conversation_id="tool-reset")
        manager._recent_tool_evidence.append({"evidence_id": "old"})
        manager.start_new_conversation(reason="explicit_reset")
        self.assertEqual(manager.recent_tool_evidence(), [])


if __name__ == "__main__":
    unittest.main()
