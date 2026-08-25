from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.discourse import (
    DiscourseReferent,
    DiscourseReferentUpdate,
    ResolvedDiscourseReference,
)
from shared.chromie_contracts.execution_outcome import (
    ClaimQualificationPolicy,
    ExecutionOutcomeBundle,
    claim_qualification_policy_sha256,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.interaction import InteractionResponse


class ConversationStateTests(unittest.TestCase):
    def test_admitted_dialogue_is_visible_before_semantic_state_without_duplication(self) -> None:
        manager = ConversationStateManager(base_conversation_id="dialogue")

        manager.record_accepted_user_turn(
            "s1",
            "上海今晚是不是有大暴雨？",
            metadata={"source": "cognitive_gateway_admitted_dialogue"},
        )

        history = manager.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["text"], "上海今晚是不是有大暴雨？")
        self.assertNotIn("route", history[0])
        self.assertNotIn("intent", history[0])
        self.assertEqual(manager.active_goal_snapshots(), [])
        self.assertEqual(manager.active_task_snapshots(), [])

        manager.record_user_turn('s1', '上海今晚是不是有大暴雨？', metadata={'source': 'goal_driven_cognitive_runtime'})

        history = manager.get_history()
        self.assertEqual(len(history), 1)
        self.assertNotIn("route", history[0])
        self.assertNotIn("intent", history[0])
        self.assertTrue(history[0]["metadata"]["accepted_dialogue_evidence"])
        self.assertEqual(history[0]["metadata"]["source"], "goal_driven_cognitive_runtime")

    def test_natural_language_reset_is_not_classified_by_host(self) -> None:
        manager = ConversationStateManager(base_conversation_id="test")
        manager.record_user_turn('s1', 'check the weather')
        original_id = manager.conversation_id

        boundary = manager.prepare_for_user_text("new topic", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(manager.conversation_id, original_id)
        self.assertNotEqual(manager.get_history(), [])

    def test_scoped_referents_coexist_and_correction_only_backgrounds_target(self) -> None:
        manager = ConversationStateManager(base_conversation_id="discourse")

        room = DiscourseReferent(
            referent_id="ref-room",
            entity_type="physical_location",
            canonical_value="客厅",
            scope_kind="goal",
            scope_ids=["goal-navigation"],
            status="foreground",
            confidence=1.0,
            source_turn_id="turn-room",
            source_goal_ids=["goal-navigation"],
        )
        chongqing = DiscourseReferent(
            referent_id="ref-chongqing",
            entity_type="location",
            canonical_value="重庆",
            scope_kind="goal",
            scope_ids=["goal-weather-chongqing"],
            status="foreground",
            confidence=1.0,
            source_turn_id="turn-chongqing",
            source_goal_ids=["goal-weather-chongqing"],
        )
        for turn_id, referent in (
            ("turn-room", room),
            ("turn-chongqing", chongqing),
        ):
            results = manager.apply_goal_association_resolution(
                GoalAssociationResolution(
                    resolution_status="resolved",
                    turn_id=turn_id,
                    referent_updates=[
                        DiscourseReferentUpdate(
                            operation="introduce",
                            referent=referent,
                            confidence=1.0,
                        )
                    ],
                    confidence=1.0,
                ),
                sid=turn_id,
                user_text=referent.canonical_value,
                atomic=True,
            )
            self.assertTrue(all(item["applied"] for item in results))

        neixiang = DiscourseReferent(
            referent_id="ref-neixiang",
            entity_type="location",
            canonical_value="内乡",
            scope_kind="conversation",
            status="foreground",
            confidence=1.0,
            source_turn_id="turn-neixiang",
            supersedes_referent_ids=["ref-chongqing"],
        )
        results = manager.apply_goal_association_resolution(
            GoalAssociationResolution(
                resolution_status="resolved",
                turn_id="turn-neixiang",
                referent_updates=[
                    DiscourseReferentUpdate(
                        operation="correct",
                        referent=neixiang,
                        target_referent_ids=["ref-chongqing"],
                        confidence=1.0,
                    )
                ],
                confidence=1.0,
            ),
            sid="sid-neixiang",
            user_text="不是重庆，是内乡。",
            atomic=True,
        )
        self.assertTrue(all(item["applied"] for item in results))

        referents = {
            item["referent_id"]: item for item in manager.discourse_referents()
        }
        self.assertEqual(referents["ref-room"]["canonical_value"], "客厅")
        self.assertEqual(referents["ref-room"]["status"], "foreground")
        self.assertEqual(referents["ref-chongqing"]["status"], "background")
        self.assertEqual(referents["ref-neixiang"]["status"], "foreground")
        self.assertEqual(
            manager.discourse_focus(),
            ["ref-room", "ref-neixiang"],
        )

        focus_result = manager.apply_goal_association_resolution(
            GoalAssociationResolution(
                resolution_status="resolved",
                turn_id="turn-rain",
                resolved_references=[
                    ResolvedDiscourseReference(
                        surface_form="那边",
                        entity_type="location",
                        resolved_value="内乡",
                        source="discourse_referent",
                        referent_id="ref-neixiang",
                        confidence=1.0,
                    )
                ],
                referent_updates=[
                    DiscourseReferentUpdate(
                        operation="focus",
                        target_referent_ids=["ref-neixiang"],
                        confidence=1.0,
                    )
                ],
                confidence=1.0,
            ),
            sid="sid-rain",
            user_text="今天那边下雨了吗？",
            atomic=True,
        )
        self.assertTrue(all(item["applied"] for item in focus_result))
        self.assertEqual(manager.discourse_focus()[-1], "ref-neixiang")

    def test_atomic_unknown_referent_update_rolls_back_all_discourse_changes(self) -> None:
        manager = ConversationStateManager(base_conversation_id="discourse-atomic")
        neixiang = DiscourseReferent(
            referent_id="ref-neixiang",
            entity_type="location",
            canonical_value="内乡",
            status="foreground",
            confidence=1.0,
            source_turn_id="turn-neixiang",
        )
        results = manager.apply_goal_association_resolution(
            GoalAssociationResolution(
                resolution_status="resolved",
                turn_id="turn-neixiang",
                referent_updates=[
                    DiscourseReferentUpdate(
                        operation="correct",
                        referent=neixiang,
                        target_referent_ids=["missing-ref"],
                        confidence=1.0,
                    )
                ],
                confidence=1.0,
            ),
            sid="sid-neixiang",
            user_text="不是那里，是内乡。",
            atomic=True,
        )
        self.assertTrue(any(item.get("rolled_back") for item in results))
        self.assertEqual(manager.discourse_referents(), [])
        self.assertEqual(manager.discourse_focus(), [])

    def test_delivered_fast_complete_response_closes_no_work_speech_goal(self) -> None:
        manager = ConversationStateManager(base_conversation_id="fast-speech")
        manager.apply_semantic_task_operations_atomically(
            [
                {
                    "operation_id": "create-greeting",
                    "operation": "create",
                    "goal": {
                        "goal_id": "goal-greeting",
                        "description": "Greet the user warmly.",
                        "source_text": "你好。",
                        "source_responsibility_refs": ["r1"],
                        "metadata": {
                            "output_mode": "speech",
                        },
                    },
                }
            ],
            sid="sid-greeting",
            user_text="你好。",
        )
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-greeting"],
        )

        results = manager.reconcile_fast_communicative_goal_completion(
            "sid-greeting",
            ["goal-greeting"],
            metadata={
                "delivery_role": "complete_response",
                "fast_activity_id": "fast-greeting",
                "interaction_id": "interaction-greeting",
            },
        )

        self.assertEqual(results[0]["responsibility_status"], "satisfied")
        self.assertTrue(results[0]["changed"])
        self.assertEqual(manager.active_goal_snapshots(), [])
        recent = manager.recent_goal_snapshots()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["goal_id"], "goal-greeting")
        self.assertEqual(recent[0]["responsibility_status"], "satisfied")
        self.assertEqual(recent[0]["work_status"], "done")

    def test_fast_communicative_delivery_cannot_close_work_requiring_goal(self) -> None:
        manager = ConversationStateManager(base_conversation_id="fast-communicative-work")
        manager.apply_semantic_task_operations_atomically(
            [
                {
                    "operation_id": "create-weather",
                    "operation": "create",
                    "goal": {
                        "goal_id": "goal-weather",
                        "description": "Check tonight's weather.",
                        "source_text": "今晚会下雨吗？",
                        "source_responsibility_refs": ["r1"],
                        "metadata": {
                            "output_mode": "information",
                        },
                    },
                }
            ],
            sid="sid-weather",
            user_text="今晚会下雨吗？",
        )

        results = manager.reconcile_fast_communicative_goal_completion(
            "sid-weather",
            ["goal-weather"],
            metadata={
                "delivery_role": "complete_response",
                "fast_activity_id": "fast-weather",
            },
        )

        self.assertEqual(
            results[0]["reason"],
            "goal_requires_nontrivial_completion_evidence",
        )
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-weather"],
        )

    def test_ambiguous_cancellation_does_not_clear_all_goal_context(self) -> None:
        manager = ConversationStateManager(base_conversation_id="test")
        manager.apply_semantic_task_operations_atomically(
            [
                {
                    "operation_id": "create-coffee",
                    "operation": "create",
                    "goal": {
                        "goal_id": "goal-coffee",
                        "description": "Prepare coffee.",
                        "source_text": "准备咖啡。",
                    },
                },
                {
                    "operation_id": "create-weather",
                    "operation": "create",
                    "goal": {
                        "goal_id": "goal-weather",
                        "description": "Check weather.",
                        "source_text": "查天气。",
                    },
                },
            ],
            sid="s1",
            user_text="准备咖啡，也查天气。",
        )
        original_id = manager.conversation_id

        boundary = manager.prepare_for_user_text("算了，刚才那个不用了。", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(manager.conversation_id, original_id)
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-coffee", "goal-weather"],
        )

    def test_soft_idle_does_not_semantically_classify_followup_text(self) -> None:
        manager = ConversationStateManager(soft_idle_timeout_sec=10, hard_idle_timeout_sec=100)
        manager.record_user_turn("s1", "check the weather")
        manager.last_activity_ms -= 20_000

        boundary = manager.prepare_for_user_text("what about it?", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(boundary["reason"], "kept_default")

    def test_user_turn_metadata_does_not_create_host_task_association(self) -> None:
        manager = ConversationStateManager()

        manager.record_user_turn(
            "s1",
            "Please continue that task.",
            metadata={"task_relation": "continue_task", "task_context_patch": {"goal": "legacy"}},
        )

        self.assertEqual(manager.active_goal_snapshots(), [])
        self.assertEqual(manager.active_task_snapshots(), [])

    def test_pending_task_keeps_context_for_new_topic_like_text(self) -> None:
        manager = ConversationStateManager(soft_idle_timeout_sec=10, hard_idle_timeout_sec=100)
        manager.record_user_turn("s1", "check the weather")
        manager.record_pending_task(sid="s1", task_type="weather", summary="weather lookup")
        manager.last_activity_ms -= 20_000

        boundary = manager.prepare_for_user_text("tell me another thing", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(boundary["reason"], "active_pending_task")

    def test_waiting_goal_keeps_context_after_soft_idle_without_pending_request(self) -> None:
        manager = ConversationStateManager(
            soft_idle_timeout_sec=10,
            hard_idle_timeout_sec=100,
        )
        manager.apply_semantic_task_operations_atomically(
            [
                {
                    "operation_id": "create-waiting-goal",
                    "operation": "create",
                    "goal": {
                        "goal_id": "goal-walk",
                        "description": "Walk forward.",
                        "source_text": "往前走。",
                    },
                    "status_update": "waiting_for_user",
                    "commitment_state": "waiting_for_user",
                    "information_gaps": [
                        {
                            "gap_id": "duration",
                            "description": "Walking duration.",
                            "blocking": True,
                            "required_for": ["goal-walk"],
                            "preferred_resolution": "ask_user",
                        }
                    ],
                }
            ],
            sid="s1",
            user_text="往前走。",
        )
        manager.last_activity_ms -= 20_000

        boundary = manager.prepare_for_user_text("tell me another thing", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(boundary["reason"], "active_goal")
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-walk"],
        )

    def test_active_goal_survives_hard_idle_conversation_boundary(self) -> None:
        manager = ConversationStateManager(
            soft_idle_timeout_sec=5,
            hard_idle_timeout_sec=5,
        )
        manager.apply_semantic_task_operations_atomically(
            [
                {
                    "operation_id": "create-long-waiting-goal",
                    "operation": "create",
                    "goal": {
                        "goal_id": "goal-reminder",
                        "description": "Create a reminder after the user supplies a time.",
                        "source_text": "提醒我。",
                    },
                    "status_update": "waiting_for_user",
                    "commitment_state": "waiting_for_user",
                }
            ],
            sid="s1",
            user_text="提醒我。",
        )
        original_id = manager.conversation_id
        manager.last_activity_ms -= 6_000

        boundary = manager.prepare_for_user_text("明天下午三点。", "s2")

        self.assertFalse(boundary["started_new"])
        self.assertEqual(boundary["reason"], "active_goal")
        self.assertEqual(manager.conversation_id, original_id)
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-reminder"],
        )

    def test_history_respects_turn_and_character_limits(self) -> None:
        manager = ConversationStateManager(max_turns=3, max_context_chars=200)
        for index in range(5):
            manager.record_user_turn(f"s{index}", f"turn {index}")

        history = manager.get_history()

        self.assertEqual(len(history), 3)
        self.assertEqual([turn["text"] for turn in history], ["turn 2", "turn 3", "turn 4"])

    def test_interaction_response_records_speech_and_named_skill(self) -> None:
        manager = ConversationStateManager()

        manager.record_interaction_response(
            "s1",
            InteractionResponse(
                speech=[{"text": "Hello."}],
                capabilities=[{"capability_id": "soridormi.nod_yes"}],
            ),
        )

        self.assertEqual(manager.get_history()[-1]["text"], "Hello.")
        self.assertEqual(
            manager.snapshot()["active_pending_tasks"][-1]["summary"],
            "soridormi.nod_yes",
        )

    def test_reused_fast_communicative_delivery_is_not_recorded_as_second_assistant_turn(self) -> None:
        manager = ConversationStateManager()
        manager.record_assistant_turn(
            "s1",
            "好，我这就往前走十秒。",
            metadata={"source": "fast_planner_communicative_delivery"},
        )

        manager.record_interaction_response(
            "s1",
            InteractionResponse(
                speech=[
                    {
                        "text": "好，我这就往前走十秒。",
                        "metadata": {
                            "reuse_current_turn_speech": True,
                            "reused_speech_event_id": "speech_event_walk",
                        },
                    }
                ],
                capabilities=[{"capability_id": "soridormi.walk_forward"}],
            ),
        )

        self.assertEqual(
            [turn["text"] for turn in manager.get_history()],
            ["好，我这就往前走十秒。"],
        )

    def test_native_interaction_metadata_records_memory_update(self) -> None:
        manager = ConversationStateManager()

        manager.record_interaction_response(
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

        manager.record_interaction_response(
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

        manager.record_interaction_response(
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
        manager.record_interaction_response(
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
        manager.record_interaction_response(
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

        manager.record_interaction_response(
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

    def test_session_memory_summarizes_active_task_and_typed_boundary_clears_it(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        manager.record_user_turn('s1', 'walk forward')
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

        boundary = manager.start_new_conversation(reason="typed_reset", sid="s2")

        self.assertTrue(boundary["started_new"])
        self.assertIsNone(manager.snapshot()["session_memory"]["current_task"])
        self.assertEqual(manager.get_history(), [])

    def test_extracted_memory_uses_task_patch_not_raw_transcript_replay(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        raw_turn = (
            "I am saying this in a messy way, but please do not replay this raw "
            "sentence in future prompts."
        )

        manager.record_user_turn('s1', raw_turn, metadata={'task_relation': 'new_task', 'task_context_patch': {'task_type': 'design', 'goal': 'Design extracted prompt memory for Chromie', 'important_claims': ['User wants refined memory extracted from chat history.'], 'constraints': {'prompt_context': 'do not inject raw original chat history'}}})

        memory = manager.snapshot()["session_memory"]
        summary = memory["memory_summary"]

        self.assertIn("Current task: Design extracted prompt memory for Chromie", summary)
        self.assertIn("User wants refined memory extracted from chat history.", summary)
        self.assertIn("Constraint: prompt_context=do not inject raw original chat history", summary)
        self.assertNotIn("messy way", summary)
        self.assertNotIn("replay this raw sentence", str(memory["extracted_memory"]))

    def test_extracted_memory_clears_on_typed_boundary(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        manager.record_user_turn('s1', 'Please remember this only for the current session.', metadata={'extracted_memory': [{'scope': 'session', 'kind': 'preference', 'text': 'User wants this note kept only for the current session.'}]})

        self.assertIn("current session", manager.snapshot()["session_memory"]["memory_summary"])

        manager.start_new_conversation(reason="typed_reset", sid="s2")

        self.assertEqual(manager.snapshot()["session_memory"]["memory_summary"], "None")
        self.assertEqual(manager.snapshot()["extracted_memory"], [])

    def test_task_context_keeps_meaningful_claim_across_sessions(self) -> None:
        manager = ConversationStateManager(base_conversation_id="session")
        manager.apply_semantic_task_operations_atomically(
            [{
                "operation_id": "create-moon-discussion",
                "operation": "create",
                "goal": {
                    "description": "Discuss whether the Moon is round",
                    "source_text": "I think the moon is round. Do you think so?",
                    "metadata": {"important_claims": ["The user thinks the Moon is round."]},
                },
                "metadata": {"task_type": "conversation"},
            }],
            sid="s1",
            user_text="I think the moon is round. Do you think so?",
            source="test_goal_association",
        )
        task_id = manager.snapshot()["current_task_context"]["task_id"]
        manager._task_contexts[-1]["important_claims"] = ["The user thinks the Moon is round."]
        manager.record_assistant_turn("s1", "The moon is round.")

        manager.record_user_turn('s2', 'or')
        manager.apply_semantic_task_operations_atomically(
            [{
                "operation_id": "continue-moon-discussion",
                "operation": "modify",
                "target_task_ids": [task_id],
                "goal_update": {"source_text": "Do you agree with me?"},
            }],
            sid="s3",
            user_text="Do you agree with me?",
            source="test_goal_association",
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
            manager.apply_semantic_task_operations_atomically(
                [{
                    "operation_id": "create-walk-confirm",
                    "operation": "create",
                    "goal": {
                        "description": "Walk forward after confirmation",
                        "source_text": "Walk forward when I confirm.",
                    },
                    "metadata": {"task_type": "robot_action"},
                }],
                sid="s1",
                user_text="Walk forward when I confirm.",
                source="test_goal_association",
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

            restored_done_context = restored_after_done.snapshot()["current_task_context"]
            self.assertIsNotNone(restored_done_context)
            self.assertEqual(restored_done_context["status"], "recoverable")
            self.assertEqual(
                restored_after_done.active_goal_snapshots()[0]["responsibility_status"],
                "open",
            )

    def test_completed_skill_request_closes_active_task_and_can_be_pruned(self) -> None:
        manager = ConversationStateManager(completed_task_retention_sec=0)
        manager.record_interaction_response(
            "s1",
            InteractionResponse(
                capabilities=[{"request_id": "skill-1", "capability_id": "soridormi.nod_yes"}],
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


class GoalScopedLifecycleTests(unittest.TestCase):
    @staticmethod
    def _create_goals(
        manager: ConversationStateManager,
        *goal_ids: str,
    ) -> list[dict]:
        return manager.apply_goal_association_resolution({'resolution_status': 'resolved', 'turn_id': 'turn-create-' + '-'.join(goal_ids), 'new_goals': [{'goal_id': goal_id, 'description': f'Complete {goal_id}.', 'source_text': f'Complete {goal_id}.'} for goal_id in goal_ids], 'confidence': 0.95, 'reason_summary': 'Independent user goals.'}, sid='sid-create', user_text='Complete the requested goals.', atomic=True)

    @staticmethod
    def _canonical_plan(
        disposition: str,
        outcomes: list[dict],
    ) -> dict:
        return {
            "plan_id": "plan-lifecycle",
            "planner_tier": "fast",
            "disposition": disposition,
            "coverage": "complete" if disposition != "clarify" else "uncertain",
            "confidence": 0.95,
            "goal_ids": [item["goal_id"] for item in outcomes],
            "steps": [],
            "goal_outcomes": outcomes,
        }

    def test_semantic_goal_ids_bind_results_to_their_distinct_task_contexts(self) -> None:
        manager = ConversationStateManager(base_conversation_id="goal-lifecycle")
        created = self._create_goals(manager, "goal-walk", "goal-blink")

        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-walk", "goal-blink"],
        )
        self.assertNotEqual(created[0]["task_id"], "goal-walk")
        self.assertNotEqual(created[1]["task_id"], "goal-blink")

        response = InteractionResponse(
            capabilities=[
                {
                    "request_id": "skill-walk",
                    "capability_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "skill-blink",
                    "capability_id": "soridormi.blink_eyes",
                    "metadata": {"source_goal_ids": ["goal-blink"]},
                },
            ],
            metadata={
                "planning_result": "composed_plan",
                "canonical_plan": self._canonical_plan(
                    "execute",
                    [
                        {
                            "goal_id": "goal-walk",
                            "disposition": "execute",
                            "coverage": "complete",
                            "step_ids": ["walk"],
                        },
                        {
                            "goal_id": "goal-blink",
                            "disposition": "execute",
                            "coverage": "complete",
                            "step_ids": ["blink"],
                        },
                    ],
                ),
            },
        )

        manager.record_interaction_response("sid-execute", response)
        self.assertEqual(
            [item["work_status"] for item in manager.active_goal_snapshots()],
            ["scheduled", "scheduled"],
        )

        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="skill-walk",
                status="completed",
            )
        )
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-walk", "goal-blink"],
        )

        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="skill-blink",
                status="completed",
            )
        )
        self.assertEqual(
            [item["responsibility_status"] for item in manager.active_goal_snapshots()],
            ["open", "open"],
        )
        self.assertEqual(manager.recent_goal_snapshots(), [])
        self.assertEqual(
            [
                item["goal_id"]
                for item in manager.goal_association_candidate_snapshots()
            ],
            ["goal-walk", "goal-blink"],
        )

    def test_planning_only_response_retains_semantics_without_runtime_work(self) -> None:
        manager = ConversationStateManager(base_conversation_id="planning-only")
        self._create_goals(manager, "goal-walk")
        response = InteractionResponse(
            interaction_id="interaction-preview",
            capabilities=[
                {
                    "request_id": "walk-preview",
                    "capability_id": "soridormi.walk_forward",
                    "args": {"duration_s": 10},
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                }
            ],
            speech=[
                {
                    "id": "speech-preview",
                    "text": "Okay, I'll walk forward.",
                    "metadata": {"covers_goal_ids": ["goal-walk"]},
                }
            ],
            metadata={
                "planning_result": "composed_plan",
                "canonical_plan": self._canonical_plan(
                    "execute",
                    [
                        {
                            "goal_id": "goal-walk",
                            "disposition": "execute",
                            "coverage": "complete",
                            "step_ids": ["walk-preview"],
                        }
                    ],
                ),
            },
        )

        manager.record_interaction_response(
            "sid-preview",
            response,
            bind_planned_execution=False,
        )

        snapshot = manager.active_goal_snapshots()[0]
        self.assertEqual(snapshot["goal_id"], "goal-walk")
        self.assertEqual(
            snapshot["metadata"]["execution_binding"]["remaining_request_ids"],
            [],
        )
        self.assertEqual(manager.snapshot()["pending_tasks"], [])
        self.assertEqual(manager.get_history()[-1]["text"], "Okay, I'll walk forward.")

    def test_respond_goal_waits_for_scoped_speech_runtime_result(self) -> None:
        manager = ConversationStateManager(base_conversation_id="respond-lifecycle")
        self._create_goals(manager, "goal-answer")
        response = InteractionResponse(
            speech=[
                {
                    "id": "speech-answer",
                    "text": "Here is the answer.",
                    "metadata": {"covers_goal_ids": ["goal-answer"]},
                }
            ],
            metadata={
                "planning_result": "respond",
                "canonical_plan": self._canonical_plan(
                    "respond",
                    [
                        {
                            "goal_id": "goal-answer",
                            "disposition": "respond",
                            "coverage": "complete",
                            "step_ids": [],
                            "response_text": "Here is the answer.",
                        }
                    ],
                ),
            },
        )

        manager.record_interaction_response("sid-answer", response)

        active = manager.active_goal_snapshots()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["goal_id"], "goal-answer")
        self.assertEqual(active[0]["work_status"], "scheduled")
        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="speech-answer",
                status="completed",
            )
        )
        self.assertEqual(manager.active_goal_snapshots(), [])

    def test_planless_direct_response_goal_waits_for_scoped_speaking_evidence(self) -> None:
        manager = ConversationStateManager(base_conversation_id="native-respond-lifecycle")
        self._create_goals(manager, "goal-native-answer")
        response = InteractionResponse(
            speech=[
                {
                    "id": "speech-native-answer",
                    "text": "I'm Chromie!",
                    "metadata": {
                        "covers_goal_ids": ["goal-native-answer"],
                        "source_goal_ids": ["goal-native-answer"],
                    },
                }
            ],
            metadata={
                "planning_result": "direct_response",
                "planless_direct_response": True,
                "goal_ids": ["goal-native-answer"],
            },
        )

        manager.record_interaction_response("sid-native-answer", response)

        active = manager.active_goal_snapshots()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["goal_id"], "goal-native-answer")
        self.assertEqual(active[0]["work_status"], "scheduled")
        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="speech-native-answer",
                status="completed",
            )
        )
        self.assertEqual(manager.active_goal_snapshots(), [])

    def test_clarify_goal_remains_active_after_clarification_speech(self) -> None:
        manager = ConversationStateManager(base_conversation_id="clarify-lifecycle")
        self._create_goals(manager, "goal-clarify")
        response = InteractionResponse(
            status="clarify",
            speech=[
                {
                    "id": "speech-question",
                    "text": "Which target do you mean?",
                    "metadata": {"covers_goal_ids": ["goal-clarify"]},
                }
            ],
            metadata={
                "planning_result": "clarify",
                "canonical_plan": self._canonical_plan(
                    "clarify",
                    [
                        {
                            "goal_id": "goal-clarify",
                            "disposition": "clarify",
                            "coverage": "uncertain",
                            "step_ids": [],
                            "unresolved": ["target"],
                            "response_text": "Which target do you mean?",
                        }
                    ],
                ),
            },
        )

        manager.record_interaction_response("sid-clarify", response)

        active = manager.active_goal_snapshots()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["work_status"], "waiting_for_user")
        self.assertEqual(active[0]["responsibility_status"], "open")
        self.assertFalse(
            manager.update_pending_task_status_for_request_id(
                request_id="speech-question",
                status="completed",
            )
        )
        self.assertEqual(
            manager.active_goal_snapshots()[0]["work_status"],
            "waiting_for_user",
        )

    def test_noncompleted_goal_requests_reach_terminal_lifecycle_states(self) -> None:
        expected = {
            "cancelled": "cancelled",
            "failed": "failed",
            "timed_out": "timed_out",
            "refused": "refused",
        }
        for runtime_status, goal_status in expected.items():
            with self.subTest(runtime_status=runtime_status):
                manager = ConversationStateManager(
                    base_conversation_id=f"terminal-{runtime_status}"
                )
                self._create_goals(manager, "goal-action")
                manager.record_interaction_response(
                    "sid-action",
                    InteractionResponse(
                        capabilities=[
                            {
                                "request_id": "skill-action",
                                "capability_id": "soridormi.blink_eyes",
                                "metadata": {
                                    "source_goal_ids": ["goal-action"]
                                },
                            }
                        ],
                        metadata={
                            "planning_result": "composed_plan",
                            "canonical_plan": self._canonical_plan(
                                "execute",
                                [
                                    {
                                        "goal_id": "goal-action",
                                        "disposition": "execute",
                                        "coverage": "complete",
                                        "step_ids": ["action"],
                                    }
                                ],
                            ),
                        },
                    ),
                )

                self.assertTrue(
                    manager.update_pending_task_status_for_request_id(
                        request_id="skill-action",
                        status=runtime_status,
                    )
                )
                active = manager.active_goal_snapshots()
                self.assertEqual(len(active), 1)
                self.assertEqual(active[0]["responsibility_status"], "open")
                self.assertEqual(active[0]["work_status"], goal_status)

    def test_multi_goal_confirmation_denial_and_expiry_close_every_goal(self) -> None:
        expected = {
            "denied": "cancelled",
            "expired": "timed_out",
        }
        for decision, final_status in expected.items():
            with self.subTest(decision=decision):
                manager = ConversationStateManager(
                    base_conversation_id=f"confirmation-{decision}"
                )
                self._create_goals(manager, "goal-walk", "goal-blink")
                response = InteractionResponse(
                    interaction_id=f"interaction-{decision}",
                    capabilities=[
                        {
                            "request_id": "skill-walk",
                            "capability_id": "soridormi.walk_forward",
                            "metadata": {"source_goal_ids": ["goal-walk"]},
                        },
                        {
                            "request_id": "skill-blink",
                            "capability_id": "soridormi.blink_eyes",
                            "metadata": {"source_goal_ids": ["goal-blink"]},
                        },
                    ],
                    metadata={
                        "planning_result": "composed_plan",
                        "semantic_plan_confirmation_required": True,
                    },
                )

                bound_goal_ids = manager.record_confirmation_scope(
                    sid="sid-confirm",
                    confirmation_id="confirm-multi",
                    interaction_id=response.interaction_id,
                    fingerprint="fingerprint-multi",
                    expires_at=42.0,
                    response=response,
                    confirmed_request_ids={"skill-walk", "skill-blink"},
                )

                self.assertEqual(
                    bound_goal_ids,
                    ["goal-walk", "goal-blink"],
                )
                self.assertEqual(
                    [item["work_status"] for item in manager.active_goal_snapshots()],
                    ["awaiting_confirmation", "awaiting_confirmation"],
                )
                self.assertFalse(
                    any(
                        task["type"] == "goal_execution"
                        for task in manager.get_pending_tasks()
                    )
                )
                self.assertTrue(
                    manager.resolve_confirmation_scope(
                        confirmation_id="confirm-multi",
                        decision=decision,
                    )
                )
                active = manager.active_goal_snapshots()
                self.assertEqual(
                    [item["responsibility_status"] for item in active],
                    ["open", "open"],
                )
                self.assertEqual(
                    [item["work_status"] for item in active],
                    [final_status, final_status],
                )

    def test_multi_goal_confirmation_approval_schedules_only_after_approval(self) -> None:
        manager = ConversationStateManager(base_conversation_id="confirmation-approved")
        self._create_goals(manager, "goal-walk", "goal-blink")
        response = InteractionResponse(
            interaction_id="interaction-approved",
            capabilities=[
                {
                    "request_id": "skill-walk",
                    "capability_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "skill-blink",
                    "capability_id": "soridormi.blink_eyes",
                    "metadata": {"source_goal_ids": ["goal-blink"]},
                },
            ],
            metadata={
                "planning_result": "composed_plan",
                "semantic_plan_confirmation_required": True,
            },
        )
        manager.record_confirmation_scope(
            sid="sid-confirm",
            confirmation_id="confirm-multi",
            interaction_id=response.interaction_id,
            fingerprint="fingerprint-multi",
            expires_at=42.0,
            response=response,
            confirmed_request_ids={"skill-walk", "skill-blink"},
        )

        self.assertTrue(
            manager.resolve_confirmation_scope(
                confirmation_id="confirm-multi",
                decision="approved",
            )
        )
        self.assertEqual(
            [item["work_status"] for item in manager.active_goal_snapshots()],
            ["planning", "planning"],
        )

        manager.record_interaction_response(
            "sid-confirm",
            response,
            confirmed_request_ids={"skill-walk", "skill-blink"},
        )

        self.assertEqual(
            [item["work_status"] for item in manager.active_goal_snapshots()],
            ["scheduled", "scheduled"],
        )
        active_task_types = [
            task["type"] for task in manager.snapshot()["active_pending_tasks"]
        ]
        self.assertEqual(active_task_types, ["goal_execution", "goal_execution"])
        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="skill-walk",
                status="completed",
            )
        )
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-walk", "goal-blink"],
        )
        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="skill-blink",
                status="completed",
            )
        )
        self.assertEqual(
            [item["responsibility_status"] for item in manager.active_goal_snapshots()],
            ["open", "open"],
        )

    def test_compatible_goal_refinement_preserves_existing_plan_work(self) -> None:
        manager = ConversationStateManager(base_conversation_id="compatible-refinement")
        self._create_goals(manager, "goal-cup")
        manager.record_interaction_response(
            "sid-plan",
            InteractionResponse(
                metadata={
                    "planning_result": "composed_plan",
                    "canonical_plan": self._canonical_plan(
                        "execute",
                        [
                            {
                                "goal_id": "goal-cup",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["step-cup"],
                            }
                        ],
                    ),
                }
            ),
        )
        before = manager.snapshot()["task_contexts"][0]
        self.assertEqual(before["plan_version"], 1)
        self.assertEqual(before["plan_status"], "proposed")
        self.assertEqual(before["status"], "planning")

        applied = manager.apply_goal_association_resolution({'resolution_status': 'resolved', 'turn_id': 'turn-blue-cup', 'associations': [{'association_id': 'assoc-blue-cup', 'relationship': 'modify', 'target_goal_ids': ['goal-cup'], 'goal_update': {'description': 'Pick up the blue cup.'}, 'confidence': 0.99, 'reason_summary': 'The user refined the same cup responsibility.'}], 'confidence': 0.99, 'reason_summary': 'Same responsibility refinement.'}, sid='sid-blue', user_text='The blue one.', atomic=True)

        self.assertTrue(all(item.get("applied") is True for item in applied))
        after = manager.snapshot()["task_contexts"][0]
        self.assertEqual(after["semantic_goal"]["goal_id"], "goal-cup")
        self.assertEqual(after["goal_version"], 2)
        self.assertEqual(after["plan_version"], 1)
        self.assertEqual(after["plan_status"], "proposed")
        self.assertEqual(after["status"], "planning")
        self.assertNotIn("superseded_plan_versions", after)

    def test_goal_refinement_defers_work_compatibility_to_planner(self) -> None:
        manager = ConversationStateManager(base_conversation_id="incompatible-refinement")
        self._create_goals(manager, "goal-cup")
        manager.record_interaction_response(
            "sid-plan",
            InteractionResponse(
                metadata={
                    "planning_result": "composed_plan",
                    "canonical_plan": self._canonical_plan(
                        "execute",
                        [
                            {
                                "goal_id": "goal-cup",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["step-cup"],
                            }
                        ],
                    ),
                }
            ),
        )

        applied = manager.apply_goal_association_resolution({'resolution_status': 'resolved', 'turn_id': 'turn-red-cup', 'associations': [{'association_id': 'assoc-red-cup', 'relationship': 'modify', 'target_goal_ids': ['goal-cup'], 'goal_update': {'description': 'Pick up the red cup instead.'}, 'confidence': 0.99, 'reason_summary': 'The user changed the target within the same responsibility.'}], 'confidence': 0.99, 'reason_summary': 'Same responsibility refinement; Planner owns Work compatibility.'}, sid='sid-red', user_text='Actually, the red one.', atomic=True)

        self.assertTrue(all(item.get("applied") is True for item in applied))
        after = manager.snapshot()["task_contexts"][0]
        self.assertEqual(after["semantic_goal"]["goal_id"], "goal-cup")
        self.assertEqual(after["goal_version"], 2)
        self.assertEqual(after["plan_version"], 1)
        self.assertEqual(after["plan_status"], "proposed")
        self.assertEqual(after["status"], "planning")
        self.assertNotIn("superseded_plan_versions", after)

    def test_reconciliation_only_plan_preserves_retained_runtime_binding(self) -> None:
        manager = ConversationStateManager(
            base_conversation_id="retained-reconciliation-only"
        )
        self._create_goals(manager, "goal-weather")
        context = manager._task_contexts[0]
        context["plan_version"] = 2
        context["plan_status"] = "running"
        context["status"] = "running"
        context["metadata"] = {
            **context.get("metadata", {}),
            "canonical_plan_id": "plan-weather-existing",
            "canonical_plan_fingerprint": "e" * 64,
        }

        manager.record_interaction_response(
            "sid-weather-follow-up",
            InteractionResponse(
                metadata={
                    "planning_result": "composed_plan",
                    "canonical_plan_id": "plan-weather-reconciled",
                    "retained_work_reconciliation_only": True,
                }
            ),
        )

        after = manager.snapshot()["task_contexts"][0]
        self.assertEqual(after["plan_version"], 2)
        self.assertEqual(after["plan_status"], "running")
        self.assertEqual(
            after["metadata"]["canonical_plan_id"],
            "plan-weather-existing",
        )
        self.assertEqual(
            after["metadata"]["last_retained_work_reconciliation_plan_id"],
            "plan-weather-reconciled",
        )

    def test_execution_outcome_bundle_preserves_exact_mixed_goal_evidence(self) -> None:
        manager = ConversationStateManager(base_conversation_id="outcome-bundle")
        self._create_goals(manager, "goal-walk", "goal-blink")
        manager.record_interaction_response(
            "sid-outcome",
            InteractionResponse(
                interaction_id="interaction-outcome",
                capabilities=[
                    {
                        "request_id": "request-walk",
                        "capability_id": "soridormi.walk_forward",
                        "metadata": {
                            "source_goal_ids": ["goal-walk"],
                            "canonical_plan_id": "plan-lifecycle",
                            "canonical_plan_fingerprint": "f" * 64,
                        },
                    },
                    {
                        "request_id": "request-blink",
                        "capability_id": "soridormi.blink_eyes",
                        "metadata": {
                            "source_goal_ids": ["goal-blink"],
                            "canonical_plan_id": "plan-lifecycle",
                            "canonical_plan_fingerprint": "f" * 64,
                        },
                    },
                ],
                metadata={
                    "planning_result": "composed_plan",
                    "turn_id": "turn-outcome",
                    "canonical_plan_id": "plan-lifecycle",
                    "canonical_plan_fingerprint": "f" * 64,
                    "canonical_plan": self._canonical_plan(
                        "execute",
                        [
                            {
                                "goal_id": "goal-walk",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["step-walk"],
                            },
                            {
                                "goal_id": "goal-blink",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["step-blink"],
                            },
                        ],
                    ),
                },
            ),
        )
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-mixed",
            turn_id="turn-outcome",
            interaction_id="interaction-outcome",
            canonical_plan_id="plan-lifecycle",
            canonical_plan_fingerprint="f" * 64,
            canonical_goal_ids=["goal-walk", "goal-blink"],
            aggregate_status="partial",
            evidence=[
                {
                    "evidence_id": "evidence-walk",
                    "request_id": "request-walk",
                    "step_id": "step-walk",
                    "capability_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-walk"],
                    "status": "completed",
                },
                {
                    "evidence_id": "evidence-blink",
                    "request_id": "request-blink",
                    "step_id": "step-blink",
                    "capability_id": "soridormi.blink_eyes",
                    "source_goal_ids": ["goal-blink"],
                    "status": "not_run",
                    "missing_result": True,
                },
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "status": "completed",
                    "step_ids": ["step-walk"],
                    "evidence_ids": ["evidence-walk"],
                    "completed_step_ids": ["step-walk"],
                },
                {
                    "goal_id": "goal-blink",
                    "status": "not_run",
                    "step_ids": ["step-blink"],
                    "evidence_ids": ["evidence-blink"],
                    "unresolved_step_ids": ["step-blink"],
                    "reason_codes": ["missing_capability_result"],
                },
            ],
        )

        applied = manager.record_execution_outcome_bundle(
            bundle,
            sid="sid-outcome",
        )

        self.assertEqual(
            [item["status"] for item in applied],
            ["completed", "not_run"],
        )
        contexts = {
            item["semantic_goal"]["goal_id"]: item
            for item in manager.snapshot()["task_contexts"]
        }
        self.assertEqual(contexts["goal-walk"]["status"], "done")
        self.assertEqual(contexts["goal-blink"]["status"], "failed")
        self.assertEqual(
            contexts["goal-walk"]["semantic_goal"]["responsibility_status"],
            "open",
        )
        self.assertEqual(
            contexts["goal-blink"]["semantic_goal"]["responsibility_status"],
            "open",
        )
        reconciled = manager.reconcile_execution_outcome_responsibilities(
            bundle, sid="sid-outcome"
        )
        self.assertEqual(
            [item["responsibility_status"] for item in reconciled],
            ["satisfied", "open"],
        )
        self.assertEqual(
            [item["goal_id"] for item in manager.active_goal_snapshots()],
            ["goal-blink"],
        )
        self.assertEqual(
            contexts["goal-blink"]["evidence_summary"]["execution_outcome"][
                "status"
            ],
            "not_run",
        )
        self.assertEqual(
            contexts["goal-walk"]["metadata"]["execution_outcome_status"],
            "completed",
        )

    def test_completed_execution_with_insufficient_qualification_keeps_goal_open(self) -> None:
        manager = ConversationStateManager(base_conversation_id="qualification-open")
        self._create_goals(manager, "goal-walk")
        manager.record_interaction_response(
            "sid-qualified",
            InteractionResponse(
                interaction_id="interaction-qualified",
                capabilities=[
                    {
                        "request_id": "request-walk",
                        "capability_id": "soridormi.walk_forward",
                        "metadata": {
                            "source_goal_ids": ["goal-walk"],
                            "canonical_plan_id": "plan-lifecycle",
                            "canonical_plan_fingerprint": "q" * 64,
                        },
                    }
                ],
                metadata={
                    "planning_result": "direct_capability",
                    "turn_id": "turn-qualified",
                    "canonical_plan_id": "plan-lifecycle",
                    "canonical_plan_fingerprint": "q" * 64,
                    "canonical_plan": self._canonical_plan(
                        "execute",
                        [
                            {
                                "goal_id": "goal-walk",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["step-walk"],
                            }
                        ],
                    ),
                },
            ),
        )
        policy = ClaimQualificationPolicy(
            claim="embodied completion",
            requirement_groups=[
                {
                    "requirements": [
                        {"source": "execution_observation"},
                        {
                            "source": "provider_postcondition",
                            "condition": "post_execution_robot_status",
                            "field_assertions": {"safe_idle": True},
                        },
                    ]
                }
            ],
        )
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-qualified",
            turn_id="turn-qualified",
            interaction_id="interaction-qualified",
            canonical_plan_id="plan-lifecycle",
            canonical_plan_fingerprint="q" * 64,
            canonical_goal_ids=["goal-walk"],
            aggregate_status="completed",
            evidence=[
                {
                    "evidence_id": "evidence-walk",
                    "request_id": "request-walk",
                    "step_id": "step-walk",
                    "capability_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-walk"],
                    "status": "completed",
                    "completion_qualification": {
                        "claim": policy.claim,
                        "status": "insufficient",
                        "policy_sha256": claim_qualification_policy_sha256(policy),
                        "evidence_ids": ["evidence-walk"],
                        "reason_codes": ["provider_postcondition_missing"],
                        "coverage": "not_required",
                        "evaluated_at": datetime.now(timezone.utc),
                    },
                    "metadata": {
                        "completion_qualification_required": True,
                    },
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "status": "completed",
                    "step_ids": ["step-walk"],
                    "evidence_ids": ["evidence-walk"],
                    "completed_step_ids": ["step-walk"],
                }
            ],
        )

        applied = manager.record_execution_outcome_bundle(bundle, sid="sid-qualified")
        context = manager._task_context_by_goal_id("goal-walk")
        assert context is not None
        self.assertEqual(applied[0]["work_status"], "recoverable")
        self.assertEqual(context["status"], "recoverable")
        self.assertEqual(context["semantic_goal"]["responsibility_status"], "open")

        reconciled = manager.reconcile_execution_outcome_responsibilities(
            bundle, sid="sid-qualified"
        )
        self.assertEqual(reconciled[0]["responsibility_status"], "open")
        self.assertFalse(reconciled[0]["completion_qualification_established"])

        opportunities = manager.derive_execution_cognitive_opportunities(bundle)
        self.assertEqual(len(opportunities), 1)
        self.assertIn("provider_postcondition_missing", opportunities[0].reason_codes)

    def test_later_correction_reopens_satisfied_responsibility_without_rewriting_outcome(self) -> None:
        manager = ConversationStateManager(base_conversation_id="reopen-after-correction")
        self._create_goals(manager, "goal-cup")
        response = InteractionResponse(
            interaction_id="interaction-cup",
            capabilities=[
                {
                    "request_id": "request-cup",
                    "capability_id": "soridormi.pick_up",
                    "metadata": {
                        "source_goal_ids": ["goal-cup"],
                        "canonical_plan_id": "plan-lifecycle",
                        "canonical_plan_fingerprint": "c" * 64,
                    },
                }
            ],
            metadata={
                "planning_result": "composed_plan",
                "turn_id": "turn-cup",
                "canonical_plan_id": "plan-lifecycle",
                "canonical_plan_fingerprint": "c" * 64,
                "canonical_plan": self._canonical_plan(
                    "execute",
                    [
                        {
                            "goal_id": "goal-cup",
                            "disposition": "execute",
                            "coverage": "complete",
                            "step_ids": ["step-cup"],
                        }
                    ],
                ),
            },
        )
        manager.record_interaction_response("sid-cup", response)
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-cup",
            turn_id="turn-cup",
            interaction_id="interaction-cup",
            canonical_plan_id="plan-lifecycle",
            canonical_plan_fingerprint="c" * 64,
            canonical_goal_ids=["goal-cup"],
            aggregate_status="completed",
            evidence=[
                {
                    "evidence_id": "evidence-cup",
                    "request_id": "request-cup",
                    "step_id": "step-cup",
                    "capability_id": "soridormi.pick_up",
                    "source_goal_ids": ["goal-cup"],
                    "status": "completed",
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-cup",
                    "status": "completed",
                    "step_ids": ["step-cup"],
                    "evidence_ids": ["evidence-cup"],
                    "completed_step_ids": ["step-cup"],
                }
            ],
        )
        manager.record_execution_outcome_bundle(bundle, sid="sid-cup")
        manager.reconcile_execution_outcome_responsibilities(bundle, sid="sid-cup")
        self.assertEqual(manager.active_goal_snapshots(), [])
        self.assertEqual(
            manager.recent_goal_snapshots()[0]["responsibility_status"],
            "satisfied",
        )

        correction = manager.apply_goal_association_resolution({'resolution_status': 'resolved', 'turn_id': 'turn-correction', 'associations': [{'association_id': 'assoc-correction', 'relationship': 'modify', 'target_goal_ids': ['goal-cup'], 'goal_update': {'description': 'Pick up the blue cup, not the red cup.'}, 'confidence': 0.99, 'reason_summary': 'The user corrected the intended cup.'}], 'confidence': 0.99, 'reason_summary': 'The same responsibility was misunderstood.'}, sid='sid-correction', user_text='No, I meant the blue cup.', atomic=True)
        self.assertTrue(all(item.get("applied") is True for item in correction))
        active = manager.active_goal_snapshots()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["goal_id"], "goal-cup")
        self.assertEqual(active[0]["responsibility_status"], "open")
        context = manager.snapshot()["task_contexts"][0]
        self.assertEqual(
            context["evidence_summary"]["execution_outcome"]["outcome_id"],
            "outcome-cup",
        )

    def test_interrupted_safe_read_stays_recoverable_with_bound_arguments(self) -> None:
        manager = ConversationStateManager(base_conversation_id="recoverable-weather")
        self._create_goals(manager, "goal-weather")
        response = InteractionResponse(
            interaction_id="interaction-weather",
            capabilities=[
                {
                    "request_id": "request-weather",
                    "capability_id": "chromie.weather.lookup",
                    "args": {"location": "上海", "date": "today"},
                    "timing": "parallel",
                    "metadata": {
                        "source_goal_ids": ["goal-weather"],
                        "canonical_plan_id": "plan-weather",
                        "canonical_plan_fingerprint": "a" * 64,
                        "safety_class": "safe_read",
                        "retryable_safe_read": True,
                    },
                }
            ],
            metadata={
                "planning_result": "composed_plan",
                "turn_id": "turn-weather",
                "canonical_plan_id": "plan-weather",
                "canonical_plan_fingerprint": "a" * 64,
                "canonical_plan": {
                    "plan_id": "plan-weather",
                    "planner_tier": "deep",
                    "disposition": "execute",
                    "coverage": "complete",
                    "confidence": 0.95,
                    "goal_ids": ["goal-weather"],
                    "steps": [
                        {
                            "step_id": "step-weather",
                            "capability_id": "chromie.weather.lookup",
                            "args": {"location": "上海", "date": "today"},
                            "timing": "sequential",
                            "source_goal_ids": ["goal-weather"],
                        }
                    ],
                    "goal_outcomes": [
                        {
                            "goal_id": "goal-weather",
                            "disposition": "execute",
                            "coverage": "complete",
                            "step_ids": ["step-weather"],
                        }
                    ],
                },
            },
        )
        manager.record_interaction_response("sid-weather", response)
        bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-weather-interrupted",
            turn_id="turn-weather",
            interaction_id="interaction-weather",
            canonical_plan_id="plan-weather",
            canonical_plan_fingerprint="a" * 64,
            canonical_goal_ids=["goal-weather"],
            aggregate_status="not_run",
            evidence=[
                {
                    "evidence_id": "evidence-weather",
                    "request_id": "request-weather",
                    "step_id": "step-weather",
                    "capability_id": "chromie.weather.lookup",
                    "source_goal_ids": ["goal-weather"],
                    "status": "not_run",
                    "missing_result": True,
                    "metadata": {
                        "request_args": {"location": "上海", "date": "today"},
                        "safety_class": "safe_read",
                        "retryable_safe_read": True,
                    },
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-weather",
                    "status": "not_run",
                    "step_ids": ["step-weather"],
                    "evidence_ids": ["evidence-weather"],
                    "unresolved_step_ids": ["step-weather"],
                    "reason_codes": ["missing_capability_result"],
                }
            ],
        )

        applied = manager.record_execution_outcome_bundle(
            bundle,
            sid="sid-weather",
        )

        self.assertEqual(applied[0]["work_status"], "recoverable")
        snapshots = manager.active_task_snapshots()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["status"], "recoverable")
        binding = snapshots[0]["metadata"]["execution_binding"]
        self.assertTrue(binding["retryable_safe_read"])
        self.assertEqual(
            binding["planned_capabilities"][0]["args"],
            {"location": "上海", "date": "today"},
        )
        opportunities = manager.derive_execution_cognitive_opportunities(
            bundle,
            situation_digest="s" * 64,
        )
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].goal_ids, ["goal-weather"])
        self.assertEqual(opportunities[0].recommended_cognition, "fast")
        self.assertEqual(
            opportunities[0].evidence_refs,
            ["outcome-weather-interrupted", "evidence-weather"],
        )
        self.assertEqual(opportunities[0].reason_codes, ["missing_capability_result"])
        self.assertEqual(opportunities[0].situation_digest, "s" * 64)
        self.assertNotIn("cognitive_opportunities", manager.snapshot())

    def test_stale_outcome_cannot_overwrite_a_newer_goal_plan_binding(self) -> None:
        manager = ConversationStateManager(base_conversation_id="stale-outcome")
        self._create_goals(manager, "goal-walk")

        def response(
            *,
            interaction_id: str,
            turn_id: str,
            plan_id: str,
            fingerprint: str,
            request_id: str,
        ) -> InteractionResponse:
            return InteractionResponse(
                interaction_id=interaction_id,
                capabilities=[
                    {
                        "request_id": request_id,
                        "capability_id": "soridormi.walk_forward",
                        "metadata": {
                            "source_goal_ids": ["goal-walk"],
                            "canonical_plan_id": plan_id,
                            "canonical_plan_fingerprint": fingerprint,
                        },
                    }
                ],
                metadata={
                    "planning_result": "composed_plan",
                    "turn_id": turn_id,
                    "canonical_plan_id": plan_id,
                    "canonical_plan_fingerprint": fingerprint,
                    "canonical_plan": self._canonical_plan(
                        "execute",
                        [
                            {
                                "goal_id": "goal-walk",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["step-walk"],
                            }
                        ],
                    ),
                },
            )

        manager.record_interaction_response(
            "sid-current",
            response(
                interaction_id="interaction-old",
                turn_id="turn-old",
                plan_id="plan-old",
                fingerprint="a" * 64,
                request_id="request-old",
            ),
        )
        manager.record_interaction_response(
            "sid-current",
            response(
                interaction_id="interaction-new",
                turn_id="turn-new",
                plan_id="plan-new",
                fingerprint="b" * 64,
                request_id="request-new",
            ),
        )
        stale_bundle = ExecutionOutcomeBundle(
            outcome_id="outcome-old",
            turn_id="turn-old",
            interaction_id="interaction-old",
            canonical_plan_id="plan-old",
            canonical_plan_fingerprint="a" * 64,
            canonical_goal_ids=["goal-walk"],
            aggregate_status="completed",
            evidence=[
                {
                    "evidence_id": "evidence-old",
                    "request_id": "request-old",
                    "step_id": "step-walk",
                    "capability_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-walk"],
                    "status": "completed",
                }
            ],
            goal_outcomes=[
                {
                    "goal_id": "goal-walk",
                    "status": "completed",
                    "step_ids": ["step-walk"],
                    "evidence_ids": ["evidence-old"],
                    "completed_step_ids": ["step-walk"],
                }
            ],
        )

        with self.assertRaisesRegex(ValueError, "stale"):
            manager.record_execution_outcome_bundle(
                stale_bundle,
                sid="sid-current",
            )

        context = manager.snapshot()["task_contexts"][0]
        self.assertEqual(context["metadata"]["canonical_plan_id"], "plan-new")
        self.assertNotIn("execution_outcome", context["evidence_summary"])
        pending = manager.snapshot()["pending_tasks"]
        self.assertEqual(
            [task["status"] for task in pending if task["type"] == "goal_execution"],
            ["scheduled", "scheduled"],
        )

    def test_not_run_never_creates_a_false_completed_memory(self) -> None:
        manager = ConversationStateManager(base_conversation_id="not-run-memory")
        self._create_goals(manager, "goal-walk")
        manager.record_interaction_response(
            "sid-not-run",
            InteractionResponse(
                capabilities=[
                    {
                        "request_id": "request-not-run",
                        "capability_id": "soridormi.walk_forward",
                        "metadata": {"source_goal_ids": ["goal-walk"]},
                    }
                ],
                metadata={
                    "planning_result": "composed_plan",
                    "canonical_plan": self._canonical_plan(
                        "execute",
                        [
                            {
                                "goal_id": "goal-walk",
                                "disposition": "execute",
                                "coverage": "complete",
                                "step_ids": ["step-walk"],
                            }
                        ],
                    ),
                },
            ),
        )

        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="request-not-run",
                status="not_run",
            )
        )

        snapshot = manager.snapshot()
        self.assertEqual(snapshot["task_contexts"][0]["status"], "failed")
        outcome_texts = [
            item["text"]
            for item in snapshot["extracted_memory"]
            if item["kind"] == "outcome"
        ]
        self.assertTrue(any(" is failed" in text for text in outcome_texts))
        self.assertFalse(any("task completed" in text for text in outcome_texts))




