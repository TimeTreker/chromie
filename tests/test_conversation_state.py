from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
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
                "ORCH_ENABLE_TASK_CONTEXT_STORE": "0",
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

    def test_agent_result_extracted_memory_update_reaches_session_memory(self) -> None:
        manager = ConversationStateManager()

        manager.record_agent_result(
            "s1",
            {
                "memory_updates": [
                    {
                        "type": "extracted_memory",
                        "key": "preference",
                        "value": {
                            "scope": "session",
                            "kind": "preference",
                            "text": "User prefers jasmine tea without sugar.",
                            "persistence_policy": "ephemeral",
                        },
                        "confidence": 0.9,
                    }
                ]
            },
        )

        memory = manager.snapshot()["session_memory"]

        self.assertIn("User prefers jasmine tea without sugar.", memory["memory_summary"])
        self.assertEqual(memory["extracted_memory"][-1]["kind"], "preference")

    def test_keyed_extracted_memory_update_revises_prior_entry(self) -> None:
        manager = ConversationStateManager()

        manager.record_agent_result(
            "s1",
            {
                "memory_updates": [
                    {
                        "type": "extracted_memory",
                        "value": {
                            "scope": "session",
                            "kind": "preference",
                            "key": "tea_preference",
                            "text": "User prefers jasmine tea without sugar.",
                        },
                    }
                ]
            },
        )
        manager.record_agent_result(
            "s2",
            {
                "memory_updates": [
                    {
                        "type": "extracted_memory",
                        "value": {
                            "scope": "session",
                            "kind": "preference",
                            "key": "tea_preference",
                            "text": "User corrected tea preference to green tea without sugar.",
                        },
                    }
                ]
            },
        )

        memory = manager.snapshot()["session_memory"]

        self.assertIn("green tea without sugar", memory["memory_summary"])
        self.assertNotIn("jasmine tea without sugar", memory["memory_summary"])
        self.assertEqual(len(memory["extracted_memory"]), 1)

    def test_hard_idle_boundary_clears_extracted_memory(self) -> None:
        manager = ConversationStateManager(
            base_conversation_id="session",
            soft_idle_timeout_sec=5,
            hard_idle_timeout_sec=5,
        )
        manager.record_agent_result(
            "s1",
            {
                "memory_updates": [
                    {
                        "type": "extracted_memory",
                        "value": {
                            "scope": "session",
                            "kind": "note",
                            "text": "User wants this only in the current conversation.",
                        },
                    }
                ]
            },
        )
        manager.last_activity_ms -= 6_000

        boundary = manager.prepare_for_user_text("tell me the weather", "s2")

        self.assertTrue(boundary["started_new"])
        self.assertEqual(manager.snapshot()["session_memory"]["memory_summary"], "None")
        self.assertEqual(manager.snapshot()["extracted_memory"], [])

    def test_agent_speech_alone_does_not_create_runtime_outcome_memory(self) -> None:
        manager = ConversationStateManager()

        manager.record_agent_result(
            "s1",
            InteractionResponse(speech=[{"text": "Done, I blinked."}]),
        )

        self.assertNotIn("Runtime confirmed", manager.snapshot()["session_memory"]["memory_summary"])

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

    def test_extracted_memory_uses_task_patch_not_raw_transcript_replay(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        raw_turn = (
            "I am saying this in a messy way, but please do not replay this raw "
            "sentence in future prompts."
        )

        manager.record_user_turn(
            "s1",
            raw_turn,
            route="deep_thought",
            intent="memory_architecture_design",
            metadata={
                "task_relation": "new_task",
                "task_context_patch": {
                    "task_type": "design",
                    "goal": "Design extracted prompt memory for Chromie",
                    "important_claims": [
                        "User wants refined memory extracted from chat history."
                    ],
                    "constraints": {
                        "prompt_context": "do not inject raw original chat history"
                    },
                },
            },
        )

        memory = manager.snapshot()["session_memory"]
        summary = memory["memory_summary"]

        self.assertIn("Current task: Design extracted prompt memory for Chromie", summary)
        self.assertIn("User wants refined memory extracted from chat history.", summary)
        self.assertIn("Constraint: prompt_context=do not inject raw original chat history", summary)
        self.assertNotIn("messy way", summary)
        self.assertNotIn("replay this raw sentence", str(memory["extracted_memory"]))

    def test_extracted_memory_clears_on_reset(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        manager.record_user_turn(
            "s1",
            "Please remember this only for the current session.",
            route="memory",
            intent="remember_session_note",
            metadata={
                "extracted_memory": [
                    {
                        "scope": "session",
                        "kind": "preference",
                        "text": "User wants this note kept only for the current session.",
                    }
                ]
            },
        )

        self.assertIn("current session", manager.snapshot()["session_memory"]["memory_summary"])

        manager.prepare_for_user_text("new session", "s2")

        self.assertEqual(manager.snapshot()["session_memory"]["memory_summary"], "None")
        self.assertEqual(manager.snapshot()["extracted_memory"], [])

    def test_task_context_keeps_meaningful_claim_across_sessions(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        manager.record_user_turn(
            "s1",
            "I think the moon is round. Do you think so?",
            route="chat",
            intent="general_conversation",
            metadata={
                "task_relation": "new_task",
                "task_context_patch": {
                    "task_type": "conversation",
                    "goal": "Discuss whether the Moon is round",
                    "important_claims": ["The user thinks the Moon is round."],
                    "entities": ["Moon"],
                },
            },
        )
        task_id = manager.snapshot()["current_task_context"]["task_id"]
        manager.record_assistant_turn("s1", "The moon is round.")

        manager.record_user_turn(
            "s2",
            "or",
            route="deep_thought",
            intent="deep_thought_low_confidence",
        )
        manager.record_user_turn(
            "s3",
            "Do you agree with me?",
            route="chat",
            intent="general_conversation",
            metadata={
                "task_relation": "continue_task",
                "target_task_id": task_id,
            },
        )

        context = manager.snapshot()["current_task_context"]
        self.assertEqual(context["task_id"], task_id)
        self.assertIn("The user thinks the Moon is round.", context["important_claims"])
        self.assertEqual(context["last_assistant_response"], "The moon is round.")
        self.assertIn("s3", context["related_sids"])
        self.assertEqual(
            manager.snapshot()["session_memory"]["current_task_context"]["task_id"],
            task_id,
        )

    def test_task_context_store_restores_unfinished_context_as_recoverable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "task_contexts.json"
            manager = ConversationStateManager(
                base_conversation_id="session",
                task_store_enabled=True,
                task_store_path=store_path,
            )
            manager.record_user_turn(
                "s1",
                "Walk forward when I confirm.",
                route="robot_action",
                intent="capability:soridormi.walk_velocity",
                metadata={
                    "task_relation": "new_task",
                    "task_context_patch": {
                        "task_type": "robot_action",
                        "goal": "Walk forward after confirmation",
                    },
                },
            )
            manager.record_pending_task(
                sid="s1",
                task_type="robot_action",
                status="awaiting_confirmation",
                summary="soridormi.walk_velocity",
                metadata={"request_ids": ["skill-1"], "remaining_request_ids": ["skill-1"]},
            )
            task_id = manager.snapshot()["current_task_context"]["task_id"]

            restored = ConversationStateManager(
                base_conversation_id="session",
                task_store_enabled=True,
                task_store_path=store_path,
            )
            restored_context = restored.snapshot()["current_task_context"]

            self.assertEqual(restored_context["task_id"], task_id)
            self.assertEqual(restored_context["status"], "recoverable")
            self.assertTrue(restored_context["metadata"]["restored_from_task_store"])
            self.assertEqual(
                restored_context["metadata"]["restored_original_status"],
                "awaiting_confirmation",
            )

            manager.update_pending_task_status_for_request_id(request_id="skill-1", status="completed")
            restored_after_done = ConversationStateManager(
                base_conversation_id="session",
                task_store_enabled=True,
                task_store_path=store_path,
            )

            self.assertIsNone(restored_after_done.snapshot()["current_task_context"])

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
        self.assertIn(
            "Runtime confirmed task completed: soridormi.nod_yes",
            manager.snapshot()["session_memory"]["memory_summary"],
        )


if __name__ == "__main__":
    unittest.main()
