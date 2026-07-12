from __future__ import annotations

import unittest

from agent.app.agents.capability import CapabilityAgent
from agent.app.agents.base import AgentServices
from orchestrator.runtime.conversation_state import ConversationStateManager
from router.app.llm_router import OllamaLLMRouter
from router.app.schema import RouteRequest
from shared.chromie_contracts.semantic_task import (
    SemanticGoal,
    SemanticTaskOperation,
)


class SemanticTaskContractTests(unittest.TestCase):
    def test_create_operation_requires_open_semantic_goal(self) -> None:
        operation = SemanticTaskOperation(
            operation_id="op-create-coffee",
            operation="create",
            confidence=0.98,
            goal=SemanticGoal(
                description="Prepare or obtain a coffee for the current user.",
                source_text="Bring me a coffee.",
            ),
            requires_replan=True,
        )

        self.assertEqual(operation.operation, "create")
        self.assertEqual(operation.goal.description, "Prepare or obtain a coffee for the current user.")

    def test_semantic_goal_rejects_low_level_control_fields(self) -> None:
        with self.assertRaises(ValueError):
            SemanticGoal(
                description="Move an actuator.",
                source_text="Move it.",
                constraints={"joint_targets": [0.1, 0.2]},
            )


class ConversationSemanticTaskTests(unittest.TestCase):
    @staticmethod
    def _create_coffee(manager: ConversationStateManager) -> str:
        manager.record_user_turn(
            "s1",
            "Bring me a coffee.",
            route="deep_thought",
            intent="prepare or obtain coffee for the current user",
            metadata={
                "source": "llm",
                "semantic_task_operations": [
                    {
                        "operation_id": "op-create-coffee",
                        "operation": "create",
                        "confidence": 0.98,
                        "relationship": "new independent user goal",
                        "goal": {
                            "description": "Prepare or obtain a coffee and deliver it to the current user.",
                            "source_text": "Bring me a coffee.",
                            "constraints": {},
                        },
                        "requires_replan": True,
                    }
                ],
            },
        )
        return manager.snapshot()["current_task_context"]["task_id"]

    def test_create_operation_builds_versioned_open_goal(self) -> None:
        manager = ConversationStateManager()
        task_id = self._create_coffee(manager)

        snapshot = manager.snapshot()["active_task_snapshots"][0]

        self.assertEqual(snapshot["task_id"], task_id)
        self.assertEqual(snapshot["goal_version"], 1)
        self.assertEqual(snapshot["plan_version"], 0)
        self.assertEqual(snapshot["status"], "planning")
        self.assertIn("coffee", snapshot["semantic_goal"]["description"].lower())

    def test_modify_operation_revises_goal_and_supersedes_plan_and_confirmation(self) -> None:
        manager = ConversationStateManager()
        task_id = self._create_coffee(manager)
        context = manager.snapshot()["current_task_context"]
        context["plan_version"] = 1
        context["plan_status"] = "proposed"
        context["confirmation"] = {
            "confirmation_id": "confirm-v1",
            "goal_version": 1,
        }

        manager.record_user_turn(
            "s2",
            "Make the coffee iced.",
            route="deep_thought",
            intent="refine the active coffee request",
            metadata={
                "source": "llm",
                "semantic_task_operations": [
                    {
                        "operation_id": "op-ice-coffee",
                        "operation": "modify",
                        "target_task_ids": [task_id],
                        "confidence": 0.99,
                        "relationship": "constraint refinement",
                        "goal_update": {
                            "description": "Prepare or obtain an iced coffee and deliver it to the current user.",
                            "constraint_updates": {"temperature": "iced"},
                        },
                        "requires_replan": True,
                    }
                ],
            },
        )

        updated = manager.snapshot()["current_task_context"]

        self.assertEqual(updated["task_id"], task_id)
        self.assertEqual(updated["goal_version"], 2)
        self.assertEqual(updated["semantic_goal"]["constraints"]["temperature"], "iced")
        self.assertEqual(updated["plan_status"], "superseded")
        self.assertIn(1, updated["superseded_plan_versions"])
        self.assertIsNone(updated["confirmation"])
        self.assertEqual(updated["invalidated_confirmations"][-1]["confirmation_id"], "confirm-v1")

    def test_planner_clarification_waits_and_answer_resumes_same_task(self) -> None:
        manager = ConversationStateManager()
        task_id = self._create_coffee(manager)

        manager.record_agent_result(
            "s1",
            {
                "metadata": {
                    "planning_result": "needs_clarification",
                    "task_id": task_id,
                    "goal_version": 1,
                    "information_gaps": [
                        {
                            "gap_id": "coffee-temperature",
                            "description": "The user's preferred coffee temperature.",
                            "blocking": True,
                            "required_for": ["select preparation capability"],
                            "preferred_resolution": "ask_user",
                            "candidate_values": ["hot", "iced"],
                        }
                    ],
                },
                "speak_immediate": [{"text": "Would you like it hot or iced?"}],
            },
        )

        waiting = manager.snapshot()["current_task_context"]
        self.assertEqual(waiting["task_id"], task_id)
        self.assertEqual(waiting["status"], "waiting_for_user")
        self.assertEqual(waiting["open_information_gaps"][0]["gap_id"], "coffee-temperature")

        manager.record_user_turn(
            "s2",
            "Iced, with no sugar.",
            route="deep_thought",
            intent="answer active coffee clarification",
            metadata={
                "source": "llm",
                "semantic_task_operations": [
                    {
                        "operation_id": "op-answer-temperature",
                        "operation": "clarification_answer",
                        "target_task_ids": [task_id],
                        "confidence": 0.99,
                        "relationship": "answers a blocking information gap",
                        "goal_update": {
                            "constraint_updates": {
                                "temperature": "iced",
                                "sugar": "none",
                            }
                        },
                        "resolved_gap_ids": ["coffee-temperature"],
                        "requires_replan": True,
                    }
                ],
            },
        )

        resumed = manager.snapshot()["current_task_context"]
        self.assertEqual(resumed["task_id"], task_id)
        self.assertEqual(resumed["goal_version"], 2)
        self.assertEqual(resumed["status"], "planning")
        self.assertEqual(resumed["open_information_gaps"], [])
        self.assertEqual(resumed["semantic_goal"]["constraints"]["temperature"], "iced")
        self.assertEqual(resumed["semantic_goal"]["constraints"]["sugar"], "none")

    def test_alternative_plan_is_retained_as_pending_confirmation(self) -> None:
        manager = ConversationStateManager()
        task_id = self._create_coffee(manager)

        manager.record_agent_result(
            "s1",
            {
                "metadata": {
                    "planning_result": "alternative_plan",
                    "task_id": task_id,
                    "goal_version": 1,
                    "semantic_plan_confirmation_required": True,
                    "confirmation_prompt": "I can bring tea instead. Is that okay?",
                    "planned_skills": [
                        {
                            "skill_id": "service.prepare_tea",
                            "args": {"size": "small"},
                            "timing": "sequential",
                        }
                    ],
                },
                "speak_immediate": [],
            },
        )

        pending = manager.snapshot()["current_task_context"]

        self.assertEqual(pending["status"], "awaiting_confirmation")
        self.assertEqual(pending["commitment_state"], "waiting_for_user")
        self.assertEqual(
            pending["pending_questions"],
            ["I can bring tea instead. Is that okay?"],
        )
        self.assertEqual(pending["plan_summary"]["result"], "alternative_plan")
        self.assertEqual(pending["confirmation"]["status"], "pending")

    def test_semantic_operation_replay_is_idempotent(self) -> None:
        manager = ConversationStateManager()
        task_id = self._create_coffee(manager)
        operation = {
            "operation_id": "op-ice-replay",
            "operation": "modify",
            "target_task_ids": [task_id],
            "confidence": 0.99,
            "goal_update": {
                "description": "Prepare or obtain an iced coffee for the current user.",
                "constraint_updates": {"temperature": "iced"},
            },
            "requires_replan": True,
        }

        first = manager.apply_semantic_task_operations(
            [operation],
            sid="s2",
            user_text="Make it iced.",
            route="deep_thought",
            intent="modify coffee",
            source="llm",
        )
        second = manager.apply_semantic_task_operations(
            [operation],
            sid="s2",
            user_text="Make it iced.",
            route="deep_thought",
            intent="modify coffee",
            source="llm",
        )

        context = manager.snapshot()["current_task_context"]
        self.assertTrue(first[0]["applied"])
        self.assertFalse(second[0]["applied"])
        self.assertTrue(second[0]["replayed"])
        self.assertEqual(context["goal_version"], 2)
        self.assertEqual(
            [item["operation_id"] for item in context["operation_history"]].count("op-ice-replay"),
            1,
        )

    def test_create_operation_replay_returns_existing_task(self) -> None:
        manager = ConversationStateManager()
        operation = {
            "operation_id": "op-create-once",
            "operation": "create",
            "confidence": 0.99,
            "goal": {
                "description": "Prepare or obtain coffee for the current user.",
                "source_text": "Bring me coffee.",
            },
            "requires_replan": True,
        }

        first = manager.apply_semantic_task_operations(
            [operation],
            sid="s1",
            user_text="Bring me coffee.",
            route="deep_thought",
            source="llm",
        )
        second = manager.apply_semantic_task_operations(
            [operation],
            sid="s1",
            user_text="Bring me coffee.",
            route="deep_thought",
            source="llm",
        )

        self.assertEqual(len(manager.snapshot()["active_task_contexts"]), 1)
        self.assertEqual(second[0]["task_id"], first[0]["task_id"])
        self.assertFalse(second[0]["applied"])
        self.assertTrue(second[0]["replayed"])

    def test_plain_chat_does_not_create_or_rebind_task_by_phrase(self) -> None:
        manager = ConversationStateManager()
        task_id = self._create_coffee(manager)

        manager.record_user_turn(
            "s2",
            "That one is interesting.",
            route="chat",
            intent="casual_conversation",
        )

        tasks = manager.snapshot()["active_task_contexts"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], task_id)
        self.assertEqual(tasks[0]["goal_version"], 1)

    def test_unknown_task_operation_is_retained_as_rejected_audit_result(self) -> None:
        manager = ConversationStateManager()
        manager.record_user_turn(
            "s1",
            "Make it iced.",
            route="deep_thought",
            intent="modify task",
            metadata={
                "semantic_task_operations": [
                    {
                        "operation_id": "op-missing-target",
                        "operation": "modify",
                        "target_task_ids": ["missing-task"],
                        "confidence": 0.8,
                        "goal_update": {"constraint_updates": {"temperature": "iced"}},
                        "requires_replan": True,
                    }
                ]
            },
        )

        result = manager.get_history()[-1]["metadata"]["semantic_task_operation_results"][0]
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"], "unknown_task_id")