class AcceptedDialogueSemanticStatusTests(unittest.TestCase):
    def test_failed_precommit_turn_remains_dialogue_evidence_without_goal_creation(self) -> None:
        manager = ConversationStateManager(enabled=True)
        manager.record_accepted_user_turn(
            "sid-failed",
            "帮我找附近好吃的地方。",
            metadata={"source": "cognitive_gateway_admitted_dialogue"},
        )

        manager.record_user_turn('sid-failed', '帮我找附近好吃的地方。', metadata={'semantic_task_resolution_authoritative': True, 'semantic_status': 'failed', 'semantic_failure_stage': 'goal_association', 'semantic_failure_class': 'contract_failure', 'canonical_goal_committed': False})
        turn = manager.user_turn_snapshot("sid-failed")
        self.assertEqual(turn["text"], "帮我找附近好吃的地方。")
        self.assertEqual(turn["metadata"]["semantic_status"], "failed")
        self.assertEqual(
            turn["metadata"]["semantic_failure_stage"],
            "goal_association",
        )
        self.assertFalse(turn["metadata"]["canonical_goal_committed"])
        self.assertEqual(manager.active_goal_snapshots(), [])
        self.assertEqual(manager.active_task_snapshots(), [])


if __name__ == "__main__":
    unittest.main()

