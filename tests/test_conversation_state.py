from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.execution_outcome import ExecutionOutcomeBundle
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


class GoalScopedLifecycleTests(unittest.TestCase):
    @staticmethod
    def _create_goals(
        manager: ConversationStateManager,
        *goal_ids: str,
    ) -> list[dict]:
        return manager.apply_goal_association_resolution(
            {
                "turn_id": "turn-create-" + "-".join(goal_ids),
                "new_goals": [
                    {
                        "goal_id": goal_id,
                        "description": f"Complete {goal_id}.",
                        "source_text": f"Complete {goal_id}.",
                    }
                    for goal_id in goal_ids
                ],
                "confidence": 0.95,
                "reason_summary": "Independent user goals.",
            },
            sid="sid-create",
            user_text="Complete the requested goals.",
            route="robot_action",
            intent="compound_action",
            atomic=True,
        )

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
            skills=[
                {
                    "request_id": "skill-walk",
                    "skill_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "skill-blink",
                    "skill_id": "soridormi.blink_eyes",
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

        manager.record_agent_result("sid-execute", response)
        self.assertEqual(
            [item["status"] for item in manager.active_goal_snapshots()],
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
            ["goal-blink"],
        )

        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="skill-blink",
                status="completed",
            )
        )
        self.assertEqual(manager.active_goal_snapshots(), [])

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

        manager.record_agent_result("sid-answer", response)

        active = manager.active_goal_snapshots()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["goal_id"], "goal-answer")
        self.assertEqual(active[0]["status"], "scheduled")
        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="speech-answer",
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

        manager.record_agent_result("sid-clarify", response)

        active = manager.active_goal_snapshots()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["status"], "waiting_for_user")
        self.assertEqual(active[0]["commitment_state"], "waiting_for_user")
        self.assertFalse(
            manager.update_pending_task_status_for_request_id(
                request_id="speech-question",
                status="completed",
            )
        )
        self.assertEqual(
            manager.active_goal_snapshots()[0]["status"],
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
                manager.record_agent_result(
                    "sid-action",
                    InteractionResponse(
                        skills=[
                            {
                                "request_id": "skill-action",
                                "skill_id": "soridormi.blink_eyes",
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
                self.assertEqual(manager.active_goal_snapshots(), [])
                self.assertEqual(
                    manager.snapshot()["task_contexts"][0]["status"],
                    goal_status,
                )

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
                    skills=[
                        {
                            "request_id": "skill-walk",
                            "skill_id": "soridormi.walk_forward",
                            "metadata": {"source_goal_ids": ["goal-walk"]},
                        },
                        {
                            "request_id": "skill-blink",
                            "skill_id": "soridormi.blink_eyes",
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
                    [item["status"] for item in manager.active_goal_snapshots()],
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
                self.assertEqual(manager.active_goal_snapshots(), [])
                self.assertEqual(
                    [
                        item["status"]
                        for item in manager.snapshot()["task_contexts"]
                    ],
                    [final_status, final_status],
                )

    def test_multi_goal_confirmation_approval_schedules_only_after_approval(self) -> None:
        manager = ConversationStateManager(base_conversation_id="confirmation-approved")
        self._create_goals(manager, "goal-walk", "goal-blink")
        response = InteractionResponse(
            interaction_id="interaction-approved",
            skills=[
                {
                    "request_id": "skill-walk",
                    "skill_id": "soridormi.walk_forward",
                    "metadata": {"source_goal_ids": ["goal-walk"]},
                },
                {
                    "request_id": "skill-blink",
                    "skill_id": "soridormi.blink_eyes",
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
            [item["status"] for item in manager.active_goal_snapshots()],
            ["planning", "planning"],
        )

        manager.record_agent_result(
            "sid-confirm",
            response,
            confirmed_request_ids={"skill-walk", "skill-blink"},
        )

        self.assertEqual(
            [item["status"] for item in manager.active_goal_snapshots()],
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
            ["goal-blink"],
        )
        self.assertTrue(
            manager.update_pending_task_status_for_request_id(
                request_id="skill-blink",
                status="completed",
            )
        )
        self.assertEqual(manager.active_goal_snapshots(), [])

    def test_execution_outcome_bundle_preserves_exact_mixed_goal_evidence(self) -> None:
        manager = ConversationStateManager(base_conversation_id="outcome-bundle")
        self._create_goals(manager, "goal-walk", "goal-blink")
        manager.record_agent_result(
            "sid-outcome",
            InteractionResponse(
                interaction_id="interaction-outcome",
                skills=[
                    {
                        "request_id": "request-walk",
                        "skill_id": "soridormi.walk_forward",
                        "metadata": {
                            "source_goal_ids": ["goal-walk"],
                            "canonical_plan_id": "plan-lifecycle",
                            "canonical_plan_fingerprint": "f" * 64,
                        },
                    },
                    {
                        "request_id": "request-blink",
                        "skill_id": "soridormi.blink_eyes",
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
                    "skill_id": "soridormi.walk_forward",
                    "source_goal_ids": ["goal-walk"],
                    "status": "completed",
                },
                {
                    "evidence_id": "evidence-blink",
                    "request_id": "request-blink",
                    "step_id": "step-blink",
                    "skill_id": "soridormi.blink_eyes",
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
                    "reason_codes": ["missing_skill_result"],
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
            contexts["goal-blink"]["evidence_summary"]["execution_outcome"][
                "status"
            ],
            "not_run",
        )
        self.assertEqual(
            contexts["goal-walk"]["metadata"]["execution_outcome_status"],
            "completed",
        )

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
                skills=[
                    {
                        "request_id": request_id,
                        "skill_id": "soridormi.walk_forward",
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

        manager.record_agent_result(
            "sid-current",
            response(
                interaction_id="interaction-old",
                turn_id="turn-old",
                plan_id="plan-old",
                fingerprint="a" * 64,
                request_id="request-old",
            ),
        )
        manager.record_agent_result(
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
                    "skill_id": "soridormi.walk_forward",
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
        manager.record_agent_result(
            "sid-not-run",
            InteractionResponse(
                skills=[
                    {
                        "request_id": "request-not-run",
                        "skill_id": "soridormi.walk_forward",
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


if __name__ == "__main__":
    unittest.main()