class RouterSemanticTaskPromptTests(unittest.TestCase):
    def test_prompt_exposes_bounded_active_goal_and_semantic_operation_contract(self) -> None:
        router = OllamaLLMRouter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            confidence_threshold=0.55,
        )
        prompt = router.build_user_prompt(
            RouteRequest(
                sid="s2",
                text="Make that coffee iced.",
                context={
                    "active_task_snapshots": [
                        {
                            "task_id": "task-coffee-001",
                            "status": "planning",
                            "goal_version": 1,
                            "plan_version": 0,
                            "semantic_goal": {
                                "description": "Prepare or obtain coffee for the current user.",
                                "source_text": "Bring me a coffee.",
                                "constraints": {},
                            },
                            "open_information_gaps": [],
                        }
                    ]
                },
            )
        )

        self.assertIn("task-coffee-001", prompt)
        self.assertIn("Prepare or obtain coffee", prompt)
        self.assertIn("metadata.semantic_task_operations", prompt)
        self.assertIn("never keywords, regexes", prompt)
        self.assertIn("open goal", prompt)


class CapabilityInformationGapTests(unittest.TestCase):
    def test_required_schema_fields_become_structured_information_gaps(self) -> None:
        agent = CapabilityAgent(AgentServices())

        gaps = agent._schema_information_gaps(
            "kitchen.prepare_coffee",
            {"size": "large"},
            {
                "type": "object",
                "required": ["temperature", "size"],
                "properties": {
                    "temperature": {
                        "type": "string",
                        "description": "Whether the coffee should be hot or iced.",
                        "enum": ["hot", "iced"],
                    },
                    "size": {"type": "string"},
                },
            },
        )

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].gap_id, "kitchen.prepare_coffee:temperature")
        self.assertEqual(gaps[0].preferred_resolution, "ask_user")
        self.assertEqual(gaps[0].candidate_values, ["hot", "iced"])


if __name__ == "__main__":
    unittest.main()
