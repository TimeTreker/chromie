from __future__ import annotations

import unittest
from typing import Any

from agent.app.schema import AgentRunRequest, RouteDecision
from agent.app.task_continuity import TaskContinuityResolver
from orchestrator.orchestrator import VoiceAssistant
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_contracts.semantic_task import (
    ResponsePlan,
    ResponseStage,
    SemanticGoal,
    SemanticTaskOperation,
    SemanticTaskOperationSet,
)


class _FakeOllama:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, **kwargs})
        return self.payload




class _FailingOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        raise TimeoutError("continuity model timed out")


class TaskContinuityResolverTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _request(text: str = "Make the coffee iced.") -> AgentRunRequest:
        return AgentRunRequest(
            sid="sid-42",
            text=text,
            route_decision=RouteDecision(
                route="deep_thought",
                intent="refine an active request",
                confidence=0.91,
                metadata={
                    "semantic_task_operations": [
                        {
                            "operation_id": "router-advisory",
                            "operation": "create",
                            "confidence": 0.7,
                            "goal": {
                                "description": "A router guess.",
                                "source_text": text,
                            },
                        }
                    ]
                },
            ),
            context={
                "conversation_id": "conversation-1",
                "active_task_snapshots": [
                    {
                        "task_id": "task-coffee-001",
                        "status": "planning",
                        "semantic_goal": {
                            "description": "Prepare or obtain a coffee for the current user.",
                            "source_text": "Bring me a coffee.",
                        },
                        "goal_version": 1,
                        "plan_version": 0,
                        "open_information_gaps": [],
                        "commitment_state": "evaluating",
                    },
                    {
                        "task_id": "task-weather-002",
                        "status": "running",
                        "semantic_goal": {
                            "description": "Check the requested weather.",
                            "source_text": "Check the weather.",
                        },
                        "goal_version": 1,
                        "plan_version": 1,
                        "open_information_gaps": [],
                        "commitment_state": "executing",
                    },
                ],
            },
        )

    async def test_resolver_semantically_modifies_existing_task(self) -> None:
        fake = _FakeOllama(
            {
                "operations": [
                    {
                        "operation_id": "model-generated-id-is-replaced",
                        "operation": "modify",
                        "target_task_ids": ["task-coffee-001"],
                        "confidence": 0.98,
                        "relationship": "constraint refinement",
                        "goal_update": {
                            "description": "Prepare or obtain an iced coffee for the current user.",
                            "constraint_updates": {"temperature": "iced"},
                        },
                        "requires_replan": True,
                    }
                ],
                "response_plan": {
                    "immediate": {
                        "text": "I will update the coffee request and check the new plan.",
                        "speech_act": "acknowledge",
                        "commitment_state": "evaluating",
                        "must_not_claim_completion": True,
                        "covers_task_ids": ["task-coffee-001"],
                    }
                },
                "confidence": 0.97,
                "reason_summary": "The user refined the active coffee goal.",
            }
        )
        resolver = TaskContinuityResolver(fake)  # type: ignore[arg-type]

        result = await resolver.resolve(self._request())

        self.assertEqual(len(result.operations), 1)
        operation = result.operations[0]
        self.assertEqual(operation.operation, "modify")
        self.assertEqual(operation.target_task_ids, ["task-coffee-001"])
        self.assertTrue(operation.operation_id.startswith("task-continuity:sid42:0:"))
        self.assertEqual(
            operation.goal_update["constraint_updates"]["temperature"],
            "iced",
        )
        self.assertEqual(result.metadata["accepted_operation_count"], 1)
        prompt = fake.calls[0]["prompt"]
        system = fake.calls[0]["system"]
        self.assertIn("Active task snapshots JSON", prompt)
        self.assertIn("Meaning and bounded context before lexical overlap", prompt)
        self.assertIn("Do not decide normal association through keywords", system)

    async def test_operation_id_is_stable_across_retries(self) -> None:
        payload = {
            "operations": [
                {
                    "operation": "modify",
                    "target_task_ids": ["task-coffee-001"],
                    "confidence": 0.95,
                    "goal_update": {"constraint_updates": {"temperature": "iced"}},
                }
            ],
            "confidence": 0.95,
        }
        resolver = TaskContinuityResolver(_FakeOllama(payload))  # type: ignore[arg-type]
        request = self._request()

        first = await resolver.resolve(request)
        second = await resolver.resolve(request)

        self.assertEqual(
            first.operations[0].operation_id,
            second.operations[0].operation_id,
        )

    async def test_unknown_and_low_confidence_operations_are_rejected(self) -> None:
        fake = _FakeOllama(
            {
                "operations": [
                    {
                        "operation": "modify",
                        "target_task_ids": ["unknown-task"],
                        "confidence": 0.99,
                        "goal_update": {"constraint_updates": {"temperature": "iced"}},
                    },
                    {
                        "operation": "modify",
                        "target_task_ids": ["task-coffee-001"],
                        "confidence": 0.2,
                        "goal_update": {"constraint_updates": {"temperature": "iced"}},
                    },
                ],
                "confidence": 0.8,
            }
        )
        resolver = TaskContinuityResolver(fake, min_confidence=0.65)  # type: ignore[arg-type]

        result = await resolver.resolve(self._request())

        self.assertEqual(result.operations, [])
        reasons = {
            item["reason"] for item in result.metadata["rejected_operations"]
        }
        self.assertEqual(
            reasons,
            {"unknown_target_task", "below_confidence_threshold"},
        )

    async def test_ambiguous_reference_can_return_clarification_without_operation(self) -> None:
        fake = _FakeOllama(
            {
                "operations": [],
                "response_plan": {
                    "immediate": {
                        "text": "Which drink should I make iced?",
                        "speech_act": "clarify",
                        "commitment_state": "waiting_for_user",
                        "must_not_claim_completion": True,
                        "covers_task_ids": ["task-coffee-001"],
                    }
                },
                "confidence": 0.78,
                "reason_summary": "The target is ambiguous.",
            }
        )
        resolver = TaskContinuityResolver(fake)  # type: ignore[arg-type]

        result = await resolver.resolve(self._request("Make that one iced."))

        self.assertEqual(result.operations, [])
        self.assertEqual(
            result.response_plan.immediate.speech_act,  # type: ignore[union-attr]
            "clarify",
        )


    async def test_model_timeout_returns_safe_empty_operation_set(self) -> None:
        resolver = TaskContinuityResolver(_FailingOllama())  # type: ignore[arg-type]

        result = await resolver.resolve(self._request())

        self.assertEqual(result.operations, [])
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.metadata["status"], "model_unavailable")
        self.assertEqual(result.metadata["error_type"], "TimeoutError")