class TimeConditionContinuousCognitionTests(unittest.TestCase):
    def _manager_with_bound_goal(self) -> ConversationStateManager:
        manager = ConversationStateManager(base_conversation_id="time-condition")
        GoalScopedLifecycleTests._create_goals(manager, "goal-reminder")
        context = manager._task_contexts[0]
        context["semantic_goal"]["source_responsibility_refs"] = ["resp-reminder"]
        context["metadata"] = {
            **context.get("metadata", {}),
            "canonical_plan_id": "plan-reminder",
            "planner_reentry_language": "en-US",
            "planner_reentry_responsibilities": [
                {
                    "schema_version": 1,
                    "local_ref": "resp-reminder",
                    "outcome": "Remind the user at the requested time.",
                    "bindings": {},
                    "output_mode": "stateful_effect",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                }
            ],
        }
        return manager

    def test_structured_time_condition_is_durable_and_emits_once_when_due(self) -> None:
        from shared.chromie_contracts.situation import GoalTimeCondition

        with TemporaryDirectory() as tmp:
            store = Path(tmp) / "tasks.json"
            manager = self._manager_with_bound_goal()
            manager.task_store_enabled = True
            manager.task_store_path = store
            condition = GoalTimeCondition(
                condition_id="condition-reminder",
                goal_id="goal-reminder",
                due_at_ms=2_000,
                source_plan_id="plan-reminder",
                source_responsibility_refs=["resp-reminder"],
            )
            self.assertTrue(manager.register_goal_time_condition(condition))
            self.assertEqual(manager.next_time_condition_due_ms(), 2_000)
            self.assertEqual(manager.due_time_condition_opportunities(now_ms=1_999), [])

            due = manager.due_time_condition_opportunities(now_ms=2_000)
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["condition"]["condition_id"], "condition-reminder")
            self.assertEqual(due[0]["opportunity"]["trigger"], "time_condition")
            self.assertEqual(due[0]["opportunity"]["goal_ids"], ["goal-reminder"])
            self.assertEqual(due[0]["language"], "en-US")
            self.assertEqual(
                due[0]["responsibilities"][0]["local_ref"],
                "resp-reminder",
            )
            self.assertIsNone(manager.next_time_condition_due_ms())
            self.assertEqual(manager.due_time_condition_opportunities(now_ms=3_000), [])
            self.assertTrue(store.exists())

    def test_time_condition_rejects_stale_plan_or_unbound_responsibility(self) -> None:
        from shared.chromie_contracts.situation import GoalTimeCondition

        manager = self._manager_with_bound_goal()
        base = {
            "condition_id": "condition-stale",
            "goal_id": "goal-reminder",
            "due_at_ms": 2_000,
            "source_plan_id": "plan-old",
            "source_responsibility_refs": ["resp-reminder"],
        }
        self.assertFalse(manager.register_goal_time_condition(GoalTimeCondition(**base)))
        base["source_plan_id"] = "plan-reminder"
        base["source_responsibility_refs"] = ["resp-other"]
        self.assertFalse(manager.register_goal_time_condition(GoalTimeCondition(**base)))