class _FakeTaskContinuityClient:
    def __init__(self, result: SemanticTaskOperationSet) -> None:
        self.result = result

    async def resolve_task_continuity(self, *args: Any, **kwargs: Any) -> SemanticTaskOperationSet:
        return self.result


class OrchestratorTaskContinuityTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _assistant(mode: str, result: SemanticTaskOperationSet) -> VoiceAssistant:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        assistant.task_continuity_mode = mode
        assistant.task_continuity_timeout_ms = 5000
        assistant.enable_agent = True
        assistant.agent_client = _FakeTaskContinuityClient(result)
        assistant.task_continuity_report_tasks = set()
        assistant.session_log = lambda *args, **kwargs: None  # type: ignore[method-assign]
        return assistant

    @staticmethod
    def _context() -> dict[str, Any]:
        return {
            "history": [],
            "active_task_snapshots": [
                {
                    "task_id": "task-coffee-001",
                    "status": "planning",
                    "semantic_goal": {
                        "description": "Prepare coffee.",
                        "source_text": "Bring coffee.",
                    },
                    "goal_version": 1,
                    "plan_version": 0,
                    "open_information_gaps": [],
                    "commitment_state": "evaluating",
                }
            ],
        }

    async def test_apply_mode_replaces_router_operations_and_sets_authority(self) -> None:
        operation = SemanticTaskOperation(
            operation_id="task-continuity:sid:0:abc",
            operation="modify",
            target_task_ids=["task-coffee-001"],
            confidence=0.99,
            goal_update={"constraint_updates": {"temperature": "iced"}},
            requires_replan=True,
        )
        result = SemanticTaskOperationSet(
            operations=[operation],
            response_plan=ResponsePlan(
                immediate=ResponseStage(
                    text="I will update that request.",
                    commitment_state="evaluating",
                    covers_task_ids=["task-coffee-001"],
                )
            ),
            confidence=0.98,
        )
        assistant = self._assistant("apply", result)
        decision = RouteDecision(
            route="deep_thought",
            intent="refine request",
            confidence=0.9,
            metadata={
                "semantic_task_operations": [
                    {
                        "operation_id": "router-old",
                        "operation": "create",
                        "confidence": 0.8,
                        "goal": {
                            "description": "Wrong new goal.",
                            "source_text": "Make it iced.",
                        },
                    }
                ]
            },
        )

        reviewed = await assistant._review_task_continuity(
            object(),  # type: ignore[arg-type]
            user_text="Make it iced.",
            session_id="sid",
            context=self._context(),
            decision=decision,
        )

        metadata = reviewed.metadata
        self.assertTrue(metadata["semantic_task_resolution_authoritative"])
        self.assertEqual(
            metadata["semantic_task_operations"][0]["operation"],
            "modify",
        )
        self.assertIn("response_plan", metadata)

    async def test_report_only_mode_does_not_change_router_operation(self) -> None:
        result = SemanticTaskOperationSet(confidence=0.9)
        assistant = self._assistant("report_only", result)
        router_operations = [
            {
                "operation_id": "router-create",
                "operation": "create",
                "confidence": 0.8,
                "goal": {
                    "description": "A new task.",
                    "source_text": "Do something.",
                },
            }
        ]
        decision = RouteDecision(
            route="deep_thought",
            intent="new request",
            confidence=0.9,
            metadata={"semantic_task_operations": router_operations},
        )

        reviewed = await assistant._review_task_continuity(
            object(),  # type: ignore[arg-type]
            user_text="Do something.",
            session_id="sid",
            context=self._context(),
            decision=decision,
        )

        self.assertEqual(
            reviewed.metadata["semantic_task_operations"],
            router_operations,
        )
        self.assertEqual(
            reviewed.metadata["task_continuity_resolution"]["status"],
            "scheduled",
        )
        self.assertNotIn(
            "semantic_task_resolution_authoritative",
            reviewed.metadata,
        )
        pending = list(assistant.task_continuity_report_tasks)
        if pending:
            await __import__("asyncio").gather(*pending)

    def test_authoritative_empty_resolution_does_not_create_legacy_task(self) -> None:
        manager = ConversationStateManager()

        manager.record_user_turn(
            "sid",
            "Tell me a joke while the task remains open.",
            route="deep_thought",
            intent="casual side conversation",
            metadata={
                "source": "task_continuity_agent",
                "semantic_task_operations": [],
                "semantic_task_resolution_authoritative": True,
            },
        )

        self.assertEqual(manager.snapshot()["task_contexts"], [])


if __name__ == "__main__":
    unittest.main()
